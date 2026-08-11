"""比赛版集中配置。

所有现场需要调整的参数都放在本文件。坐标以摆杆中心 O 为原点，
位置单位为毫米，向右为正；速度单位为毫米/秒，向右为正。
"""


# ==================== 功能开关 ====================

ENABLE_UART = False      # UART0 串口通信
ENABLE_STREAM = False    # 网页图传
ENABLE_DISPLAY = True   # MaixCAM 本地小屏
DEBUG_MODE = False      # 1 像素红色 YOLO 原始框


# ==================== 相机与模型 ====================

ENABLE_AI = False

CAPTURE_WIDTH = 320
CAPTURE_HEIGHT = 240

MODEL_LOCAL_PATH = "model_310353.mud"
MODEL_SYSTEM_PATH = "/root/models/model_310353.mud"
CONFIDENCE_THRESHOLD = 0.5
IOU_THRESHOLD = 0.45


# ==================== Classic detector ====================

CLASSIC_ROD_ROI = (8, 75, 304, 90)
CLASSIC_SATURATION_MAX = 85
CLASSIC_VALUE_MIN = 35
CLASSIC_VALUE_MAX = 255
CLASSIC_MOTION_THRESHOLD = 18
CLASSIC_MIN_DIAMETER_RATIO = 0.35
CLASSIC_MAX_DIAMETER_RATIO = 1.85
CLASSIC_MIN_AREA_RATIO = 0.10
CLASSIC_MAX_AREA_RATIO = 2.80
CLASSIC_MIN_ASPECT_RATIO = 0.35
CLASSIC_MAX_ASPECT_RATIO = 2.80
CLASSIC_MIN_CIRCULARITY = 0.06
CLASSIC_AXIS_DISTANCE_DIAMETERS = 1.75
CLASSIC_MAX_TRACK_MISSES = 3


# ==================== 摆杆标定 ====================

# 固定摄像头后，将两点改为 25 cm 有效摆杆左右端的中心像素。
ROD_LEFT_POINT = (20, 120)
ROD_RIGHT_POINT = (300, 120)
ROD_LENGTH_MM = 250.0
BALL_DIAMETER_MM = 10.0
DISPLAY_BOX_SIZE_PX = 24
PIPE_HALF_WIDTH_PX = 16
MARKER_HALF_LENGTH_PX = 6.0

# YOLO 球心到摆杆轴线和端点的允许范围，单位为球直径倍数。
AXIS_MAX_DISTANCE_DIAMETERS = 1.8
AXIS_RANGE_MARGIN_DIAMETERS = 1.0


# ==================== 卡尔曼跟踪 ====================

# 位置测量方差，单位为 mm^2。
KALMAN_MEASUREMENT_VARIANCE = 4.0
# 未建模加速度方差，单位为 (mm/s^2)^2。
KALMAN_ACCELERATION_VARIANCE = 1000000.0
KALMAN_INITIAL_POSITION_VARIANCE = 25.0
KALMAN_INITIAL_VELOCITY_VARIANCE = 10000.0
KALMAN_DEFAULT_DT_S = 0.05
KALMAN_MAX_DT_S = 0.10

MAX_PREDICTION_FRAMES = 5
MAX_JUMP_DIAMETERS = 2.8
JUMP_CONFIRM_TOLERANCE_DIAMETERS = 0.8
JUMP_CONFIRM_FRAMES = 2
FAST_JUMP_CONFIDENCE_THRESHOLD = 0.75


# ==================== UART0 主控通信 ====================

# UART0 会输出系统启动日志；主控必须等待 '$' 帧头后再开始解析。
# A16 上电时被外部拉低可能影响启动，接线和上电顺序必须实机验证。
UART_DEVICE = "/dev/ttyS0"
UART_BAUDRATE = 115200
UART_TX_PIN = "A16"
UART_RX_PIN = "A17"
UART_TX_FUNC = "UART0_TX"
UART_RX_FUNC = "UART0_RX"
UART_SEND_INTERVAL_MS = 50


# ==================== 图传与显示 ====================
STREAM_INTERVAL_MS = 67
DISPLAY_INTERVAL_MS = 100


# MaixPy ticks_ms 通常使用 2^30 周期，用于桌面可测试的回绕差值计算。
TICKS_PERIOD_MS = 1 << 30
