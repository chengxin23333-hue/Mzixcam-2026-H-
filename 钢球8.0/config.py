"""比赛版集中配置。

所有现场需要调整的参数都放在本文件。坐标以摆杆中心 O 为原点，
位置单位为毫米，向左为正；速度单位为毫米/秒，向左为正。
"""


# ==================== 功能开关 ====================

# 四个输出/调试开关彼此独立：例如关闭图传不会影响串口，显示初始化失败也不会
# 停止视觉计算。比赛时建议只开启主控真正需要的输出，以降低 CPU 和网络负担。
ENABLE_UART = True      # UART0 串口通信
ENABLE_STREAM = True    # 网页图传
ENABLE_DISPLAY =True   # MaixCAM 本地小屏
DEBUG_MODE = True      # 1 像素红色经典视觉候选框
ENABLE_ENDPOINT_HOLD = True  # 末端位置保持、漏检复用及高速返回释放总开关
SHOW_PIPE_GUIDES = False  # 两条蓝色水管引导线
SHOW_SCALE_MARKERS = False  # 下方蓝线外侧的红色调试尺刻度与标签
SHOW_ROI_FRAME = True  # 黑色识别 ROI 边框与尺寸标签
SHOW_LOCAL_CALIBRATION_POINTS = True  # 仅本地屏显示的 +5/0/-5 cm 蓝色校准点


# ==================== 相机 ====================

# 识别、坐标标定和叠加层都以 320x240 为基准；改变分辨率后必须同步重做 ROI、
# 杆端点和三点位置标定，不能只修改下面两个数字。
CAPTURE_WIDTH = 320
CAPTURE_HEIGHT = 240

# 自动白平衡会随手、车体和背景颜色变化，导致同一颗钢球的 HSV 饱和度漂移。
# False 表示锁定下面四通道增益，使现场颜色条件尽量稳定；若改为 True，AWB_GAIN
# 不再由本程序主动写入相机。
AUTO_AWB = False
AWB_GAIN = [0.134, 0.0625, 0.0625, 0.1139]


# ==================== Classic detector ====================

# ROI 格式为 (左上角 x, 左上角 y, 宽, 高)。当前只处理两条蓝线附近的 30 像素
# 高条带，ROI 外画面仍可显示/图传，但不参与 HSV、运动差分和轮廓运算。
# 高度过小会裁断贴边钢球；过大则会把水管外的高光和车体背景带入候选集。
CLASSIC_ROD_ROI = (8, 112, 292, 16)

# 静态亮色掩膜采用 HSV 条件：任意色相、低饱和度、亮度位于指定区间。
# SATURATION_MAX 调大可接纳更多带环境反色的钢球，同时也会增加彩色背景干扰。
# VALUE_MIN 调大可排除暗背景，但钢球阴影区域会更容易断裂；VALUE_MAX 通常保持 255。
CLASSIC_SATURATION_MAX = 65
CLASSIC_VALUE_MIN = 35
CLASSIC_VALUE_MAX = 255

# 相邻灰度帧的像素差超过该值才算运动。值小对慢球敏感但容易响应曝光噪声，
# 值大可抑制抖动但可能漏掉速度慢、对比度低的钢球。
CLASSIC_MOTION_THRESHOLD = 18

# 下列尺寸/面积门限都相对于“由杆长和真实球径推算出的理论像素球径”。
# 放宽范围能容忍反光造成的轮廓残缺或粘连，但会让刻度、高光更容易通过。
CLASSIC_MIN_DIAMETER_RATIO = 0.35
CLASSIC_MAX_DIAMETER_RATIO = 1.85
CLASSIC_MIN_AREA_RATIO = 0.10
CLASSIC_MAX_AREA_RATIO = 2.80

# 宽高比 1.0 最像正方形/圆形包围盒。当前范围较宽，用来容忍钢球轮廓只剩一部分。
CLASSIC_MIN_ASPECT_RATIO = 0.35
CLASSIC_MAX_ASPECT_RATIO = 2.80

# 圆度公式为 4*pi*面积/周长^2，理想圆接近 1。阈值越高越严格，但高光破碎时
# 真实钢球的圆度也会明显下降。
CLASSIC_MIN_CIRCULARITY = 0.06

# 候选中心到水管轴线的最大垂距，以理论球径为单位。1.0 表示最多偏离一个球径。
CLASSIC_AXIS_DISTANCE_DIAMETERS = 1.0

# 经典检测连续漏掉多少帧后，previous_center 不再作为候选选择参考。
# 这与下面卡尔曼 MAX_PREDICTION_FRAMES 不是同一个计数器。
CLASSIC_MAX_TRACK_MISSES = 3

# 已有跟踪参考时，候选超过 2 个球径直接拒绝，防止远处固定白色刻度抢走轨迹。
CLASSIC_TRACK_GATE_DIAMETERS = 2.0

# 球被真实识别到端部后，若因贴住固定挡板而失去轮廓，则保持最后端部位置。
# 端部区域沿轴线向内延伸两个理论球径；中间区域不会触发机械限位保持。
CLASSIC_ENDPOINT_HOLD_ZONE_DIAMETERS = 2.0
# 端部保持期间，球高速返回会越过普通轨迹距离门。只有候选同时满足检测质量和
# 帧间运动量要求时才解除保持，避免静态高光或刻度把绿框从端部拉走。
CLASSIC_ENDPOINT_RELEASE_MIN_SCORE = 0.45
CLASSIC_ENDPOINT_RELEASE_MIN_MOTION = 0.08


