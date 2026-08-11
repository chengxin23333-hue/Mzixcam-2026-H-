"""官方 HTTP JPEG 图传的启动、限流与故障隔离封装。"""

import config
from receiver_page import PAGE_HTML


def ticks_diff_ms(now_ms, previous_ms):
    period = config.TICKS_PERIOD_MS
    half_period = period // 2
    return (
        (int(now_ms) - int(previous_ms) + half_period) % period
    ) - half_period


class VideoStreamer:
    """向浏览器发布带标注画面；图传故障不会终止视觉与串口。"""

    def __init__(
        self,
        stream_factory=None,
        interval_ms=config.STREAM_INTERVAL_MS,
    ):
        self.interval_ms = int(interval_ms)
        self.last_publish_ms = None
        self.stream = None
        self.active = False

        try:
            if stream_factory is None:
                from maix import http

                stream_factory = http.JpegStreamer
            self.stream = stream_factory()
            self.stream.set_html(PAGE_HTML)
            self.stream.start()
            self.active = True
        except Exception as error:
            print("http stream start error: {}".format(error))

    def publish(self, img, now_ms):
        if not self.active:
            return False
        if self.last_publish_ms is not None:
            elapsed_ms = ticks_diff_ms(now_ms, self.last_publish_ms)
            if elapsed_ms < self.interval_ms:
                return False

        try:
            self.stream.write(img)
            self.last_publish_ms = int(now_ms)
            return True
        except Exception as error:
            print("http stream write error, stream disabled: {}".format(error))
            self.active = False
            return False
