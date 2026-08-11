"""钢球几何、物理坐标换算、短时预测与画面叠加模块。

坐标以 25 cm 摆杆中心 O 为零点，向左为正，位置单位为 mm，速度单位为
mm/s。此模块不依赖神经网络或相机硬件，因此可以在电脑上独立测试。
"""

import config


# 三种状态会原样交给 UART：LOST 没有可用目标，MEASURED 本帧有视觉测量，
# PREDICTED 本帧漏检但仍在卡尔曼允许的短时预测窗口内。
STATUS_LOST = 0
STATUS_MEASURED = 1
STATUS_PREDICTED = 2

# 通用限幅函数。这里不强制转换类型，调用者可同时用于浮点物理量和整数像素量。
def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


# 杆端点既要位于画面内，也必须相隔足够距离；两个点重合会让投影、单位向量和
# 理论球径计算出现除零。平方距离大于 1 还排除了几乎重合的亚像素标定。
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


# 配置加载阶段的数值防线：拒绝字符串、NaN、无穷大以及不允许的零/负数。
# name 只用于生成能直接指出错误参数的异常消息。
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


# 三点位置标定必须满足：像素从左到右严格增加，物理位置严格减小。
# “像素增、位置减”正是本项目左正右负的定义；如果顺序写反，速度符号也会反。
def validate_position_calibration(calibration, frame_width):
    if len(calibration) != 3:
        raise ValueError("POSITION_CALIBRATION must contain exactly 3 points")
    previous_pixel = None
    previous_position = None
    for pixel_x, position_mm in calibration:
        pixel_x = float(pixel_x)
        position_mm = float(position_mm)
        values_are_finite = (
            pixel_x == pixel_x
            and position_mm == position_mm
            and abs(pixel_x) != float("inf")
            and abs(position_mm) != float("inf")
        )
        if not values_are_finite or not (0.0 <= pixel_x < float(frame_width)):
            raise ValueError("invalid POSITION_CALIBRATION point")
        if previous_pixel is not None and pixel_x <= previous_pixel:
            raise ValueError("POSITION_CALIBRATION pixels must increase")
        if previous_position is not None and position_mm >= previous_position:
            raise ValueError("POSITION_CALIBRATION positions must decrease")
        previous_pixel = pixel_x
        previous_position = position_mm
    return True


# 两点线性映射公式：先求 value 在 source_a/source_b 间的比例，再把同一比例应用
# 到 target_a/target_b。ratio 允许小于 0 或大于 1，因此标定区间外仍可线性外推。
def _linear_map(value, source_a, target_a, source_b, target_b):
    ratio = (float(value) - float(source_a)) / float(source_b - source_a)
    return float(target_a) + ratio * float(target_b - target_a)


# 像素转毫米采用左右两段独立标定，避免相机透视导致“左边每像素毫米数”和
# “右边每像素毫米数”不同。pixel_x 恰好等于中心点时使用左段，结果仍为 0。
def pixel_to_position_mm(pixel_x, calibration=config.POSITION_CALIBRATION):
    left, center, right = calibration
    first, second = (left, center) if pixel_x <= center[0] else (center, right)
    return _linear_map(pixel_x, first[0], first[1], second[0], second[1])


# 毫米转像素是上一个函数的逆过程，主要供预测框和刻度位置绘制使用。
# 正位置选择左段，负位置选择右段，保持左正右负的一致性。
def position_mm_to_pixel(position_mm, calibration=config.POSITION_CALIBRATION):
    left, center, right = calibration
    first, second = (
        (left, center) if position_mm >= center[1] else (center, right)
    )
    return _linear_map(position_mm, first[1], first[0], second[1], second[0])


