"""Fixed-pipe classical steel-ball detector for the 8.0 application."""

import math

import config
from ball_module import (
    BallTracker,
    BallVisionBase,
    attach_display_geometry,
    clamp,
    make_marker_geometry,
    make_pipe_guide_lines,
    point_to_position_mm,
    position_mm_to_point,
    project_to_rod,
    elapsed_seconds,
    validate_physical_parameters,
    validate_rod_points,
)


# 兼容旧配置或精简配置：字段存在时使用现场值，不存在时退回代码内默认值。
# 这样新增实验参数不会让缺少该字段的旧 config.py 在导入阶段直接崩溃。
def _config(name, default):
    return getattr(config, name, default)


# 利用固定机构的真实比例推算钢球在画面中的理论直径：
# 球像素直径 / 杆像素长度 = 球真实直径 / 杆真实长度。
# 后续所有面积、宽高、轴线距离和搜索窗口都围绕这个尺度自适应。
def expected_ball_diameter_px(
    left,
    right,
    ball_diameter_mm=config.BALL_DIAMETER_MM,
    rod_length_mm=config.ROD_LENGTH_MM,
):
    # 使用二维欧氏长度而不是单独 x 差，因此相机轻微倾斜不会改变比例估计。
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    rod_length_px = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    return rod_length_px * float(ball_diameter_mm) / float(rod_length_mm)


# 对单个轮廓进行与图像位置无关的基础筛选，并把通过者转换成统一候选字典。
# 返回 None 表示该轮廓在此阶段已确定不可能是钢球。
def evaluate_contour_candidate(
    box,
    area,
    perimeter,
    center,
    motion_score,
    expected_diameter_px,
):
    x, y, width, height = box
    # 理论面积按圆计算；最小 1 像素保护后续除法。
    diameter = max(1.0, float(expected_diameter_px))
    expected_area = math.pi * (diameter * 0.5) ** 2
    # 面积门先排除小噪点和大块反光粘连。范围按理论圆面积的比例配置。
    if (
        area < expected_area * _config("CLASSIC_MIN_AREA_RATIO", 0.10)
        or area > expected_area * _config("CLASSIC_MAX_AREA_RATIO", 2.80)
    ):
        return None

    # 面积相近的细长物也可能通过第一关，因此再限制包围盒宽和高。
    minimum_size = diameter * _config("CLASSIC_MIN_DIAMETER_RATIO", 0.35)
    maximum_size = diameter * _config("CLASSIC_MAX_DIAMETER_RATIO", 1.85)
    if (
        width < minimum_size
        or height < minimum_size
        or width > maximum_size
        or height > maximum_size
    ):
        return None

    # 宽高比接近 1 更像球；max(1,height) 防止异常空框除零。
    aspect_ratio = width / float(max(1, height))
    if not (
        _config("CLASSIC_MIN_ASPECT_RATIO", 0.35)
        <= aspect_ratio
        <= _config("CLASSIC_MAX_ASPECT_RATIO", 2.80)
    ):
        return None

    # 圆度=4*pi*A/P^2，理想圆为 1；轮廓破碎、锯齿或细长时会降低。
    circularity = 0.0
    if perimeter > 0.0:
        circularity = 4.0 * math.pi * float(area) / (float(perimeter) ** 2)
    if circularity < _config("CLASSIC_MIN_CIRCULARITY", 0.06):
        return None

    # 评分不再做硬拒绝，而是用于多个合格候选间排序：尺寸占 50%，形状占 35%，
    # 运动只占 15%。因此静止球仍可以凭尺寸和形状被选中。
    measured_diameter = max(width, height)
    size_score = max(0.0, 1.0 - abs(measured_diameter - diameter) / diameter)
    shape_score = min(1.0, circularity / 0.75)
    motion_score = clamp(float(motion_score), 0.0, 1.0)
    detector_score = (
        0.50 * size_score + 0.35 * shape_score + 0.15 * motion_score
    )
    # center/box 此时仍是 ROI 局部坐标，稍后统一平移到完整画面坐标。
    return {
        "center": (float(center[0]), float(center[1])),
        "box": (int(x), int(y), int(width), int(height)),
        "detector_score": detector_score,
        "size_score": size_score,
        "shape_score": shape_score,
        "motion_score": motion_score,
    }


