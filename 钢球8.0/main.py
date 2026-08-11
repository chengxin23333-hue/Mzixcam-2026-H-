"""钢球视觉 6.0 纯视觉比赛主程序。

同一帧图像依次用于经典检测/卡尔曼、UART0、浏览器图传和本地显示。各输出独立
限速，任何一个输出故障都不改变钢球状态的含义。
"""

from maix import app, camera, display, time

import config
from ball_module import STATUS_LOST
from classic_ball_module import ClassicBallVision
from communication import UartPublisher, init_uart
from video_stream import VideoStreamer


# MaixPy 的 ticks_ms 会在固定周期后回绕，不能直接用 now-previous 判断。
# 这里把差值折回到 [-period/2, period/2)；只要两次调用间隔远小于半周期，
# 即使计数器跨过 0，也能得到正确的正毫秒差。
def ticks_diff_ms(now_ms, previous_ms):
    period = config.TICKS_PERIOD_MS
    half_period = period // 2
    return (
        (int(now_ms) - int(previous_ms) + half_period) % period
    ) - half_period


# 通用限流判断。previous_ms 为 None 代表输出从未执行，第一次必须立即放行。
def interval_due(now_ms, previous_ms, interval_ms):
    if previous_ms is None:
        return True
    return ticks_diff_ms(now_ms, previous_ms) >= int(interval_ms)


# 叠加层只影响人看到的图像，不参与 UART 数据。绘制异常时返回 False，让主循环
# 永久关闭本次运行的叠加层，避免一个字体/颜色 API 错误反复中断实时识别。
def draw_overlay_safely(vision, img, result, fps, show_x_text=True):
    try:
        vision.draw_overlay(img, result, fps, show_x_text=show_x_text)
        return True
    except Exception as error:
        print("overlay error, disabled: {}".format(error))
        return False


def draw_x_text_safely(vision, img, result):
    try:
        vision.draw_x_text(img, result)
        return True
    except Exception as error:
        print("x text overlay error, disabled: {}".format(error))
        return False


def draw_calibration_points_safely(vision, img):
    try:
        vision.draw_local_calibration_points(img)
        return True
    except Exception as error:
        print("calibration point overlay error, disabled: {}".format(error))
        return False


# 无论串口是否启用或初始化是否成功，都返回一个 UartPublisher 对象。
# 串口为空的发布器会安静地忽略发送，这样主循环不需要到处判断 None。
def start_uart_publisher():
    if not config.ENABLE_UART:
        print("uart: disabled")
        return UartPublisher(None)
    try:
        serial_dev = init_uart()
        print(
            "uart: {} {} baud, TX {}, RX {}".format(
                config.UART_DEVICE,
                config.UART_BAUDRATE,
                config.UART_TX_PIN,
                config.UART_RX_PIN,
            )
        )
        return UartPublisher(serial_dev)
    except Exception as error:
        print("uart start error, output disabled: {}".format(error))
        return UartPublisher(None)


# JpegStreamer 内部负责 HTTP 服务；本函数只根据总开关决定是否创建。
# 图传启动失败时 VideoStreamer.active=False，识别和 UART 仍继续工作。
def start_streamer():
    if not config.ENABLE_STREAM:
        print("http stream: disabled")
        return None
    streamer = VideoStreamer()
    if streamer.active:
        print("http stream: ready")
    return streamer


# 本地屏幕也是可选输出。初始化失败返回 None，由主循环跳过显示分支。
def start_display():
    if not config.ENABLE_DISPLAY:
        print("display: disabled")
        return None
    try:
        disp = display.Display()
        print("display: ready")
        return disp
    except Exception as error:
        print("display start error, output disabled: {}".format(error))
        return None


# 自动白平衡可能因手、车体或背景进入画面而改变钢球颜色。比赛版默认使用固定
# 四通道增益；若固件不支持手动接口，捕获异常并保留相机默认设置继续运行。
def configure_camera_awb(cam):
    if config.AUTO_AWB:
        print("camera awb: auto")
        return True
    try:
        cam.awb_mode(camera.AwbMode.Manual)
        cam.set_wb_gain(config.AWB_GAIN)
        print("camera awb: manual")
        return True
    except Exception as error:
        print("camera awb config error, using default: {}".format(error))
        return False


# 主程序的数据流固定为：采集一帧 -> 视觉测量/跟踪 -> 绘制叠加层 -> UART ->
# 网页图传 -> 本地屏幕。UART、图传和屏幕各自限速，识别本身每个主循环都运行。
def main():
    # 视觉对象先创建，以便相机直接采用它要求的 BGR888 输入格式。
    vision = ClassicBallVision()
    cam = camera.Camera(
        config.CAPTURE_WIDTH,
        config.CAPTURE_HEIGHT,
        vision.input_format,
    )
    configure_camera_awb(cam)
    print(
        "vision: camera {}x{}, classic ready".format(
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
        )
    )

    # 三个输出分别初始化；其中任意一个失败都不会阻止另外两个启动。
    uart_publisher = start_uart_publisher()
    streamer = start_streamer()
    disp = start_display()
    last_display_ms = None
    overlay_enabled = True
    local_calibration_points_enabled = True
    local_x_text_enabled = True

    # app.need_exit() 由 MaixCam 应用框架处理退出请求，避免使用无限 while True
    # 导致应用被关闭时资源无法正常释放。
    while not app.need_exit():
        # 同一个 now_ms 传给本帧所有模块，保证跟踪时间、UART 和图传限流一致。
        now_ms = time.ticks_ms()
        img = cam.read()
        fps = time.fps()

        # 相机帧缺失时立即向主控报告 lost，不复用上一帧坐标。
        if img is None:
            vision.reset()
            result = {
                "status": STATUS_LOST,
                "x_mm": 0.0,
                "v_mm_s": 0.0,
            }
        else:
            # process() 只计算结果，不直接改写画面；叠加层在之后绘制，因此检测不会
            # 把上一帧画出的绿框、蓝线或文字当作本帧输入特征。
            result = vision.process(img, now_ms)
            if overlay_enabled:
                overlay_enabled = draw_overlay_safely(
                    vision,
                    img,
                    result,
                    fps,
                    show_x_text=False,
                )

        # 即使 img=None，也发送明确的 LOST，让主控不会继续使用旧坐标。
        uart_publisher.publish(result, now_ms)

        # 图传写入的是已经绘制叠加层的同一帧；未启用时 streamer 为 None。
        if img is not None and streamer is not None:
            streamer.publish(img, now_ms)

        if (
            img is not None
            and disp is not None
            and interval_due(
                now_ms,
                last_display_ms,
                config.DISPLAY_INTERVAL_MS,
            )
        ):
            try:
                if local_calibration_points_enabled:
                    local_calibration_points_enabled = draw_calibration_points_safely(
                        vision,
                        img,
                    )
                if local_x_text_enabled:
                    local_x_text_enabled = draw_x_text_safely(
                        vision,
                        img,
                        result,
                    )
                # 只有实际显示成功才更新时间，否则下一帧会立即重试一次。
                disp.show(img)
                last_display_ms = now_ms
            except Exception as error:
                # 运行中显示设备故障后将其置空，后续帧不再反复访问坏设备。
                print("display write error, output disabled: {}".format(error))
                disp = None

if __name__ == "__main__":
    main()