# ==================== 摆杆标定 ====================

# 固定摄像头后，将两点改为 25 cm 有效摆杆左右端的中心像素。
# 两个点还定义水管轴线方向；即使相机略微倾斜，候选也会先投影到该轴线再换算位置。
ROD_LEFT_POINT = (20, 120)
ROD_RIGHT_POINT = (300, 120)

# 真实长度和球径都用毫米。理论像素球径 = 轴线像素长度 * 球径 / 杆长，
# 因此修改任一物理量都会连带改变轮廓尺寸门限和跟踪跳变门限。
ROD_LENGTH_MM = 250.0
BALL_DIAMETER_MM = 10.0

# 三点标定格式为 (像素 x, 物理位置 mm)。像素从左到右递增，位置必须递减，
# 因而本系统统一采用“左正右负”：x=95 为 +50 mm，x=230.6 为 -50 mm。
# 左半段和右半段分别线性插值，可补偿透视造成的两侧比例不同。
POSITION_CALIBRATION = (
    (98.0, 50.0),
    (158.4, 0.0),
    (218, -50.0),
)
# 最终绿/黄框固定为 24x24，不随原始轮廓大小变化，便于比赛画面观察。
DISPLAY_BOX_SIZE_PX = 24
# 本地屏校准辅助点，不参与识别、UART 或网页图传。
LOCAL_CALIBRATION_POINT_MM = (50.0, 0.0, -50.0)
LOCAL_CALIBRATION_POINT_RADIUS_PX = 2
# 蓝线距离轴线各 10 像素，左右再延长 15 像素；它们只是显示参考，不参与分割。
PIPE_HALF_WIDTH_PX = 10
PIPE_GUIDE_EXTENSION_PX = 15
# 调试尺从 +10 cm 到 -10 cm 每 5 mm 一格；整厘米用长刻度，其余用短刻度。
# 仅每 50 mm 显示数字，避免 MaixCAM 实机字体在密集位置相互重叠。
RULER_HALF_RANGE_MM = 100.0
RULER_STEP_MM = 5.0
RULER_MINOR_TICK_PX = 4.0
RULER_MAJOR_TICK_PX = 8.0
RULER_LABEL_INTERVAL_MM = 50.0
RULER_LABEL_GAP_PX = 4.0

# ==================== 卡尔曼跟踪 ====================

# 位置测量方差，单位为 mm^2。
# 值小表示更相信视觉位置，响应快但更容易跟随像素抖动；值大则更平滑但滞后。
KALMAN_MEASUREMENT_VARIANCE = 4.0
# 未建模加速度方差，单位为 (mm/s^2)^2。
# 当前数值很大，允许钢球快速变速，因此速度响应灵敏，同时也可能更抖。
KALMAN_ACCELERATION_VARIANCE = 1000000.0
# 初始协方差不是实际位置/速度，而是滤波器对初始状态“不确定程度”的估计。
# 初始速度不确定度较大，使第二、三帧位置测量能快速建立有方向的速度。
KALMAN_INITIAL_POSITION_VARIANCE = 25.0
KALMAN_INITIAL_VELOCITY_VARIANCE = 10000.0
# 时间戳异常或没有上一时间时按 50 ms 计算；实际间隔最多按 100 ms 计算，
# 防止一次卡顿被当成超长运动时间而破坏协方差。
KALMAN_DEFAULT_DT_S = 0.05
KALMAN_MAX_DT_S = 0.10

# 没有视觉测量时最多输出 5 帧 PRED；再漏一帧就清空状态并输出 LOST。
MAX_PREDICTION_FRAMES = 5
# 单帧残差超过 2.8 个球径（当前 28 mm）视为可疑跳变。
MAX_JUMP_DIAMETERS = 2.8
# 可疑新位置连续出现时，两帧之间相差不超过 0.8 个球径才算同一新目标；
# 满足 JUMP_CONFIRM_FRAMES 后在新位置重置滤波器，重置瞬间速度为 0。
JUMP_CONFIRM_TOLERANCE_DIAMETERS = 0.8
JUMP_CONFIRM_FRAMES = 2
# 检测评分足够高时允许跳过两帧确认，直接接受快速位移；同样会重置速度。
FAST_JUMP_SCORE_THRESHOLD = 0.75


# ==================== UART0 主控通信 ====================

# UART0 会输出系统启动日志；主控必须等待 '$' 帧头后再开始解析。
# A16 上电时被外部拉低可能影响启动，接线和上电顺序必须实机验证。
# 线路约定：MaixCAM TX(A16) 接主控 RX，MaixCAM RX(A17) 接主控 TX，并共地。
UART_DEVICE = "/dev/ttyS0"
UART_BAUDRATE = 115200
UART_TX_PIN = "A16"
UART_RX_PIN = "A17"
UART_TX_FUNC = "UART0_TX"
UART_RX_FUNC = "UART0_RX"
# 50 ms 表示最多 20 Hz 发送视觉结果；主循环可以更快运行，但发布器会自行限速。
UART_SEND_INTERVAL_MS = 50


# ==================== 图传与显示 ====================
# 图传约 15 FPS，本地屏幕约 10 FPS。二者只限制输出，不限制识别和 UART 更新频率。
STREAM_INTERVAL_MS = 67
DISPLAY_INTERVAL_MS = 100


# MaixPy ticks_ms 通常使用 2^30 周期，用于桌面可测试的回绕差值计算。
TICKS_PERIOD_MS = 1 << 30
