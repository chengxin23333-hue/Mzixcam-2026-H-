"""钢球视觉 5.0 比赛主程序。

同一帧图像依次用于 YOLO/卡尔曼、UART0、浏览器图传和本地显示。各输出独立
限速，任何一个输出故障都不改变钢球状态的含义。
"""

from maix import app, camera, display, time

import config
from ball_module import STATUS_LOST
from communication import UartPublisher, init_uart
from video_stream import VideoStreamer

if config.ENABLE_AI:
    from ball_module import BallVision
    vision_mode = "ai"
else:
    from classic_ball_module import ClassicBallVision
    BallVision = ClassicBallVision
    vision_mode = "classic"


def ticks_diff_ms(now_ms, previous_ms):
    period = config.TICKS_PERIOD_MS
    half_period = period // 2
    return (
        (int(now_ms) - int(previous_ms) + half_period) % period
    ) - half_period


def interval_due(now_ms, previous_ms, interval_ms):
    if previous_ms is None:
        return True
    return ticks_diff_ms(now_ms, previous_ms) >= int(interval_ms)


def draw_overlay_safely(vision, img, result, fps):
    try:
        vision.draw_overlay(img, result, fps)
        return True
    except Exception as error:
        print("overlay error, disabled: {}".format(error))
        return False


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


def start_streamer():
    if not config.ENABLE_STREAM:
        print("http stream: disabled")
        return None
    streamer = VideoStreamer()
    if streamer.active:
        print("http stream: ready")
    return streamer


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


def main():
    # 先加载模型以取得模型输入格式，随后只创建一个 320x240 相机。
    vision = BallVision()
    cam = camera.Camera(
        config.CAPTURE_WIDTH,
        config.CAPTURE_HEIGHT,
        vision.input_format,
    )
    print(
        "vision: camera {}x{}, {} ready".format(
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
            vision_mode,
        )
    )

    uart_publisher = start_uart_publisher()
    streamer = start_streamer()
    disp = start_display()
    last_display_ms = None
    overlay_enabled = True

    while not app.need_exit():
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
            result = vision.process(img, now_ms)
            if overlay_enabled:
                overlay_enabled = draw_overlay_safely(
                    vision,
                    img,
                    result,
                    fps,
                )

        uart_publisher.publish(result, now_ms)

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
                disp.show(img)
                last_display_ms = now_ms
            except Exception as error:
                print("display write error, output disabled: {}".format(error))
                disp = None

if __name__ == "__main__":
    main()