def validate_physical_parameters():
    """在加载硬件前检查会参与除法或几何门限的现场参数。"""
    positive_parameters = (
        ("ROD_LENGTH_MM", config.ROD_LENGTH_MM),
        ("BALL_DIAMETER_MM", config.BALL_DIAMETER_MM),
        ("DISPLAY_BOX_SIZE_PX", config.DISPLAY_BOX_SIZE_PX),
        ("PIPE_HALF_WIDTH_PX", config.PIPE_HALF_WIDTH_PX),
        ("RULER_HALF_RANGE_MM", config.RULER_HALF_RANGE_MM),
        ("RULER_STEP_MM", config.RULER_STEP_MM),
        ("RULER_MINOR_TICK_PX", config.RULER_MINOR_TICK_PX),
        ("RULER_MAJOR_TICK_PX", config.RULER_MAJOR_TICK_PX),
        ("RULER_LABEL_INTERVAL_MM", config.RULER_LABEL_INTERVAL_MM),
        ("RULER_LABEL_GAP_PX", config.RULER_LABEL_GAP_PX),
    )
    # 这些量都会作为除数、框尺寸或几何距离使用，必须严格大于零。
    for name, value in positive_parameters:
        _validate_finite_parameter(name, value)
    validate_position_calibration(
        config.POSITION_CALIBRATION,
        config.CAPTURE_WIDTH,
    )


def project_to_rod(point, left, right):
    """把像素点投影到摆杆轴线，返回比例、投影点和垂直距离。"""
    # 轴向向量 right-left 决定水管的真实倾斜方向，而不是假定水管完全水平。
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    axis_length_sq = axis_x * axis_x + axis_y * axis_y
    if axis_length_sq <= 0.0:
        return 0.0, (float(left[0]), float(left[1])), float("inf")

    # 点积/轴长平方得到投影比例：ratio=0 在左端，ratio=1 在右端。
    # 不对 ratio 限幅，因此杆端外的点仍会投影到轴线延长线上。
    point_x = point[0] - left[0]
    point_y = point[1] - left[1]
    ratio = (point_x * axis_x + point_y * axis_y) / float(axis_length_sq)
    projected = (
        left[0] + ratio * axis_x,
        left[1] + ratio * axis_y,
    )
    # 原始点到投影点的欧氏距离就是候选偏离水管轴线的垂距，经典检测用它
    # 排除蓝线走廊之外的背景轮廓。
    distance_x = point[0] - projected[0]
    distance_y = point[1] - projected[1]
    distance = (distance_x * distance_x + distance_y * distance_y) ** 0.5
    return ratio, projected, distance


# 把轴线比例重新还原成二维像素点；绘制倾斜水管上的刻度和预测框时使用。
def ratio_to_point(ratio, left, right):
    return (
        left[0] + ratio * (right[0] - left[0]),
        left[1] + ratio * (right[1] - left[1]),
    )


def point_to_position_mm(
    point,
    left=config.ROD_LEFT_POINT,
    right=config.ROD_RIGHT_POINT,
    calibration=config.POSITION_CALIBRATION,
):
    # 先消除候选中心在垂直方向的偏差，再仅使用轴线投影点的 x 做三点标定。
    # 因而钢球框在蓝线上下轻微晃动不会直接改变输出位置。
    _, projected, _ = project_to_rod(point, left, right)
    return pixel_to_position_mm(projected[0], calibration)


def position_mm_to_point(
    position_mm,
    left=config.ROD_LEFT_POINT,
    right=config.ROD_RIGHT_POINT,
    calibration=config.POSITION_CALIBRATION,
):
    # 三点标定当前以像素 x 为自变量，所以垂直轴线无法完成逆换算并明确报错。
    axis_x = float(right[0] - left[0])
    if axis_x == 0.0:
        raise ValueError("position calibration requires a nonvertical axis")
    pixel_x = position_mm_to_pixel(position_mm, calibration)
    # 求出该 x 在杆轴线上的比例，再恢复相应 y；相机略微倾斜时预测框仍贴着轴线。
    ratio = (pixel_x - float(left[0])) / axis_x
    return ratio_to_point(ratio, left, right)


