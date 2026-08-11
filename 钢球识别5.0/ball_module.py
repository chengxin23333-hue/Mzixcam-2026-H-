"""钢球检测、物理坐标换算与短时预测模块。

坐标以 25 cm 摆杆中心 O 为零点，向右为正，位置单位为 mm，速度单位为
mm/s。MaixPy 硬件模块只在 ``BallVision`` 初始化时导入，因此几何和卡尔曼
算法可以在电脑上独立测试。
"""

import os

import config


STATUS_LOST = 0
STATUS_MEASURED = 1
STATUS_PREDICTED = 2

MARKER_SPECS_MM = ((-50.0, "-5"), (0.0, "O"), (50.0, "+5"))


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def map_box_from_model(box, source_width, source_height, model_width, model_height):
    """将 FIT_CONTAIN 模型画面中的检测框还原到相机画面。"""
    x, y, width, height = box
    scale = min(
        float(model_width) / float(source_width),
        float(model_height) / float(source_height),
    )
    pad_x = (model_width - source_width * scale) / 2.0
    pad_y = (model_height - source_height * scale) / 2.0

    x1 = clamp(int(round((x - pad_x) / scale)), 0, source_width - 1)
    y1 = clamp(int(round((y - pad_y) / scale)), 0, source_height - 1)
    x2 = clamp(int(round((x + width - pad_x) / scale)), x1 + 1, source_width)
    y2 = clamp(int(round((y + height - pad_y) / scale)), y1 + 1, source_height)
    return x1, y1, x2 - x1, y2 - y1


def validate_rod_points(left, right, frame_width, frame_height):
    points_in_frame = (
        0 <= left[0] < frame_width
        and 0 <= left[1] < frame_height
        and 0 <= right[0] < frame_width
        and 0 <= right[1] < frame_height
    )
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    return points_in_frame and dx * dx + dy * dy > 1.0


def _validate_finite_parameter(name, value, allow_zero=False):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid {}: must be a finite number".format(name))
    is_finite = number == number and abs(number) != float("inf")
    valid_range = number >= 0.0 if allow_zero else number > 0.0
    if not is_finite or not valid_range:
        relation = "nonnegative" if allow_zero else "positive"
        raise ValueError(
            "invalid {}: must be finite and {}".format(name, relation)
        )


def validate_physical_parameters():
    """在加载硬件前检查会参与除法或几何门限的现场参数。"""
    positive_parameters = (
        ("ROD_LENGTH_MM", config.ROD_LENGTH_MM),
        ("BALL_DIAMETER_MM", config.BALL_DIAMETER_MM),
        ("DISPLAY_BOX_SIZE_PX", config.DISPLAY_BOX_SIZE_PX),
        ("PIPE_HALF_WIDTH_PX", config.PIPE_HALF_WIDTH_PX),
        (
            "AXIS_MAX_DISTANCE_DIAMETERS",
            config.AXIS_MAX_DISTANCE_DIAMETERS,
        ),
        ("MARKER_HALF_LENGTH_PX", config.MARKER_HALF_LENGTH_PX),
    )
    for name, value in positive_parameters:
        _validate_finite_parameter(name, value)
    _validate_finite_parameter(
        "AXIS_RANGE_MARGIN_DIAMETERS",
        config.AXIS_RANGE_MARGIN_DIAMETERS,
        allow_zero=True,
    )


def project_to_rod(point, left, right):
    """把像素点投影到摆杆轴线，返回比例、投影点和垂直距离。"""
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    axis_length_sq = axis_x * axis_x + axis_y * axis_y
    if axis_length_sq <= 0.0:
        return 0.0, (float(left[0]), float(left[1])), float("inf")

    point_x = point[0] - left[0]
    point_y = point[1] - left[1]
    ratio = (point_x * axis_x + point_y * axis_y) / float(axis_length_sq)
    projected = (
        left[0] + ratio * axis_x,
        left[1] + ratio * axis_y,
    )
    distance_x = point[0] - projected[0]
    distance_y = point[1] - projected[1]
    distance = (distance_x * distance_x + distance_y * distance_y) ** 0.5
    return ratio, projected, distance


def ratio_to_point(ratio, left, right):
    return (
        left[0] + ratio * (right[0] - left[0]),
        left[1] + ratio * (right[1] - left[1]),
    )