# 在一帧 ROI 内产生所有基础合格候选，同时返回模糊灰度图供下一帧运动差分。
# cv2_module/numpy_module 可注入假实现，方便电脑单元测试。
def detect_candidates(
    roi_bgr,
    previous_gray,
    expected_diameter_px,
    cv2_module=None,
    numpy_module=None,
    hsv_lower=None,
    hsv_upper=None,
    morphology_kernel=None,
):
    if cv2_module is None or numpy_module is None:
        import cv2 as cv2_module
        import numpy as numpy_module

    cv2 = cv2_module
    np = numpy_module
    if hsv_lower is None:
        hsv_lower = np.array(
            (0, 0, _config("CLASSIC_VALUE_MIN", 35)),
            dtype=np.uint8,
        )
    if hsv_upper is None:
        hsv_upper = np.array(
            (
                179,
                _config("CLASSIC_SATURATION_MAX", 85),
                _config("CLASSIC_VALUE_MAX", 255),
            ),
            dtype=np.uint8,
        )
    if morphology_kernel is None:
        morphology_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (3, 3),
        )

    # HSV 用于按亮度/饱和度找钢球；灰度图只用于帧差运动评分。
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    # 5x5 高斯模糊削弱传感器噪点和细碎纹理，避免帧差把静态背景噪声判成运动。
    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # 色相范围 0~179 全放行，只保留“低饱和度且亮度合适”的像素。钢球反射环境色
    # 后饱和度可能升高，因此 CLASSIC_SATURATION_MAX 是现场最敏感的参数之一。
    static_mask = cv2.inRange(
        hsv,
        hsv_lower,
        hsv_upper,
    )
    # 3x3 椭圆核更适合圆目标：OPEN 先去孤立亮点，CLOSE 再填钢球高光/阴影造成的孔洞。
    static_mask = cv2.morphologyEx(
        static_mask,
        cv2.MORPH_OPEN,
        morphology_kernel,
    )
    static_mask = cv2.morphologyEx(
        static_mask,
        cv2.MORPH_CLOSE,
        morphology_kernel,
        iterations=2,
    )

    # 第一帧没有 previous_gray，运动掩膜全零；运动只参与评分，不是轮廓生成条件，
    # 因此第一帧仍可能产生静态候选。
    if previous_gray is not None and previous_gray.shape == gray_blur.shape:
        # absdiff 不关心亮变暗还是暗变亮，只关心变化幅度。阈值后二值化，再膨胀一次
        # 覆盖移动球在前后位置留下的两瓣差分区域。
        difference = cv2.absdiff(previous_gray, gray_blur)
        _, motion_mask = cv2.threshold(
            difference,
            _config("CLASSIC_MOTION_THRESHOLD", 18),
            255,
            cv2.THRESH_BINARY,
        )
        motion_mask = cv2.dilate(
            motion_mask,
            morphology_kernel,
            iterations=1,
        )
    else:
        motion_mask = np.zeros_like(gray_blur)

    # RETR_EXTERNAL 只取最外层，避免一个带孔钢球同时产生内外多个候选。
    # CHAIN_APPROX_SIMPLE 压缩直线上的冗余点，降低周长和矩计算成本。
    contour_result = cv2.findContours(
        static_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    # OpenCV 不同版本 findContours 返回 2 项或 3 项，倒数第二项始终是 contours。
    contours = contour_result[-2]
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        perimeter = cv2.arcLength(contour, True)
        # 优先使用轮廓矩的质心，比包围盒中心更贴近不完整亮斑的真实重心。
        moments = cv2.moments(contour)
        if moments["m00"] > 0.0:
            center = (
                moments["m10"] / moments["m00"],
                moments["m01"] / moments["m00"],
            )
        else:
            center = (x + width * 0.5, y + height * 0.5)

        # motion_score 是候选包围盒内运动像素的平均占比：黑=0、白=255，除以 255
        # 后归一化到 0~1。它描述“这个候选区域有多少发生了变化”。
        motion_region = motion_mask[y : y + height, x : x + width]
        motion_score = (
            float(np.mean(motion_region)) / 255.0
            if motion_region.size
            else 0.0
        )
        candidate = evaluate_contour_candidate(
            (x, y, width, height),
            area,
            perimeter,
            center,
            motion_score,
            expected_diameter_px,
        )
        if candidate is not None:
            candidates.append(candidate)

    return candidates, gray_blur


# detect_candidates 为提高效率只看 ROI，输出坐标相对 ROI 左上角。本函数复制每个
# 候选并加回 roi_x/roi_y，使轴线筛选、显示和物理标定统一使用完整画面坐标。
def translate_candidates(candidates, roi):
    roi_x, roi_y, _, _ = roi
    translated = []
    for candidate in candidates:
        item = dict(candidate)
        center_x, center_y = candidate["center"]
        item["center"] = (center_x + roi_x, center_y + roi_y)
        x, y, width, height = candidate["box"]
        item["box"] = (x + roi_x, y + roi_y, width, height)
        translated.append(item)
    return translated


def is_near_rod_endpoint(
    center,
    left,
    right,
    diameter_px,
    zone_diameters,
):
    """Return whether a center is within the configured along-axis end zone."""
    axis_x = float(right[0] - left[0])
    axis_y = float(right[1] - left[1])
    axis_length = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    if axis_length <= 0.0:
        return False
    ratio, _, _ = project_to_rod(center, left, right)
    endpoint_distance = min(abs(ratio), abs(1.0 - ratio)) * axis_length
    zone_width = max(0.0, float(diameter_px) * float(zone_diameters))
    return endpoint_distance <= zone_width


# 从基础候选中选择唯一目标。筛选顺序为：轴线走廊硬门 -> 已有轨迹时的
# 距离硬门 -> 综合评分排序。
def select_classic_candidate(
    candidates,
    previous_center,
    left,
    right,
    diameter_px,
):
    diameter = max(1.0, float(diameter_px))
    accepted = []
    axis_distance_limit = diameter * _config(
        "CLASSIC_AXIS_DISTANCE_DIAMETERS", 1.0
    )
    track_distance_limit = diameter * _config(
        "CLASSIC_TRACK_GATE_DIAMETERS", 2.0
    )
    for candidate in candidates:
        # 先排除远离水管轴线的背景，即使它的面积和形状非常像球也不接受。
        _, _, distance = project_to_rod(candidate["center"], left, right)
        if distance > axis_distance_limit:
            continue
        if previous_center is not None:
            # 有轨迹后再加位置连续性硬门，防止远处固定刻度突然获得高分并抢框。
            delta_x = candidate["center"][0] - previous_center[0]
            delta_y = candidate["center"][1] - previous_center[1]
            track_distance = (delta_x * delta_x + delta_y * delta_y) ** 0.5
            if track_distance > track_distance_limit:
                continue
        accepted.append(candidate)
    if not accepted:
        return None

    def score(candidate):
        # detector_score 奖励尺寸/圆度/运动；两个减分项分别惩罚偏离轴线和偏离
        # 上一轨迹位置。这里是排序软惩罚，不会替代上面的硬拒绝门限。
        center = candidate["center"]
        _, _, distance = project_to_rod(center, left, right)
        value = float(candidate.get("detector_score", 0.0))
        value -= 0.35 * distance / diameter
        if previous_center is not None:
            delta_x = center[0] - previous_center[0]
            delta_y = center[1] - previous_center[1]
            track_distance = (delta_x * delta_x + delta_y * delta_y) ** 0.5
            value -= 0.25 * track_distance / diameter
        return value

    return max(accepted, key=score)


# 端部保持后，快速返回的真球可能已越过普通的轨迹距离门。此选择器只在端部保持
# 激活且普通选择失败时使用，并用“轴线内 + 高质量 + 有运动”限制静态高光误释放。
def select_endpoint_release_candidate(candidates, left, right, diameter_px):
    diameter = max(1.0, float(diameter_px))
    axis_distance_limit = diameter * _config(
        "CLASSIC_AXIS_DISTANCE_DIAMETERS", 1.0
    )
    min_score = _config("CLASSIC_ENDPOINT_RELEASE_MIN_SCORE", 0.45)
    min_motion = _config("CLASSIC_ENDPOINT_RELEASE_MIN_MOTION", 0.08)
    accepted = []
    for candidate in candidates:
        _, _, distance = project_to_rod(candidate["center"], left, right)
        if distance > axis_distance_limit:
            continue
        if float(candidate.get("detector_score", 0.0)) < min_score:
            continue
        if float(candidate.get("motion_score", 0.0)) < min_motion:
            continue
        accepted.append((candidate, distance))
    if not accepted:
        return None

    def score(item):
        candidate, distance = item
        return float(candidate.get("detector_score", 0.0)) - (
            0.35 * distance / diameter
        )

    return max(accepted, key=score)[0]


# 不修改 BallTracker 状态地预估“当前时刻”应位于哪个像素。它只供本帧候选选择
# 作为参考，真正的预测/校正仍由 tracker.update 统一执行一次。
def predicted_tracker_center(tracker, now_ms):
    state = tracker.state
    if not state.get("initialized", False):
        return None
    position_mm = float(state["position_mm"])
    previous_ms = state.get("last_update_ms")
    if previous_ms is not None:
        # 左正右负的速度直接参与 x_mm += v*dt；随后逆标定为像素中心。
        position_mm += float(state["velocity_mm_s"]) * elapsed_seconds(
            now_ms, previous_ms
        )
    # 参考位置同样不能越过真实杆长，避免搜索窗跑到机构外部。
    position_mm = clamp(
        position_mm,
        -config.ROD_LENGTH_MM * 0.5,
        config.ROD_LENGTH_MM * 0.5,
    )
    return position_mm_to_point(
        position_mm,
        config.ROD_LEFT_POINT,
        config.ROD_RIGHT_POINT,
        config.POSITION_CALIBRATION,
    )


# ROI 必须为位于完整帧内的正面积矩形；越界切片虽然不一定报错，却会让标定和
# 坐标平移悄悄不一致，因此在启动阶段明确拒绝。
def validate_classic_roi(roi, frame_width, frame_height):
    x, y, width, height = roi
    return (
        width > 0
        and height > 0
        and x >= 0
        and y >= 0
        and x + width <= frame_width
        and y + height <= frame_height
    )


# 在 Maix 图像层先裁出水管区域，再把这张小图转换成 NumPy/OpenCV 数组。
# 顺序必须是 crop -> to_bytes：若先转换完整帧，即使后面再切片，仍会复制和整理
# 320x240 的全部像素。返回值坐标以 ROI 左上角为原点，完整画面坐标稍后统一加回。
def image_roi_to_cv2(img, roi, image_module, numpy_module):
    roi_x, roi_y, roi_width, roi_height = roi
    roi_img = img.crop(roi_x, roi_y, roi_width, roi_height)
    if roi_img.format() != image_module.Format.FMT_BGR888:
        roi_img = roi_img.to_format(image_module.Format.FMT_BGR888)
    data = numpy_module.frombuffer(
        roi_img.to_bytes(),
        dtype=numpy_module.uint8,
    )
    return data.reshape((roi_height, roi_width, 3))


class ClassicBallVision(BallVisionBase):
    """OpenCV detector that preserves the tracking and overlay contract."""

    def __init__(self):
        # 先验证纯配置，再导入 Maix/OpenCV 硬件相关模块，配置错误能更早、更清楚地暴露。
        validate_physical_parameters()
        if not validate_rod_points(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
        ):
            raise ValueError("invalid rod calibration points")

        self.roi = _config("CLASSIC_ROD_ROI", (8, 75, 304, 90))
        if not validate_classic_roi(
            self.roi,
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
        ):
            raise ValueError("invalid CLASSIC_ROD_ROI")

        # 延迟导入让本文件中的几何和候选函数可在没有 MaixPy 的电脑测试环境中加载。
        from maix import image
        import cv2
        import numpy as np

        self.image = image
        self.cv2 = cv2
        self.np = np
        self.hsv_lower = np.array(
            (0, 0, config.CLASSIC_VALUE_MIN),
            dtype=np.uint8,
        )
        self.hsv_upper = np.array(
            (179, config.CLASSIC_SATURATION_MAX, config.CLASSIC_VALUE_MAX),
            dtype=np.uint8,
        )
        self.morphology_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (3, 3),
        )
        # OpenCV 直接处理 BGR；相机使用相同格式可避免主循环每帧额外转换色序。
        self.input_format = image.Format.FMT_BGR888
        self.tracker = BallTracker()
        # 理论球径在固定相机/固定机构下不变，只需启动时计算一次。
        self.ball_diameter_px = expected_ball_diameter_px(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
        )
        # previous_gray 用于帧差；previous_center/missed_frames 用于候选位置连续性。
        self.previous_gray = None
        self.previous_center = None
        self.endpoint_hold_center = None
        self.max_track_misses = _config("CLASSIC_MAX_TRACK_MISSES", 3)
        self.missed_frames = self.max_track_misses + 1
        # 纯显示几何同样只需预计算一次，process() 不会修改这些固定线段。
        self.markers = make_marker_geometry(
            config.POSITION_CALIBRATION,
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.PIPE_HALF_WIDTH_PX,
            config.RULER_HALF_RANGE_MM,
            config.RULER_STEP_MM,
            config.RULER_MINOR_TICK_PX,
            config.RULER_MAJOR_TICK_PX,
            config.RULER_LABEL_INTERVAL_MM,
            config.RULER_LABEL_GAP_PX,
        )
        self.pipe_guide_lines = make_pipe_guide_lines(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.PIPE_HALF_WIDTH_PX,
            config.PIPE_GUIDE_EXTENSION_PX,
        )

    def reset(self):
        # 相机断帧时清除所有跨帧状态，防止恢复后把断帧前的速度或灰度图
        # 应用到完全不同的场景。固定标定几何无需重算。
        self.tracker.reset()
        self.previous_gray = None
        self.previous_center = None
        self.endpoint_hold_center = None
        self.missed_frames = self.max_track_misses + 1

    def process(self, img, now_ms):
        # 1. 先在 Maix 图像层裁出水管 ROI，只将这张小图转换为 NumPy。
        # img 本身仍是完整帧，主循环可继续在原图上画框、显示并发送网页图传。
        roi_bgr = image_roi_to_cv2(img, self.roi, self.image, self.np)
        # 2. 使用上一帧灰度产生运动分数；调用结束后立即保存当前灰度供下一帧使用。
        roi_candidates, current_gray = detect_candidates(
            roi_bgr,
            self.previous_gray,
            self.ball_diameter_px,
            self.cv2,
            self.np,
            self.hsv_lower,
            self.hsv_upper,
            self.morphology_kernel,
        )
        self.previous_gray = current_gray
        # 3. 后续轴线、标定和显示均使用完整画面坐标，不能继续保留 ROI 局部坐标。
        candidates = translate_candidates(roi_candidates, self.roi)
        endpoint_hold_enabled = _config("ENABLE_ENDPOINT_HOLD", True)
        if not endpoint_hold_enabled:
            self.endpoint_hold_center = None

        # 只有最近漏检数未超限时才使用轨迹参考；超限后允许新目标从任意轴线位置锁定。
        tracking_reference = None
        if self.missed_frames <= self.max_track_misses:
            # 优先使用带速度的当前时刻预测；滤波器尚未初始化时退回上一像素中心。
            tracking_reference = predicted_tracker_center(self.tracker, now_ms)
            if tracking_reference is None:
                tracking_reference = self.previous_center
        # 4. 从本帧所有轮廓中选出唯一候选；静止球也可凭尺寸和形状入选。
        best = select_classic_candidate(
            candidates,
            tracking_reference,
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            self.ball_diameter_px,
        )
        if (
            best is None
            and self.endpoint_hold_center is not None
            and endpoint_hold_enabled
        ):
            best = select_endpoint_release_candidate(
                candidates,
                config.ROD_LEFT_POINT,
                config.ROD_RIGHT_POINT,
                self.ball_diameter_px,
            )
        # 这些变量构成视觉层交给跟踪器的统一接口。measurement_mm=None 明确表示
        # 本帧没有可接受测量；detected_center 只服务于显示框像素位置。
        measurement_mm = None
        detected_center = None
        detector_score = 0.0
        # 5. 直接使用最佳轮廓作为本帧测量，不要求先运动或建立外观模型。
        if best is not None:
            detected_center = best["center"]
            detector_score = best["detector_score"]
            if (
                endpoint_hold_enabled
                and is_near_rod_endpoint(
                    detected_center,
                    config.ROD_LEFT_POINT,
                    config.ROD_RIGHT_POINT,
                    self.ball_diameter_px,
                    _config("CLASSIC_ENDPOINT_HOLD_ZONE_DIAMETERS", 2.0),
                )
            ):
                self.endpoint_hold_center = detected_center
            else:
                self.endpoint_hold_center = None
        elif endpoint_hold_enabled and self.endpoint_hold_center is not None:
            # 固定挡板处球与热熔胶会粘成大轮廓。此前真实测量已确认球到端部时，
            # 继续使用最后端部中心作为机械限位测量；调试红框仍只表示真实轮廓。
            detected_center = self.endpoint_hold_center
            detector_score = 1.0
            if self.tracker.state.get("initialized", False):
                self.tracker.state["velocity_mm_s"] = 0.0

        # 6. 把最终像素测量投影到轴线并换算毫米。轮廓分数同时交给 BallTracker，
        # 用于判断大跳变能否直接接受。
        if detected_center is not None:
            measurement_mm = point_to_position_mm(
                detected_center,
                config.ROD_LEFT_POINT,
                config.ROD_RIGHT_POINT,
                config.POSITION_CALIBRATION,
            )
            # 真实轮廓成功后重置经典检测漏帧计数，并更新下一帧位置参考。
            self.previous_center = detected_center
            self.missed_frames = 0
        else:
            # 经典层漏帧超过阈值后清除像素参考；卡尔曼仍有自己独立的预测帧上限。
            self.missed_frames += 1
            if self.missed_frames > self.max_track_misses:
                self.previous_center = None

        # 7. 跟踪器负责毫米位置/有符号速度、跳变确认和 MEAS/PRED/LOST 状态。
        result = self.tracker.update(measurement_mm, now_ms, detector_score)
        # 显示几何是附加字段，不改变 UART 使用的 x_mm/v_mm_s/status。
        result = attach_display_geometry(result, detected_center)
        # 调试关闭时不构造候选框元组，减少比赛主循环中的临时对象。
        if config.DEBUG_MODE:
            result["raw_candidate_boxes"] = tuple(
                candidate["box"] for candidate in candidates
            )
        return result