def make_fixed_box(center, side_px, frame_width, frame_height):
    """生成固定物理尺寸的正方形框，靠近边界时整体平移而不压扁。"""
    # 最终显示框与检测轮廓大小解耦：无论反光轮廓多大，都画固定边长的绿/黄框。
    side = max(1, int(round(side_px)))
    side = min(side, int(frame_width), int(frame_height))
    x1 = int(round(center[0] - side / 2.0))
    y1 = int(round(center[1] - side / 2.0))
    # 靠近画面边缘时移动整个框，而不是缩小框，避免视觉上误以为球尺寸改变。
    x1 = int(clamp(x1, 0, frame_width - side))
    y1 = int(clamp(y1, 0, frame_height - side))
    return x1, y1, side, side


def make_pipe_guide_lines(left, right, half_width_px, extension_px=0.0):
    """Return the two fixed pipe boundaries parallel to the calibrated axis."""
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    axis_length = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    if axis_length <= 0.0:
        raise ValueError("pipe axis must have nonzero length")
    # unit 是沿水管方向的单位向量，normal 是旋转 90 度后的法向单位向量。
    unit_x = axis_x / axis_length
    unit_y = axis_y / axis_length
    normal_x = -axis_y / axis_length
    normal_y = axis_x / axis_length
    # extension 沿轴线延长两端，offset 沿法向量把中心轴复制成上下两条平行线。
    extension_x = unit_x * float(extension_px)
    extension_y = unit_y * float(extension_px)
    offset_x = normal_x * float(half_width_px)
    offset_y = normal_y * float(half_width_px)
    return (
        (
            left[0] - extension_x - offset_x,
            left[1] - extension_y - offset_y,
            right[0] + extension_x - offset_x,
            right[1] + extension_y - offset_y,
        ),
        (
            left[0] - extension_x + offset_x,
            left[1] - extension_y + offset_y,
            right[0] + extension_x + offset_x,
            right[1] + extension_y + offset_y,
        ),
    )


# 根据同一组三点位置标定生成下方蓝线外侧的调试尺。刻度线始终垂直于水管，
# 即使相机画面中的水管倾斜也不会画成固定竖线。
def make_marker_geometry(
    calibration,
    left,
    right,
    pipe_half_width_px,
    half_range_mm,
    step_mm,
    minor_tick_px,
    major_tick_px,
    label_interval_mm,
    label_gap_px,
):
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    axis_length = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    if abs(axis_x) <= 0.0 or axis_length <= 0.0:
        raise ValueError("position calibration requires a nonvertical axis")
    if half_range_mm <= 0.0 or step_mm <= 0.0 or label_interval_mm <= 0.0:
        raise ValueError("ruler range, step and label interval must be positive")
    unit_x = axis_x / axis_length
    unit_y = axis_y / axis_length
    normal_x = -axis_y / axis_length
    normal_y = axis_x / axis_length
    markers = []
    tick_count = int(round(2.0 * float(half_range_mm) / float(step_mm)))

    for tick_index in range(tick_count + 1):
        position_mm = float(half_range_mm) - tick_index * float(step_mm)
        pixel_x = position_mm_to_pixel(position_mm, calibration)
        ratio = (float(pixel_x) - float(left[0])) / float(axis_x)
        axis_point = ratio_to_point(ratio, left, right)
        baseline = (
            axis_point[0] + normal_x * pipe_half_width_px,
            axis_point[1] + normal_y * pipe_half_width_px,
        )

        is_major = abs(position_mm / 10.0 - round(position_mm / 10.0)) < 1e-6
        tick_length = major_tick_px if is_major else minor_tick_px

        line_end = (
            baseline[0] + normal_x * tick_length,
            baseline[1] + normal_y * tick_length,
        )
        label = ""
        label_point = line_end
        is_labeled = abs(
            position_mm / float(label_interval_mm)
            - round(position_mm / float(label_interval_mm))
        ) < 1e-6
        if is_labeled:
            position_cm = position_mm / 10.0
            if position_cm > 0.0:
                label = "+{:g}".format(position_cm)
            elif position_cm < 0.0:
                label = "{:g}".format(position_cm)
            else:
                label = "0"
            label_point = (
                line_end[0] + normal_x * label_gap_px - unit_x * len(label) * 4,
                line_end[1] + normal_y * label_gap_px - unit_y * len(label) * 4,
            )

        markers.append(
            {
                "position_mm": position_mm,
                "point": baseline,
                "line": (baseline[0], baseline[1], line_end[0], line_end[1]),
                "label": label,
                "label_point": label_point,
            }
        )
    return markers