def ratio_to_position_mm(ratio, rod_length_mm=config.ROD_LENGTH_MM):
    return (float(ratio) - 0.5) * float(rod_length_mm)


def position_mm_to_ratio(position_mm, rod_length_mm=config.ROD_LENGTH_MM):
    return 0.5 + float(position_mm) / float(rod_length_mm)


def make_fixed_box(center, side_px, frame_width, frame_height):
    """生成固定物理尺寸的正方形框，靠近边界时整体平移而不压扁。"""
    side = max(1, int(round(side_px)))
    side = min(side, int(frame_width), int(frame_height))
    x1 = int(round(center[0] - side / 2.0))
    y1 = int(round(center[1] - side / 2.0))
    x1 = int(clamp(x1, 0, frame_width - side))
    y1 = int(clamp(y1, 0, frame_height - side))
    return x1, y1, side, side


def make_pipe_guide_lines(left, right, half_width_px):
    """Return the two fixed pipe boundaries parallel to the calibrated axis."""
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    axis_length = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    if axis_length <= 0.0:
        raise ValueError("pipe axis must have nonzero length")
    normal_x = -axis_y / axis_length
    normal_y = axis_x / axis_length
    offset_x = normal_x * float(half_width_px)
    offset_y = normal_y * float(half_width_px)
    return (
        (
            left[0] - offset_x,
            left[1] - offset_y,
            right[0] - offset_x,
            right[1] - offset_y,
        ),
        (
            left[0] + offset_x,
            left[1] + offset_y,
            right[0] + offset_x,
            right[1] + offset_y,
        ),
    )


def make_marker_geometry(left, right, rod_length_mm, half_tick_px):
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    axis_length = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    normal_x = -axis_y / axis_length
    normal_y = axis_x / axis_length
    markers = []

    for position_mm, label in MARKER_SPECS_MM:
        ratio = position_mm_to_ratio(position_mm, rod_length_mm)
        point = ratio_to_point(ratio, left, right)
        markers.append(
            {
                "position_mm": position_mm,
                "point": point,
                "line": (
                    point[0] - normal_x * half_tick_px,
                    point[1] - normal_y * half_tick_px,
                    point[0] + normal_x * half_tick_px,
                    point[1] + normal_y * half_tick_px,
                ),
                "label": label,
            }
        )
    return markers


def ticks_diff_ms(now_ms, previous_ms, period_ms=config.TICKS_PERIOD_MS):
    """计算可回绕毫秒计数器的有符号差值。"""
    half_period = period_ms // 2
    return ((int(now_ms) - int(previous_ms) + half_period) % period_ms) - half_period


def elapsed_seconds(now_ms, previous_ms):
    elapsed_ms = ticks_diff_ms(now_ms, previous_ms)
    if elapsed_ms <= 0:
        return config.KALMAN_DEFAULT_DT_S
    return min(elapsed_ms / 1000.0, config.KALMAN_MAX_DT_S)


def new_filter_state():
    return {
        "initialized": False,
        "position_mm": 0.0,
        "velocity_mm_s": 0.0,
        "p00": config.KALMAN_INITIAL_POSITION_VARIANCE,
        "p01": 0.0,
        "p10": 0.0,
        "p11": config.KALMAN_INITIAL_VELOCITY_VARIANCE,
        "prediction_count": 0,
        "pending_mm": None,
        "pending_count": 0,
        "last_update_ms": None,
    }


def kalman_predict(state, dt_s):
    """常速度状态预测，过程噪声采用未建模加速度协方差。"""
    state = dict(state)
    if not state["initialized"]:
        return state

    dt_s = clamp(float(dt_s), 0.0, config.KALMAN_MAX_DT_S)
    p00 = state["p00"]
    p01 = state["p01"]
    p10 = state["p10"]
    p11 = state["p11"]
    acceleration_variance = config.KALMAN_ACCELERATION_VARIANCE
    dt2 = dt_s * dt_s
    dt3 = dt2 * dt_s
    dt4 = dt2 * dt2
    q00 = 0.25 * dt4 * acceleration_variance
    q01 = 0.5 * dt3 * acceleration_variance
    q11 = dt2 * acceleration_variance

    state["position_mm"] += state["velocity_mm_s"] * dt_s
    state["p00"] = p00 + dt_s * (p01 + p10) + dt2 * p11 + q00
    state["p01"] = p01 + dt_s * p11 + q01
    state["p10"] = p10 + dt_s * p11 + q01
    state["p11"] = p11 + q11
    return state


