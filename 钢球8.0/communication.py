"""UART0 主控通信模块。

协议：$VIS,status,x_mm,v_mm_s,seq,crc#\r\n
UART0 在应用启动前可能输出系统日志，主控必须从 '$' 帧头开始解析。
"""

import config


UART_ERROR_LOG_INTERVAL_MS = 1000


STATUS_LOST = 0
STATUS_MEASURED = 1
STATUS_PREDICTED = 2


def clamp_int(value, minimum, maximum):
    """将输入安全转换为整数并限制范围。"""
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        value = 0
    return max(int(minimum), min(int(maximum), value))


def crc8_atm(payload):
    """计算 ASCII 载荷的 CRC-8/ATM，poly=0x07，init=0x00。"""
    crc = 0
    for byte in str(payload).encode("ascii"):
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def normalize_result(result):
    """把识别结果转换为主控协议使用的三个整数。"""
    if not isinstance(result, dict):
        result = {}

    status = clamp_int(result.get("status", STATUS_LOST), 0, 2)
    if status == STATUS_LOST:
        return {"status": STATUS_LOST, "x_mm": 0, "v_mm_s": 0}

    return {
        "status": status,
        "x_mm": clamp_int(result.get("x_mm", 0), -32768, 32767),
        "v_mm_s": clamp_int(result.get("v_mm_s", 0), -32768, 32767),
    }


def build_vis_packet(result, sequence):
    """构造不含 CRLF 的完整 VIS 文本帧。"""
    result = normalize_result(result)
    sequence = clamp_int(sequence, 0, 65535)
    payload = "VIS,{},{},{},{}".format(
        result["status"],
        result["x_mm"],
        result["v_mm_s"],
        sequence,
    )
    return "${},{:02X}#".format(payload, crc8_atm(payload))


def next_sequence(sequence):
    return (int(sequence) + 1) & 0xFFFF


def ticks_diff_ms(now_ms, previous_ms):
    """计算带 ticks_ms 回绕的有符号毫秒差。"""
    period = config.TICKS_PERIOD_MS
    half_period = period // 2
    return (
        (int(now_ms) - int(previous_ms) + half_period) % period
    ) - half_period


def should_send_result(
    now_ms,
    last_send_ms,
    interval_ms=config.UART_SEND_INTERVAL_MS,
):
    if last_send_ms is None:
        return True
    return ticks_diff_ms(now_ms, last_send_ms) >= int(interval_ms)


def get_uart_config():
    return {
        "device": config.UART_DEVICE,
        "baudrate": config.UART_BAUDRATE,
        "tx_pin": config.UART_TX_PIN,
        "rx_pin": config.UART_RX_PIN,
        "tx_func": config.UART_TX_FUNC,
        "rx_func": config.UART_RX_FUNC,
    }


def init_uart():
    """映射 UART0 引脚并打开串口；硬件错误由启动层明确处理。"""
    from maix import err, pinmap, time as maix_time, uart

    uart_config = get_uart_config()
    err.check_raise(
        pinmap.set_pin_function(
            uart_config["tx_pin"],
            uart_config["tx_func"],
        ),
        "Failed set pin{} function to {}".format(
            uart_config["tx_pin"],
            uart_config["tx_func"],
        ),
    )
    err.check_raise(
        pinmap.set_pin_function(
            uart_config["rx_pin"],
            uart_config["rx_func"],
        ),
        "Failed set pin{} function to {}".format(
            uart_config["rx_pin"],
            uart_config["rx_func"],
        ),
    )
    serial_dev = uart.UART(
        uart_config["device"],
        uart_config["baudrate"],
    )
    maix_time.sleep_ms(50)
    return serial_dev


def send_packet(serial_dev, packet):
    """发送一帧并追加 CRLF；错误由发布器限流记录。"""
    if serial_dev is None:
        return False
    try:
        serial_dev.write_str(str(packet) + "\r\n")
        return True
    except Exception:
        return False


class UartPublisher:
    """管理固定发送周期和 16 位循环序号。"""

    def __init__(self, serial_dev, interval_ms=config.UART_SEND_INTERVAL_MS):
        self.serial_dev = serial_dev
        self.interval_ms = int(interval_ms)
        self.sequence = 0
        self.last_send_ms = None
        self.last_error_log_ms = None

    def publish(self, result, now_ms):
        if not should_send_result(
            now_ms,
            self.last_send_ms,
            self.interval_ms,
        ):
            return False

        packet = build_vis_packet(result, self.sequence)
        self.last_send_ms = int(now_ms)
        self.sequence = next_sequence(self.sequence)
        sent = send_packet(self.serial_dev, packet)
        if not sent and self.serial_dev is not None and should_send_result(
            now_ms,
            self.last_error_log_ms,
            UART_ERROR_LOG_INTERVAL_MS,
        ):
            print("uart write error, will retry")
            self.last_error_log_ms = int(now_ms)
        return sent