def ticks_diff_ms(now_ms, previous_ms, period_ms=config.TICKS_PERIOD_MS):
    """计算可回绕毫秒计数器的有符号差值。"""
    # 通过模运算把差值折回半周期范围，解决 now_ms 从最大值回绕到 0 时普通减法
    # 得到巨大负数的问题。调用间隔必须远小于半周期，这在实时主循环中成立。
    half_period = period_ms // 2
    return ((int(now_ms) - int(previous_ms) + half_period) % period_ms) - half_period


# 把毫秒间隔转换为卡尔曼使用的秒。异常的非正间隔使用默认 50 ms；长卡顿最多
# 按 100 ms 处理，避免一次暂停让预测位置和过程噪声突然爆炸。
def elapsed_seconds(now_ms, previous_ms):
    elapsed_ms = ticks_diff_ms(now_ms, previous_ms)
    if elapsed_ms <= 0:
        return config.KALMAN_DEFAULT_DT_S
    return min(elapsed_ms / 1000.0, config.KALMAN_MAX_DT_S)


# 创建完全独立的新状态字典，供首次启动、手动 reset、LOST 超时和跳变重置共用。
def new_filter_state():
    return {
        # 未初始化时没有任何可信位置；第一帧测量只建立位置，速度保持 0。
        "initialized": False,
        "position_mm": 0.0,
        "velocity_mm_s": 0.0,
        # P=[[p00,p01],[p10,p11]] 是位置/速度估计误差协方差：
        # p00 位置方差，p11 速度方差，p01/p10 是位置与速度的交叉协方差。
        "p00": config.KALMAN_INITIAL_POSITION_VARIANCE,
        "p01": 0.0,
        "p10": 0.0,
        "p11": config.KALMAN_INITIAL_VELOCITY_VARIANCE,
        # prediction_count 统计连续没有被接受测量的帧数，达到上限后转 LOST。
        "prediction_count": 0,
        # pending_* 保存可疑大跳变，只有新位置连续出现才确认换目标。
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
    # 状态转移矩阵 F=[[1,dt],[0,1]]，对应“短时间内速度恒定”。
    # 本函数复制字典后再修改，避免调用者持有的旧快照被原地污染。
    p00 = state["p00"]
    p01 = state["p01"]
    p10 = state["p10"]
    p11 = state["p11"]
    # 实际钢球会加速，常速度模型无法直接描述；把未知加速度作为过程噪声 Q。
    # Q 的三个非零量来自连续白噪声加速度模型：dt^4/4、dt^3/2、dt^2。
    acceleration_variance = config.KALMAN_ACCELERATION_VARIANCE
    dt2 = dt_s * dt_s
    dt3 = dt2 * dt_s
    dt4 = dt2 * dt2
    q00 = 0.25 * dt4 * acceleration_variance
    q01 = 0.5 * dt3 * acceleration_variance
    q11 = dt2 * acceleration_variance

    # 位置和速度都带方向：左为正、右为负。负速度会让预测位置继续减小，即向右。
    # 常速度预测不直接改变 velocity，只有后续位置测量修正或边界限幅会改变它。
    state["position_mm"] += state["velocity_mm_s"] * dt_s
    # P'=F P F^T + Q。协方差随预测增大，表示漏检越久越不确定，下一次可靠测量
    # 对状态的修正权重也会相应增大。
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
    # 这里只测得位置 z，没有直接测速，所以观测矩阵 H=[1,0]。
    # S = HPH^T + R = p00 + 位置测量方差，是“预测与测量差值”的总不确定度。
    innovation_variance = p00 + config.KALMAN_MEASUREMENT_VARIANCE
    if innovation_variance <= 0.0:
        return state

    # K=[k0,k1]^T 是卡尔曼增益：k0 修正位置，k1 通过位置-速度交叉协方差
    # 间接修正速度。代码没有直接使用相邻位置做裸差分测速。
    k0 = p00 / innovation_variance
    k1 = p10 / innovation_variance
    # innovation=z-x_pred。测量比预测更靠左时为正，速度向正方向修正；更靠右时
    # 为负，速度向负方向修正。因此 velocity_mm_s 的正负就是实际运动方向。
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
    # LOST 强制输出零位置、零速度，防止主控误用已经清空的内部状态。
    if status == STATUS_LOST:
        return {
            "status": STATUS_LOST,
            "x_mm": 0.0,
            "v_mm_s": 0.0,
            "prediction_count": 0,
        }
    # MEASURED 和 PREDICTED 都保留有符号浮点状态；通信层才负责四舍五入成整数。
    return {
        "status": status,
        "x_mm": state["position_mm"],
        "v_mm_s": state["velocity_mm_s"],
        "prediction_count": state["prediction_count"],
    }


def attach_display_geometry(result, detected_center):
    """Attach display-only geometry without changing the tracker/UART result."""
    # 复制结果并只附加 display_* 字段，避免显示用像素坐标改变 UART 的物理量语义。
    result = dict(result)
    status = result.get("status", STATUS_LOST)
    result["display_box"] = None
    result["display_center"] = None
    result["display_status"] = status
    if status == STATUS_LOST:
        return result

    if detected_center is not None:
        # 本帧有轮廓中心时，绿框严格画在实际测量像素处。
        center = detected_center
        result["display_status"] = STATUS_MEASURED
    elif status == STATUS_PREDICTED:
        # 漏检时没有像素中心，把卡尔曼预测毫米位置逆换算成像素，显示黄色框。
        center = position_mm_to_point(
            result["x_mm"],
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.POSITION_CALIBRATION,
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
    """融合视觉测量，并在短暂丢检时进行有限帧数预测。"""

    def __init__(self):
        self.state = new_filter_state()
        # 物理状态限制在杆中心 ±杆长/2，防止预测持续跑到真实机构之外。
        self.minimum_mm = -config.ROD_LENGTH_MM / 2.0
        self.maximum_mm = config.ROD_LENGTH_MM / 2.0

    def reset(self):
        """清除测量、速度和跳变确认，防止故障后复用旧状态。"""
        self.state = new_filter_state()

    def _reset_at_measurement(self, measurement_mm, now_ms):
        # 首次锁定或确认大跳变时，从新位置重新开始：位置可信，但没有连续历史可用于
        # 判断速度，所以 velocity_mm_s 保持 new_filter_state() 给出的 0。
        self.state = new_filter_state()
        self.state["initialized"] = True
        self.state["position_mm"] = clamp(
            float(measurement_mm), self.minimum_mm, self.maximum_mm
        )
        self.state["last_update_ms"] = int(now_ms)
        return _base_result(STATUS_MEASURED, self.state)

    def _clamp_physical_state(self):
        # minimum 是最右端（负），maximum 是最左端（正）。到右端后只清除继续向右
        # 的负速度；到左端后只清除继续向左的正速度，允许速度指向杆内侧。
        if self.state["position_mm"] <= self.minimum_mm:
            self.state["position_mm"] = self.minimum_mm
            if self.state["velocity_mm_s"] < 0.0:
                self.state["velocity_mm_s"] = 0.0
        elif self.state["position_mm"] >= self.maximum_mm:
            self.state["position_mm"] = self.maximum_mm
            if self.state["velocity_mm_s"] > 0.0:
                self.state["velocity_mm_s"] = 0.0

    def update(self, measurement_mm, now_ms, measurement_score=0.0):
        # measurement_mm=None 表示本帧没有视觉位置；0.0 是有效的中心位置，不能
        # 使用 if measurement_mm 之类的真假判断。
        if not self.state["initialized"]:
            if measurement_mm is None:
                return _base_result(STATUS_LOST, self.state)
            return self._reset_at_measurement(measurement_mm, now_ms)

        # 每帧都先按上一速度预测到当前时刻，再判断是否接受本帧测量。这保证残差
        # 比较的是同一时间点的预测与测量，而不是上一帧位置与当前帧位置。
        previous_ms = self.state["last_update_ms"]
        dt_s = config.KALMAN_DEFAULT_DT_S
        if previous_ms is not None:
            dt_s = elapsed_seconds(now_ms, previous_ms)
        self.state = kalman_predict(self.state, dt_s)
        self.state["last_update_ms"] = int(now_ms)
        self._clamp_physical_state()

        accepted_measurement = measurement_mm
        if measurement_mm is None:
            # 漏检会中断“大跳变连续确认”，防止两次相隔很久的错误框拼成两帧确认。
            self.state["pending_mm"] = None
            self.state["pending_count"] = 0
        else:
            measurement_mm = clamp(
                float(measurement_mm), self.minimum_mm, self.maximum_mm
            )
            # 使用球径而不是固定毫米定义跳变阈值，使参数具有直观物理意义。
            max_jump_mm = config.MAX_JUMP_DIAMETERS * config.BALL_DIAMETER_MM
            residual_mm = measurement_mm - self.state["position_mm"]
            if abs(residual_mm) > max_jump_mm:
                # 高分候选允许快速重定位，但重置会把速度清零；这是防止把一次巨大
                # 位置变化直接换算成不可信的超大速度。
                if float(measurement_score) >= config.FAST_JUMP_SCORE_THRESHOLD:
                    return self._reset_at_measurement(measurement_mm, now_ms)
                pending_mm = self.state["pending_mm"]
                tolerance_mm = (
                    config.JUMP_CONFIRM_TOLERANCE_DIAMETERS
                    * config.BALL_DIAMETER_MM
                )
                # 普通大跳变必须在相近位置连续出现。第二帧仍靠近 pending_mm 才累计，
                # 否则把它当作另一个偶发候选并从 1 重新计数。
                if pending_mm is not None and abs(measurement_mm - pending_mm) <= tolerance_mm:
                    self.state["pending_count"] += 1
                else:
                    self.state["pending_count"] = 1
                self.state["pending_mm"] = measurement_mm

                if self.state["pending_count"] >= config.JUMP_CONFIRM_FRAMES:
                    return self._reset_at_measurement(measurement_mm, now_ms)
                # 尚未确认的大跳变不进入 kalman_correct，本帧按 PREDICTED 处理。
                accepted_measurement = None
            else:
                # 正常残差立即接受，同时清除之前未完成的大跳变确认。
                self.state["pending_mm"] = None
                self.state["pending_count"] = 0
                accepted_measurement = measurement_mm

        if accepted_measurement is not None:
            # 有效测量同时修正位置和速度，并把连续预测计数归零。
            self.state = kalman_correct(self.state, accepted_measurement)
            self.state["prediction_count"] = 0
            self._clamp_physical_state()
            return _base_result(STATUS_MEASURED, self.state)

        # 没有测量或测量被跳变门拒绝时，仅输出预测。超过允许帧数后完全清空，
        # 下一次检测将以速度 0 重新初始化，避免无限外推旧轨迹。
        self.state["prediction_count"] += 1
        if self.state["prediction_count"] > config.MAX_PREDICTION_FRAMES:
            self.state = new_filter_state()
            return _base_result(STATUS_LOST, self.state)
        return _base_result(STATUS_PREDICTED, self.state)


class BallVisionBase:
    """Shared display overlay for the pure-vision detector."""

    def draw_overlay(self, img, result, fps=0.0, show_x_text=True):
        # 蓝线和红色刻度仅为显示叠加；process() 在绘制前已经完成，不会把这些
        # 人工颜色当成下一次检测输入。
        if config.SHOW_PIPE_GUIDES:
            draw_pipe_guide_lines(img, self.pipe_guide_lines, self.image)
        if config.SHOW_ROI_FRAME:
            draw_roi_overlay(img, config.CLASSIC_ROD_ROI, self.image)
        if config.SHOW_SCALE_MARKERS:
            draw_markers(img, self.markers, self.image)
        if config.DEBUG_MODE:
            # 调试红框展示所有经过轮廓基础筛选的候选，不代表最终被跟踪器接受。
            raw_box_color = self.image.COLOR_RED
            raw_boxes = result.get("raw_candidate_boxes", ())
            for raw_box in raw_boxes:
                img.draw_rect(*raw_box, color=raw_box_color, thickness=1)
        status = result.get("status", STATUS_LOST)
        display_status = result.get("display_status", status)
        box = result.get("display_box")
        if box is not None:
            # 真实测量用绿色；仅靠卡尔曼外推的位置用黄色，便于现场区分数据来源。
            box_color = (
                self.image.COLOR_GREEN
                if display_status == STATUS_MEASURED
                else self.image.COLOR_YELLOW
            )
            img.draw_rect(*box, color=box_color, thickness=2)

        # status 文本和 UART 状态一致，不使用 display_status，防止显示层掩盖跟踪状态。
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
        # 显式 '+' 格式保留速度方向：正号向左，负号向右。
        v_text = "v:{:+.0f}mm/s".format(result.get("v_mm_s", 0.0))
        bottom_y = config.CAPTURE_HEIGHT - 14
        img.draw_string(2, 2, status_text, status_color)
        img.draw_string(
            right_aligned_x(fps_text, config.CAPTURE_WIDTH),
            2,
            fps_text,
            self.image.COLOR_WHITE,
        )
        if show_x_text:
            self.draw_x_text(img, result)
        img.draw_string(
            right_aligned_x(v_text, config.CAPTURE_WIDTH),
            bottom_y,
            v_text,
            self.image.COLOR_WHITE,
        )
        return img

    def draw_x_text(self, img, result):
        x_text = "x:{:+.1f}mm".format(result.get("x_mm", 0.0))
        bottom_y = config.CAPTURE_HEIGHT - 14
        img.draw_string(2, bottom_y, x_text, self.image.COLOR_WHITE)
        return img

    def draw_local_calibration_points(self, img):
        if not config.SHOW_LOCAL_CALIBRATION_POINTS:
            return img
        for position_mm in config.LOCAL_CALIBRATION_POINT_MM:
            point = position_mm_to_point(
                position_mm,
                config.ROD_LEFT_POINT,
                config.ROD_RIGHT_POINT,
                config.POSITION_CALIBRATION,
            )
            img.draw_circle(
                int(round(point[0])),
                int(round(point[1])),
                config.LOCAL_CALIBRATION_POINT_RADIUS_PX,
                self.image.COLOR_BLUE,
                thickness=-1,
            )
        return img


# Maix 字符绘制没有现成的右对齐测量，这里按每字符约 8 像素估算起点，
# 并用 margin 保证长文本不会产生负坐标。
def right_aligned_x(text, frame_width, character_width_px=8, margin_px=2):
    return max(margin_px, int(frame_width) - margin_px - len(text) * character_width_px)


def draw_roi_overlay(img, roi, image_module):
    """绘制当前识别 ROI 的黑色边框。"""
    x, y, width, height = roi
    img.draw_rect(
        x,
        y,
        width,
        height,
        color=image_module.COLOR_BLACK,
        thickness=1,
    )


# 将预计算的浮点蓝线坐标在真正绘制时统一四舍五入，避免几何函数过早丢精度。
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
    """绘制下方蓝线外侧的调试尺刻度和错行标签。"""
    for marker in markers:
        # 红线厚度固定为 1，降低开启刻度显示后遮挡钢球的概率。
        x1, y1, x2, y2 = marker["line"]
        img.draw_line(
            int(round(x1)),
            int(round(y1)),
            int(round(x2)),
            int(round(y2)),
            image_module.COLOR_RED,
            thickness=1,
        )
        if marker["label"]:
            label_x, label_y = marker["label_point"]
            img.draw_string(
                int(round(label_x)),
                int(round(label_y)),
                marker["label"],
                image_module.COLOR_RED,
            )