def kalman_correct(state, measurement_mm):
    """使用一维位置测量修正位置和速度，并保持协方差对称。"""
    state = dict(state)
    p00 = state["p00"]
    p01 = state["p01"]
    p10 = state["p10"]
    p11 = state["p11"]
    innovation_variance = p00 + config.KALMAN_MEASUREMENT_VARIANCE
    if innovation_variance <= 0.0:
        return state

    k0 = p00 / innovation_variance
    k1 = p10 / innovation_variance
    innovation = float(measurement_mm) - state["position_mm"]
    state["position_mm"] += k0 * innovation
    state["velocity_mm_s"] += k1 * innovation

    # H=[1,0] 的协方差更新；平均非对角项，抑制浮点累计的不对称。
    new_p00 = (1.0 - k0) * p00
    new_p01 = (1.0 - k0) * p01
    new_p10 = p10 - k1 * p00
    new_p11 = p11 - k1 * p01
    cross = 0.5 * (new_p01 + new_p10)
    state["p00"] = max(0.0, new_p00)
    state["p01"] = cross
    state["p10"] = cross
    state["p11"] = max(0.0, new_p11)
    return state


def _base_result(status, state):
    if status == STATUS_LOST:
        return {
            "status": STATUS_LOST,
            "x_mm": 0.0,
            "v_mm_s": 0.0,
            "prediction_count": 0,
        }
    return {
        "status": status,
        "x_mm": state["position_mm"],
        "v_mm_s": state["velocity_mm_s"],
        "prediction_count": state["prediction_count"],
    }


def attach_display_geometry(result, detected_center):
    """Attach display-only geometry without changing the tracker/UART result."""
    result = dict(result)
    status = result.get("status", STATUS_LOST)
    result["display_box"] = None
    result["display_center"] = None
    result["display_status"] = status
    if status == STATUS_LOST:
        return result

    if detected_center is not None:
        center = detected_center
        result["display_status"] = STATUS_MEASURED
    elif status == STATUS_PREDICTED:
        center = ratio_to_point(
            position_mm_to_ratio(result["x_mm"]),
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
        )
    else:
        return result

    result["display_center"] = center
    result["display_box"] = make_fixed_box(
        center,
        config.DISPLAY_BOX_SIZE_PX,
        config.CAPTURE_WIDTH,
        config.CAPTURE_HEIGHT,
    )
    return result


class BallTracker:
    """融合 YOLO 位置，并在短暂丢检时进行有限帧数预测。"""

    def __init__(self):
        self.state = new_filter_state()
        self.minimum_mm = -config.ROD_LENGTH_MM / 2.0
        self.maximum_mm = config.ROD_LENGTH_MM / 2.0

    def reset(self):
        """清除测量、速度和跳变确认，防止故障后复用旧状态。"""
        self.state = new_filter_state()

    def _reset_at_measurement(self, measurement_mm, now_ms):
        self.state = new_filter_state()
        self.state["initialized"] = True
        self.state["position_mm"] = clamp(
            float(measurement_mm), self.minimum_mm, self.maximum_mm
        )
        self.state["last_update_ms"] = int(now_ms)
        return _base_result(STATUS_MEASURED, self.state)

    def _clamp_physical_state(self):
        if self.state["position_mm"] <= self.minimum_mm:
            self.state["position_mm"] = self.minimum_mm
            if self.state["velocity_mm_s"] < 0.0:
                self.state["velocity_mm_s"] = 0.0
        elif self.state["position_mm"] >= self.maximum_mm:
            self.state["position_mm"] = self.maximum_mm
            if self.state["velocity_mm_s"] > 0.0:
                self.state["velocity_mm_s"] = 0.0

    def update(self, measurement_mm, now_ms, measurement_score=0.0):
        if not self.state["initialized"]:
            if measurement_mm is None:
                return _base_result(STATUS_LOST, self.state)
            return self._reset_at_measurement(measurement_mm, now_ms)

        previous_ms = self.state["last_update_ms"]
        dt_s = config.KALMAN_DEFAULT_DT_S
        if previous_ms is not None:
            dt_s = elapsed_seconds(now_ms, previous_ms)
        self.state = kalman_predict(self.state, dt_s)
        self.state["last_update_ms"] = int(now_ms)
        self._clamp_physical_state()

        accepted_measurement = measurement_mm
        if measurement_mm is None:
            self.state["pending_mm"] = None
            self.state["pending_count"] = 0
        else:
            measurement_mm = clamp(
                float(measurement_mm), self.minimum_mm, self.maximum_mm
            )
            max_jump_mm = config.MAX_JUMP_DIAMETERS * config.BALL_DIAMETER_MM
            residual_mm = measurement_mm - self.state["position_mm"]
            if abs(residual_mm) > max_jump_mm:
                if float(measurement_score) >= config.FAST_JUMP_CONFIDENCE_THRESHOLD:
                    return self._reset_at_measurement(measurement_mm, now_ms)
                pending_mm = self.state["pending_mm"]
                tolerance_mm = (
                    config.JUMP_CONFIRM_TOLERANCE_DIAMETERS
                    * config.BALL_DIAMETER_MM
                )
                if pending_mm is not None and abs(measurement_mm - pending_mm) <= tolerance_mm:
                    self.state["pending_count"] += 1
                else:
                    self.state["pending_count"] = 1
                self.state["pending_mm"] = measurement_mm

                if self.state["pending_count"] >= config.JUMP_CONFIRM_FRAMES:
                    return self._reset_at_measurement(measurement_mm, now_ms)
                accepted_measurement = None
            else:
                self.state["pending_mm"] = None
                self.state["pending_count"] = 0
                accepted_measurement = measurement_mm

        if accepted_measurement is not None:
            self.state = kalman_correct(self.state, accepted_measurement)
            self.state["prediction_count"] = 0
            self._clamp_physical_state()
            return _base_result(STATUS_MEASURED, self.state)

        self.state["prediction_count"] += 1
        if self.state["prediction_count"] > config.MAX_PREDICTION_FRAMES:
            self.state = new_filter_state()
            return _base_result(STATUS_LOST, self.state)
        return _base_result(STATUS_PREDICTED, self.state)


class BallVision:
    """MaixCAM YOLO 检测封装；不管理相机、串口、图传或本地显示。"""

    def __init__(self):
        validate_physical_parameters()
        if not validate_rod_points(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
        ):
            raise ValueError("invalid rod calibration points")

        from maix import image, nn

        self.image = image
        model_path = config.MODEL_LOCAL_PATH
        if not os.path.exists(model_path):
            model_path = config.MODEL_SYSTEM_PATH
        if not os.path.exists(model_path):
            raise RuntimeError("YOLO model not found: {}".format(model_path))

        # 闭环必须让检测结果、当前画面和时间戳属于同一帧。
        self.detector = nn.YOLOv5(model=model_path, dual_buff=False)
        self.model_width = self.detector.input_width()
        self.model_height = self.detector.input_height()
        self.input_format = self.detector.input_format()
        self.tracker = BallTracker()

        axis_x = config.ROD_RIGHT_POINT[0] - config.ROD_LEFT_POINT[0]
        axis_y = config.ROD_RIGHT_POINT[1] - config.ROD_LEFT_POINT[1]
        self.rod_length_px = (axis_x * axis_x + axis_y * axis_y) ** 0.5
        self.ball_diameter_px = (
            self.rod_length_px * config.BALL_DIAMETER_MM / config.ROD_LENGTH_MM
        )
        self.ratio_margin = (
            config.AXIS_RANGE_MARGIN_DIAMETERS
            * self.ball_diameter_px
            / self.rod_length_px
        )
        self.markers = make_marker_geometry(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.ROD_LENGTH_MM,
            config.MARKER_HALF_LENGTH_PX,
        )
        self.pipe_guide_lines = make_pipe_guide_lines(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.PIPE_HALF_WIDTH_PX,
        )

    def reset(self):
        self.tracker.reset()

    def process(self, img, now_ms):
        model_img = img.resize(
            self.model_width,
            self.model_height,
            self.image.Fit.FIT_CONTAIN,
        )
        objs = self.detector.detect(
            model_img,
            conf_th=config.CONFIDENCE_THRESHOLD,
            iou_th=config.IOU_THRESHOLD,
        )

        best = None
        best_ratio = None
        best_center = None
        raw_yolo_boxes = []
        for candidate in objs:
            mapped_box = map_box_from_model(
                (candidate.x, candidate.y, candidate.w, candidate.h),
                config.CAPTURE_WIDTH,
                config.CAPTURE_HEIGHT,
                self.model_width,
                self.model_height,
            )
            raw_yolo_boxes.append(mapped_box)
            center = (
                mapped_box[0] + mapped_box[2] / 2.0,
                mapped_box[1] + mapped_box[3] / 2.0,
            )
            ratio, _, axis_distance = project_to_rod(
                center,
                config.ROD_LEFT_POINT,
                config.ROD_RIGHT_POINT,
            )
            passes_axis_gate = (
                -self.ratio_margin <= ratio <= 1.0 + self.ratio_margin
                and axis_distance
                <= config.AXIS_MAX_DISTANCE_DIAMETERS * self.ball_diameter_px
            )
            if passes_axis_gate and (best is None or candidate.score > best.score):
                best = candidate
                best_ratio = clamp(ratio, 0.0, 1.0)
                best_center = center

        measurement_mm = None
        if best_ratio is not None:
            measurement_mm = ratio_to_position_mm(best_ratio)
        result = self.tracker.update(
            measurement_mm,
            now_ms,
            best.score if best is not None else 0.0,
        )
        result = attach_display_geometry(result, best_center)
        result["raw_yolo_boxes"] = tuple(raw_yolo_boxes)
        return result

    def draw_overlay(self, img, result, fps=0.0):
        draw_pipe_guide_lines(img, self.pipe_guide_lines, self.image)
        draw_markers(img, self.markers, self.image)
        if config.DEBUG_MODE:
            raw_box_color = self.image.COLOR_RED
            raw_boxes = result.get("raw_candidate_boxes")
            if raw_boxes is None:
                raw_boxes = result.get("raw_yolo_boxes", ())
            for raw_box in raw_boxes:
                img.draw_rect(*raw_box, color=raw_box_color, thickness=1)
        status = result.get("status", STATUS_LOST)
        display_status = result.get("display_status", status)
        box = result.get("display_box")
        if box is not None:
            box_color = (
                self.image.COLOR_GREEN
                if display_status == STATUS_MEASURED
                else self.image.COLOR_YELLOW
            )
            img.draw_rect(*box, color=box_color, thickness=2)

        if status == STATUS_MEASURED:
            status_text = "MEAS"
            status_color = self.image.COLOR_GREEN
        elif status == STATUS_PREDICTED:
            status_text = "PRED"
            status_color = self.image.COLOR_YELLOW
        else:
            status_text = "LOST"
            status_color = self.image.COLOR_RED
        fps_text = "fps:{:.1f}".format(fps)
        x_text = "x:{:+.1f}mm".format(result.get("x_mm", 0.0))
        v_text = "v:{:+.0f}mm/s".format(result.get("v_mm_s", 0.0))
        bottom_y = config.CAPTURE_HEIGHT - 14
        img.draw_string(2, 2, status_text, status_color)
        img.draw_string(
            right_aligned_x(fps_text, config.CAPTURE_WIDTH),
            2,
            fps_text,
            self.image.COLOR_WHITE,
        )
        img.draw_string(2, bottom_y, x_text, self.image.COLOR_WHITE)
        img.draw_string(
            right_aligned_x(v_text, config.CAPTURE_WIDTH),
            bottom_y,
            v_text,
            self.image.COLOR_WHITE,
        )
        return img


def right_aligned_x(text, frame_width, character_width_px=8, margin_px=2):
    return max(margin_px, int(frame_width) - margin_px - len(text) * character_width_px)


def draw_pipe_guide_lines(img, guide_lines, image_module):
    for x1, y1, x2, y2 in guide_lines:
        img.draw_line(
            int(round(x1)),
            int(round(y1)),
            int(round(x2)),
            int(round(y2)),
            image_module.COLOR_BLUE,
            thickness=2,
        )


def draw_markers(img, markers, image_module):
    """在固定画面中标出 -5 cm、中心 O 和 +5 cm。"""
    for marker in markers:
        x1, y1, x2, y2 = marker["line"]
        img.draw_line(
            int(round(x1)),
            int(round(y1)),
            int(round(x2)),
            int(round(y2)),
            image_module.COLOR_BLUE,
            thickness=2,
        )
        label_x = int(round(marker["point"][0])) - 8
        label_y = int(round(marker["point"][1])) + 8
        img.draw_string(label_x, label_y, marker["label"], image_module.COLOR_BLUE)
