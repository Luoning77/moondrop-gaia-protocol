"""MOONDROP Pudding GAIA V3 蓝牙控制台。

用法:
    python tools/webtest.py --demo                 # 假设备，完整面板
    python tools/webtest.py --demo --demo-noack    # 假设备模拟 SET 无 ACK
    python tools/webtest.py --port COM5            # 真机 SPP 串口
    python tools/webtest.py --find-port            # 只打印自动检测到的串口
    python tools/webtest.py --web-port 9090        # 自定义 Web 端口

面板覆盖: 降噪五档、手势 5 行 × 左右耳、电量、增益、指示灯、
提示音、LHDC、一拖二，并保留自定义 Feature/Cmd 与原始 TX/RX 日志。
"""
import sys, json, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import serial

VENDOR_ID = 0x001D

# 帧里的 Feature 字节 = feature_id << 1（低 bit 为响应标志）
FEATURE_NAMES = {
    0x00: "基础查询",
    0x04: "ANC V1",
    0x0A: "EQ",
    0x10: "AudioCuration",
    0x1A: "电池",
    0x1C: "提示音",
    0x1E: "增益",
    0x20: "编解码",
    0x24: "空间音频",
    0x26: "指示灯",
    0x28: "一拖二",
    0x2C: "手势",
    0x30: "关机",
    0x3C: "左右声道",
    0x40: "ANC V2",
}

ANC_MODES = {0x00: "关闭", 0x01: "自适应", 0x02: "通透", 0x03: "抗风噪", 0x04: "降噪"}
GAIN_LEVELS = {0x00: "高", 0x01: "中", 0x02: "低"}
BATTERY_NAMES = {1: "左耳", 2: "右耳", 3: "充电盒"}
TOUCH_ACTIONS = {
    0: "无", 1: "播放/暂停", 2: "上一曲", 3: "下一曲",
    4: "音量+", 5: "音量-", 6: "语音助手", 7: "降噪切换",
}
TOUCH_ROWS = ("单击", "双击", "三击", "长按1秒", "长按3秒")
ERROR_NAMES = {
    0: "不支持的特性", 1: "不支持的命令", 2: "未认证", 3: "资源不足",
    4: "认证中", 5: "参数无效", 6: "状态错误", 7: "处理中",
}


def feature_name(f):
    base = f & 0xFE
    return FEATURE_NAMES.get(base) or f"0x{base:02X} / feature {base >> 1}"


def _ascii(payload):
    if not payload:
        return ""
    printable = sum(1 for b in payload if 32 <= b < 127)
    if len(payload) >= 2 and printable >= len(payload) * 0.6:
        return "".join(chr(b) for b in payload if 32 <= b < 127)
    return ""


def _hex_bytes(values):
    return " ".join(f"{v:02X}" for v in values)


def _touch_pair(value):
    left = TOUCH_ACTIONS.get((value >> 4) & 0xF, f"未定义{((value >> 4) & 0xF)}")
    right = TOUCH_ACTIONS.get(value & 0xF, f"未定义{(value & 0xF)}")
    return f"L:{left} / R:{right}"


def parse_battery(payload):
    """解析 [ID:1][level:1] 对，0xFF = 不可用。"""
    if len(payload) < 2 or len(payload) % 2 != 0:
        return None
    batteries = []
    for i in range(0, len(payload), 2):
        bid = payload[i]
        batteries.append({
            "id": bid,
            "name": BATTERY_NAMES.get(bid, f"设备{bid}"),
            "level": payload[i + 1],
        })
    return batteries


def _summarize(d):
    """把解析后的帧变成一行人类可读文本，供 Web 日志直接显示。"""
    if not d:
        return ""
    payload = d.get("payload") or []
    base_feature = d.get("feature_base")
    cmd = d.get("cmd_base")
    frame_type = d.get("frame_type")

    if frame_type == "error":
        code = payload[0] if payload else None
        name = ERROR_NAMES.get(code, f"错误码 {code}")
        return f"设备错误: {name}" + (f" ({code})" if code is not None else "")
    if frame_type == "command":
        return ""

    if base_feature == 0x00:
        if cmd == 0x00:
            return f"GAIA 版本: {_hex_bytes(payload) or '(空)'}"
        if cmd == 0x01:
            return f"支持的特性: {max(0, (len(payload) - 1) // 2)} 项"
        if cmd == 0x02:
            return f"支持的特性(下一页): {max(0, (len(payload) - 1) // 2)} 项"
        if cmd == 0x03:
            return f"设备序列号: {d.get('ascii') or '(空)'}"
        if cmd == 0x05:
            return f"应用/固件版本: {d.get('ascii') or '(空)'}"
        if cmd == 0x07:
            return f"注册通知: {_hex_bytes(payload) or '(空)'}"
        if cmd == 0x08:
            return f"取消通知: {_hex_bytes(payload) or '(空)'}"
        if cmd == 0x0C:
            pid = f"0x{payload[0]:02X}" if payload else "?"
            return f"传输信息 {pid}: {_hex_bytes(payload[1:]) or '(空)'}"
        if cmd == 0x0D:
            return f"传输参数: {_hex_bytes(payload) or '(空)'}"
        if cmd == 0x14:
            return f"左耳序列号: {d.get('ascii') or '(空)'}"
        if cmd == 0x15:
            return f"右耳序列号: {d.get('ascii') or '(空)'}"
        return f"基础 C:0x{cmd:02X}"

    if base_feature == 0x40:
        if cmd in (0x03, 0x04) and payload:
            return f"ANC 模式: {ANC_MODES.get(payload[0], '未知')} (0x{payload[0]:02X})"
        if cmd == 0x29 and payload:
            return ("ANC 切换配置: " + " ".join(
                f"{name}={payload[i] if i < len(payload) else '?'}"
                for i, name in enumerate(("STATE", "ON", "OFF", "通透", "ORDER"))
            ))
        if cmd in (0x29, 0x2A):
            return f"ANC 切换配置: {_hex_bytes(payload) or '(空)'}"
        return f"ANC C:0x{cmd:02X}"

    if base_feature == 0x1A:
        if cmd == 0x00:
            return f"支持的电池: {', '.join(str(b) for b in payload) or '(空)'}"
        if cmd == 0x01 and d.get("battery"):
            parts = []
            for bat in d["battery"]:
                level = "不可用" if bat["level"] == 0xFF else f"{bat['level']}%"
                parts.append(f"{bat['name']} {level}")
            return "电量: " + " · ".join(parts)
        return f"电池 C:0x{cmd:02X}"

    if base_feature == 0x1E:
        if payload:
            return f"增益: {GAIN_LEVELS.get(payload[0], '未知')} (0x{payload[0]:02X})"
        return "增益: (空)"

    if base_feature == 0x26:
        if payload:
            return f"指示灯: {'开' if payload[0] else '关'}"
        return "指示灯: (空)"

    if base_feature == 0x1C:
        if len(payload) >= 3:
            return (f"提示音: {'开' if payload[0] else '关'} · "
                    f"音量 {payload[1]} · 组号 {payload[2]}")
        return f"提示音: {_hex_bytes(payload) or '(空)'}"

    if base_feature == 0x20:
        names = {0x01: "LC3", 0x02: "LDAC", 0x05: "LHDC", 0x03: "LC3", 0x04: "LDAC", 0x06: "LHDC"}
        label = names.get(cmd, f"C:0x{cmd:02X}")
        if payload:
            return f"{label}: {'开' if payload[0] else '关'}"
        return f"{label}: (空)"

    if base_feature == 0x2C:
        if len(payload) >= 5:
            kind = {1: "出厂默认", 2: "当前", 3: "写回"}.get(cmd, f"C:0x{cmd:02X}")
            rows = "；".join(f"{TOUCH_ROWS[i]} {_touch_pair(payload[i])}" for i in range(5))
            return f"手势[{kind}]: {rows}"
        return f"手势: {_hex_bytes(payload) or '(空)'}"

    if base_feature == 0x28:
        if cmd == 0x01 and payload:
            return f"一拖二: {'开' if payload[0] else '关'}"
        if cmd == 0x03 and payload:
            return f"一拖二超时: {payload[0]} 秒"
        if cmd == 0x05:
            name = ""
            if len(payload) > 7:
                name = bytes(payload[7:]).decode("utf-8", "replace").strip("\x00 ")
            return f"一拖二设备: {name or d.get('ascii') or _hex_bytes(payload) or '(空)'}"
        if cmd == 0x06:
            return "一拖二设备: (下一页/无更多)"
        return f"一拖二 C:0x{cmd:02X}"

    if base_feature == 0x0A:
        return f"EQ C:0x{cmd:02X}: {_hex_bytes(payload) or '(空)'}"

    return ""


def build_tx(feature, cmd, payload=b"", seq=0):
    """构造 FF 04 封装帧。len 字段 = payload 字节数（与真机抓包一致）。"""
    payload = bytes(payload)
    if len(payload) > 0xFFFF:
        raise ValueError("payload 过长")
    n = len(payload)
    header = bytes([
        0xFF, 0x04, (n >> 8) & 0xFF, n & 0xFF,
        seq & 0xFF, VENDOR_ID & 0xFF, feature & 0xFF, cmd & 0xFF,
    ])
    return header + payload


def decode_packet(data):
    """解析 FF 封装或裸 PDU。裸 PDU 形如 00 1D <feature> <cmd> <payload...>。"""
    if not data:
        return None
    data = bytes(data)
    if len(data) >= 8 and data[0] == 0xFF and data[1] == 0x04:
        length = (data[2] << 8) | data[3]
        if len(data) < 8 + length:
            return None
        if data[5] != 0x1D:
            return None
        f, c = data[6], data[7]
        payload = list(data[8:8 + length])
    elif len(data) >= 4 and data[0] == 0x00 and data[1] == 0x1D:
        f, c = data[2], data[3]
        payload = list(data[4:])
    else:
        return None

    base_feature = f & 0xFE
    if c & 0x80:
        frame_type = "error" if (f & 0x01) else "notification"
    else:
        frame_type = "response" if (f & 0x01) else "command"
    cmd_base = c & 0x7F

    result = {
        "feature": f,
        "feature_base": base_feature,
        "feature_id": base_feature >> 1,
        "feature_name": feature_name(f),
        "cmd": c,
        "cmd_base": cmd_base,
        "cmd_hex": f"0x{c:02X}",
        "frame_type": frame_type,
        "payload": payload,
        "payload_hex": _hex_bytes(payload),
        "ascii": _ascii(payload),
        "raw": data.hex(" ").upper(),
    }
    if frame_type != "error" and base_feature == 0x1A:
        battery = parse_battery(payload)
        if battery:
            result["battery"] = battery
    result["summary"] = _summarize(result)
    return result


class MockSerial:
    """DEMO 假设备：在内存里模拟布丁的 GAIA 应答，不需要真实蓝牙。

    noack=True 时 SET 命令不回应，用来复现真机「SET 无 ACK、写后重读」的路径。
    latency 模拟设备处理延迟（秒）。
    """

    def __init__(self, noack=False, latency=0.0):
        self.is_open = True
        self.port = "MOCK"
        self.noack = bool(noack)
        self.latency = max(0.0, float(latency))
        self._rx = bytearray()
        self._pending = bytearray()      # 上次 write 遗留的半帧

        self._anc = 0x01                 # 自适应
        self._anc_cfg = [1, 1, 1, 1, 1]  # STATE, ON, OFF, TRANSPARENT, ORDER
        self._gain = 0x01                # 中
        self._led = 1
        self._battery = {1: 82, 2: 79, 3: 95}
        self._touch_default = bytearray([0x77, 0x77, 0x77, 0x77, 0x77])
        self._touch = bytearray([0x11, 0x23, 0x66, 0x77, 0x00])
        self._tone = [1, 60, 1]          # enabled, volume, group(index)
        self._lc3 = 1
        self._ldac = 0
        self._lhdc = 0
        self._onebringtwo = 0
        self._onebringtwo_timeout = 5
        self._fw = b"3.5.2-demo"
        self._serial = b"DEMO-DEVICE-SN"     # 0x00 cmd 0x03
        self._serial_l = b"DEMO-SN-L-0001"   # 0x00 cmd 0x14
        self._serial_r = b"DEMO-SN-R-0001"   # 0x00 cmd 0x15
        self._peer = b"\x52\x3E\x85\x63\x9C\xB0"
        self._notify_features = set()

    # ---- pyserial 兼容接口 ----
    def reset_input_buffer(self):
        self._rx.clear()
        self._pending.clear()

    def flush(self):
        pass

    @property
    def in_waiting(self):
        return len(self._rx)

    def read(self, n):
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def close(self):
        self.is_open = False
        self._pending.clear()

    def write(self, data):
        raw = bytes(data)
        # 拼接上次遗留的半帧，支持一个帧被拆成多次写入。
        data = bytes(self._pending) + raw
        self._pending = bytearray()
        replies = bytearray()
        try:
            rest = data
            while len(rest) >= 8:
                length = (rest[2] << 8) | rest[3]
                total = 8 + length
                if len(rest) < total:
                    break
                replies += self._handle(rest[:total])
                rest = rest[total:]
            if rest:
                self._pending = bytearray(rest)
        except Exception:
            replies = bytearray()
            self._pending = bytearray()
        if self.latency:
            time.sleep(self.latency)
        self._rx += replies
        return len(raw)

    # ---- 帧构造 ----
    @staticmethod
    def _reply(feature, cmd, payload=b""):
        payload = bytes(payload)
        n = len(payload)
        return bytes([
            0xFF, 0x04, (n >> 8) & 0xFF, n & 0xFF, 0x00, 0x1D,
            (feature | 0x01) & 0xFF, cmd & 0x7F,
        ]) + payload

    @staticmethod
    def _error(feature, cmd, code):
        return bytes([
            0xFF, 0x04, 0x00, 0x01, 0x00, 0x1D,
            (feature | 0x01) & 0xFF, (cmd & 0x7F) | 0x80, code & 0xFF,
        ])

    def _ack(self, feature, cmd, payload=b""):
        if self.noack:
            return b""
        return self._reply(feature, cmd, payload)

    # ---- 命令处理 ----
    def _handle(self, pkt):
        if len(pkt) < 8 or pkt[0] != 0xFF or pkt[1] != 0x04:
            return b""
        if pkt[5] != 0x1D:
            return b""
        length = (pkt[2] << 8) | pkt[3]
        if len(pkt) < 8 + length:
            return b""
        f = pkt[6] & 0xFF
        raw_cmd = pkt[7] & 0xFF
        if raw_cmd & 0x80 or f & 0x01:
            return b""                    # 不是命令帧
        c = raw_cmd & 0x7F
        pl = list(pkt[8:8 + length])

        if f == 0x40:                     # ANC V2
            if c == 0x03:
                return self._reply(f, c, bytes([self._anc]))
            if c == 0x04:
                if len(pl) != 1 or pl[0] > 4:
                    return self._error(f, c, 5)
                self._anc = pl[0]
                return self._ack(f, c, bytes([self._anc]))
            if c == 0x29:
                return self._reply(f, c, bytes(self._anc_cfg))
            if c == 0x2A:
                if len(pl) != 5:
                    return self._error(f, c, 5)
                self._anc_cfg = list(pl)
                return self._ack(f, c, bytes(self._anc_cfg))
            return self._error(f, c, 1)

        if f == 0x1A:                     # 电池
            if c == 0x00:
                return self._reply(f, c, bytes([1, 2, 3]))
            if c == 0x01:
                ids = pl if pl else [1, 2, 3]
                out = bytearray()
                for bid in ids:
                    if bid in self._battery:
                        out += bytes([bid, self._battery[bid]])
                    else:
                        out += bytes([bid, 0xFF])
                return self._reply(f, c, out)
            return self._error(f, c, 1)

        if f == 0x1E:                     # 增益
            if c == 0x01:
                return self._reply(f, c, bytes([self._gain]))
            if c == 0x02:
                if len(pl) != 1 or pl[0] not in GAIN_LEVELS:
                    return self._error(f, c, 5)
                self._gain = pl[0]
                return self._ack(f, c, bytes([self._gain]))
            return self._error(f, c, 1)

        if f == 0x26:                     # 指示灯
            if c == 0x01:
                return self._reply(f, c, bytes([self._led]))
            if c == 0x02:
                if len(pl) != 1 or pl[0] not in (0, 1):
                    return self._error(f, c, 5)
                self._led = pl[0]
                return self._ack(f, c, bytes([self._led]))
            return self._error(f, c, 1)

        if f == 0x1C:                     # 提示音
            if c == 0x01:
                return self._reply(f, c, bytes(self._tone))
            if c == 0x02:
                if len(pl) != 3 or pl[0] not in (0, 1) or not 0 <= pl[1] <= 100:
                    return self._error(f, c, 5)
                self._tone = [pl[0], pl[1], pl[2] & 0xFF]
                return self._ack(f, c, bytes(self._tone))
            return self._error(f, c, 1)

        if f == 0x2C:                     # 手势 TOUCHV2
            if c == 0x01:
                return self._reply(f, c, bytes(self._touch_default))
            if c == 0x02:
                return self._reply(f, c, bytes(self._touch))
            if c == 0x03:
                if len(pl) != 5:
                    return self._error(f, c, 5)
                self._touch = bytearray(pl)
                return self._ack(f, c, bytes(self._touch))
            return self._error(f, c, 1)

        if f == 0x20:                     # 编解码
            if c == 0x01:
                return self._reply(f, c, bytes([self._lc3]))
            if c == 0x02:
                return self._reply(f, c, bytes([self._ldac]))
            if c == 0x05:
                return self._reply(f, c, bytes([self._lhdc]))
            if c in (0x03, 0x04, 0x06):
                if len(pl) != 1 or pl[0] not in (0, 1):
                    return self._error(f, c, 5)
                if c == 0x03:
                    self._lc3 = pl[0]
                elif c == 0x04:
                    self._ldac = pl[0]
                else:
                    self._lhdc = pl[0]
                return self._ack(f, c, bytes([pl[0]]))
            return self._error(f, c, 1)

        if f == 0x28:                     # 一拖二
            if c == 0x01:
                return self._reply(f, c, bytes([self._onebringtwo]))
            if c == 0x03:
                return self._reply(f, c, bytes([self._onebringtwo_timeout]))
            if c == 0x05:
                return self._reply(f, c, b"\x00" + self._peer + b"DEMO-PC")
            if c == 0x06:
                return self._reply(f, c, b"")
            if c == 0x02:
                if len(pl) != 1 or pl[0] not in (0, 1):
                    return self._error(f, c, 5)
                self._onebringtwo = pl[0]
                return self._ack(f, c, bytes([self._onebringtwo]))
            if c == 0x04:
                if len(pl) != 1:
                    return self._error(f, c, 5)
                self._onebringtwo_timeout = pl[0]
                return self._ack(f, c, bytes([self._onebringtwo_timeout]))
            if c == 0x07:
                return self._ack(f, c, b"")
            return self._error(f, c, 1)

        if f == 0x00:                     # 基础域（APK: V3BasicPlugin）
            if c == 0x00:
                return self._reply(f, c, bytes([0x03]))      # GAIA 版本
            if c == 0x01:
                # [more][featureId][version]... 成对列表
                return self._reply(f, c, bytes([
                    0x00,
                    0x00, 0x01, 0x05, 0x01, 0x0D, 0x01, 0x0E, 0x01, 0x0F, 0x01,
                    0x10, 0x01, 0x13, 0x01, 0x14, 0x01, 0x16, 0x01, 0x20, 0x01,
                ]))
            if c == 0x02:
                return self._reply(f, c, b"")                # 下一页特性
            if c == 0x03:
                return self._reply(f, c, self._serial)       # 设备序列号
            if c == 0x05:
                return self._reply(f, c, self._fw)           # 应用/固件版本
            if c == 0x07:
                if pl:
                    self._notify_features.add(pl[0])
                return self._ack(f, c, b"")                  # 注册通知
            if c == 0x08:
                if pl:
                    self._notify_features.discard(pl[0])
                return self._ack(f, c, b"")                  # 取消通知
            if c == 0x0C:
                if len(pl) != 1 or not 1 <= pl[0] <= 7:
                    return self._error(f, c, 5)
                return self._reply(f, c, bytes([pl[0], 0x00]))  # 读取传输信息（占位）
            if c == 0x0D:
                return self._ack(f, c, bytes(pl))            # 设置传输参数（写）
            if c == 0x14:
                return self._reply(f, c, self._serial_l)     # 左耳序列号
            if c == 0x15:
                return self._reply(f, c, self._serial_r)     # 右耳序列号
            return self._reply(f, c, b"")

        if f == 0x0A:                     # EQ（面板未使用，保持可查询）
            if c == 0x03:
                return self._reply(f, c, bytes([0x06]))
            if c == 0x05:
                return self._reply(f, c, bytes([pl[0] if pl else 0, 0x06, 0x00, 0x00]))
            if c == 0x06:
                return self._ack(f, c, bytes(pl))
            return self._reply(f, c, b"")

        return self._error(f, c, 0)


# ---------------------------------------------------------------------------
# 串口收发
# ---------------------------------------------------------------------------
ser = None
ser_lock = threading.Lock()
device_online = False


def _parse_hex(text):
    raw = "".join(str(text).split())
    if not raw:
        return b""
    if len(raw) % 2 != 0:
        raise ValueError("payload 必须是偶数长度的十六进制")
    try:
        return bytes.fromhex(raw)
    except ValueError:
        raise ValueError("payload 含非法十六进制字符")


def _error_result(tx, message):
    return {
        "tx": decode_packet(tx),
        "tx_raw": tx.hex(" ").upper(),
        "rx_raw": None,
        "decoded": None,
        "error": message,
    }


_rx_carry = bytearray()


def _take_frame(buf):
    """从缓冲区头部取一个 FF 04 帧；返回 (frame, rest) 或 (None, buf)。"""
    if len(buf) < 8 or not buf.startswith(b"\xFF\x04"):
        return None, buf
    body_len = (buf[2] << 8) | buf[3]
    total = 8 + body_len
    if len(buf) < total:
        return None, buf
    return bytes(buf[:total]), buf[total:]


def _recv_frame(timeout):
    """读取一个完整帧。优先按 FF 04 长度字段判断，裸 PDU 按 50ms 静默判断。

    一次 read 可能带回多帧：只返回第一帧，剩余字节留在 _rx_carry，
    供 send_cmd 继续匹配，避免把同一批到达的真实响应丢掉。
    """
    if not ser or not ser.is_open:
        return b""
    deadline = time.time() + max(0.05, timeout)
    buf = bytearray(_rx_carry)
    _rx_carry.clear()
    frame, rest = _take_frame(buf)
    if frame is not None:
        _rx_carry.extend(rest)
        return frame
    last_rx = 0.0
    while time.time() < deadline:
        try:
            waiting = ser.in_waiting
        except Exception:
            waiting = 0
        if waiting:
            try:
                chunk = ser.read(waiting)
            except Exception:
                break
            if chunk:
                buf.extend(chunk)
                last_rx = time.time()
                # 丢掉帧头前的杂字节，但保留可能只到了一半的 FF / 00 1D 头。
                if not (buf.startswith(b"\xFF\x04") or buf.startswith(b"\x00\x1D")) and len(buf) >= 2:
                    candidates = [i for i in (buf.find(b"\xFF\x04"), buf.find(b"\x00\x1D")) if i >= 0]
                    if candidates:
                        del buf[:min(candidates)]
                    elif buf[-1:] in (b"\xFF", b"\x00"):
                        buf = buf[-1:]
                    else:
                        buf.clear()
                if buf.startswith(b"\xFF\x04"):
                    frame, rest = _take_frame(buf)
                    if frame is not None:
                        _rx_carry.extend(rest)
                        return frame
                elif buf.startswith(b"\x00\x1D") and len(buf) >= 4:
                    if time.time() - last_rx >= 0.05:
                        return bytes(buf)
        else:
            if buf.startswith(b"\x00\x1D") and len(buf) >= 4 and time.time() - last_rx >= 0.05:
                return bytes(buf)
            time.sleep(0.005)
    if buf:
        _rx_carry.extend(buf)
    return b""


def send_cmd(feature, cmd, payload_hex="", timeout=1.0, retries=1):
    payload = _parse_hex(payload_hex)
    tx = build_tx(feature, cmd, payload)
    if ser is None or not ser.is_open:
        return _error_result(tx, "串口未连接")

    expected_feature = (feature | 0x01) & 0xFF
    expected_cmd = cmd & 0x7F
    last_rx = b""
    last_decoded = None
    matched = False
    for attempt in range(retries + 1):
        with ser_lock:
            if ser is None or not ser.is_open:
                return _error_result(tx, "串口未连接")
            try:
                ser.reset_input_buffer()
                _rx_carry.clear()
                ser.write(tx)
                ser.flush()
            except Exception as exc:
                return _error_result(tx, f"串口写入失败: {exc}")
            deadline = time.time() + max(0.05, timeout)
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                frame = _recv_frame(remaining)
                if not frame:
                    break
                last_rx = frame
                last_decoded = decode_packet(frame)
                if (last_decoded
                        and last_decoded["feature"] == expected_feature
                        and last_decoded["cmd_base"] == expected_cmd
                        and last_decoded["frame_type"] in ("response", "error")):
                    matched = True
                    break
                # 通知或其他命令的响应：继续等到 deadline，找真正的响应。
        if matched:
            break
        if last_rx:
            break
        if attempt < retries:
            time.sleep(0.08)

    if not last_rx:
        return _error_result(tx, "无响应")
    result = {
        "tx": decode_packet(tx),
        "tx_raw": tx.hex(" ").upper(),
        "rx_raw": last_rx.hex(" ").upper(),
        "decoded": last_decoded,
        "matched": matched,
    }
    if last_decoded is None:
        result["warning"] = "收到无法解析的帧"
    elif not matched:
        result["warning"] = "未收到匹配的响应帧"
    return result


def _payload_of(result):
    d = result.get("decoded") if result else None
    if not d or d.get("frame_type") in ("error", "notification"):
        return None
    if result.get("matched") is False:
        return None
    return d.get("payload")


def _error_of(result):
    d = result.get("decoded") if result else None
    if d and d.get("frame_type") == "error":
        code = d["payload"][0] if d.get("payload") else None
        name = ERROR_NAMES.get(code, f"错误码 {code}")
        return name + (f" ({code})" if code is not None else "")
    return None


def _mark_online(steps):
    global device_online
    if any(step.get("decoded") is not None for step in steps):
        device_online = True


def _fmt_value(value):
    if isinstance(value, (list, tuple, bytearray)):
        return _hex_bytes(value)
    if isinstance(value, bool):
        return "01" if value else "00"
    if isinstance(value, int):
        return f"{value:02X}"
    return str(value)


def _finish(action, steps, ok, message, **extra):
    out = {"action": action, "ok": bool(ok), "message": message, "steps": steps}
    out.update(extra)
    _mark_online(steps)
    return out


def _set_verify(action, set_spec, read_spec, expected, label_set, label_read, extract):
    """写一条 SET，等待片刻后重读校验。SET 是否回 ACK 不影响校验结论。"""
    set_feature, set_cmd, set_payload = set_spec
    steps = []
    set_result = send_cmd(set_feature, set_cmd, set_payload, timeout=0.5, retries=0)
    set_result["label"] = label_set
    set_result["no_reply_ok"] = True
    steps.append(set_result)
    set_error = _error_of(set_result)
    set_failure = set_result.get("error")

    time.sleep(0.2)
    read_result = send_cmd(read_spec[0], read_spec[1], "", timeout=1.0, retries=1)
    read_result["label"] = label_read
    steps.append(read_result)

    raw = _payload_of(read_result)
    after = extract(raw) if raw is not None else None
    ok = after == expected
    if ok:
        message = "写入后重读一致"
    elif set_failure and set_failure != "无响应":
        message = f"写入失败：{set_failure}"
    elif set_error:
        message = f"设备拒绝：{set_error}"
    elif after is None and read_result.get("error"):
        message = f"重读失败：{read_result['error']}"
    elif after is None:
        message = "写入已发送，但重读无响应"
    else:
        message = f"重读值 {_fmt_value(after)} 与目标 {_fmt_value(expected)} 不一致"

    extra = {"requested": expected, "after": after}
    if set_error:
        extra["set_error"] = set_error
    return _finish(action, steps, ok, message, **extra)


# ---------------------------------------------------------------------------
# 状态读取
# ---------------------------------------------------------------------------
STATE_READS = [
    ("battery", 0x1A, 0x01, "010203", 1.0, 1, "读取电量"),
    ("anc", 0x40, 0x03, "", 1.0, 1, "读取降噪模式"),
    ("anc_config", 0x40, 0x29, "", 0.6, 0, "读取降噪切换配置"),
    ("gain", 0x1E, 0x01, "", 0.8, 1, "读取增益"),
    ("led", 0x26, 0x01, "", 0.8, 1, "读取指示灯"),
    ("touch", 0x2C, 0x02, "", 1.0, 1, "读取手势"),
    ("tone", 0x1C, 0x01, "", 0.8, 1, "读取提示音"),
    ("lhdc", 0x20, 0x05, "", 0.6, 0, "读取 LHDC"),
    ("lc3", 0x20, 0x01, "", 0.6, 0, "读取 LC3"),
    ("ldac", 0x20, 0x02, "", 0.6, 0, "读取 LDAC"),
    ("onebringtwo", 0x28, 0x01, "", 0.6, 0, "读取一拖二"),
    ("onebringtwo_timeout", 0x28, 0x03, "", 0.6, 0, "读取一拖二超时"),
]


def read_state():
    global device_online
    steps = []
    by_key = {}

    # 先用固件查询探活：没有响应就不再逐项等超时，避免离线时页面卡十几秒。
    probe = send_cmd(0x00, 0x05, "", timeout=1.2, retries=1)
    probe["label"] = "读取固件版本"
    steps.append(probe)
    by_key["firmware"] = probe
    if probe.get("decoded") is None:
        device_online = False
        return {
            "online": False,
            "demo": isinstance(ser, MockSerial),
            "port": getattr(ser, "port", None),
            "state": {},
            "steps": steps,
        }

    for key, feature, cmd, payload, timeout, retries, label in STATE_READS:
        result = send_cmd(feature, cmd, payload, timeout=timeout, retries=retries)
        result["label"] = label
        steps.append(result)
        by_key[key] = result

    state = {}

    def payload(key):
        return _payload_of(by_key.get(key))

    res = by_key.get("firmware")
    if res and res.get("decoded") and res["decoded"].get("frame_type") == "response":
        if res["decoded"].get("ascii"):
            state["firmware"] = res["decoded"]["ascii"]

    p = payload("battery")
    if p is not None:
        battery_frame = by_key["battery"].get("decoded")
        battery = battery_frame.get("battery") if battery_frame else None
        if battery:
            state["battery"] = battery

    p = payload("anc")
    if p:
        state["anc"] = p[0]

    p = payload("anc_config")
    if p is not None and len(p) >= 5:
        state["anc_config"] = p[:5]

    p = payload("gain")
    if p:
        state["gain"] = p[0]

    p = payload("led")
    if p:
        state["led"] = p[0] & 0x01

    p = payload("touch")
    if p is not None and len(p) >= 5:
        state["touch"] = p[:5]

    p = payload("tone")
    if p is not None and len(p) >= 3:
        state["tone"] = [p[0] & 0x01, p[1] & 0xFF, p[2] & 0xFF]

    for key in ("lhdc", "lc3", "ldac"):
        p = payload(key)
        if p:
            state[key] = p[0] & 0x01

    p = payload("onebringtwo")
    if p:
        state["onebringtwo"] = p[0] & 0x01

    p = payload("onebringtwo_timeout")
    if p:
        state["onebringtwo_timeout"] = p[0]

    online = any(step.get("decoded") is not None for step in steps)
    device_online = online
    return {
        "online": online,
        "demo": isinstance(ser, MockSerial),
        "port": getattr(ser, "port", None),
        "state": state,
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# 写入接口
# ---------------------------------------------------------------------------
def set_anc(mode):
    if mode not in ANC_MODES:
        raise ValueError("降噪模式必须是 0..4")
    return _set_verify(
        "设置降噪",
        (0x40, 0x04, f"{mode:02X}"),
        (0x40, 0x03),
        mode,
        "设置 ANC 模式",
        "重读 ANC 模式",
        lambda p: p[0] if p else None,
    )


def set_gain(level):
    if level not in GAIN_LEVELS:
        raise ValueError("增益必须是 0..2")
    return _set_verify(
        "设置增益",
        (0x1E, 0x02, f"{level:02X}"),
        (0x1E, 0x01),
        level,
        "设置增益",
        "重读增益",
        lambda p: p[0] if p else None,
    )


def set_led(on):
    if on not in (0, 1):
        raise ValueError("指示灯参数必须是 0/1")
    return _set_verify(
        "设置指示灯",
        (0x26, 0x02, f"{on:02X}"),
        (0x26, 0x01),
        on,
        "设置指示灯",
        "重读指示灯",
        lambda p: (p[0] & 0x01) if p else None,
    )


def set_lhdc(on):
    if on not in (0, 1):
        raise ValueError("LHDC 参数必须是 0/1")
    return _set_verify(
        "设置 LHDC",
        (0x20, 0x06, f"{on:02X}"),
        (0x20, 0x05),
        on,
        "设置 LHDC",
        "重读 LHDC",
        lambda p: (p[0] & 0x01) if p else None,
    )


def set_onebringtwo(on):
    if on not in (0, 1):
        raise ValueError("一拖二参数必须是 0/1")
    return _set_verify(
        "设置一拖二",
        (0x28, 0x02, f"{on:02X}"),
        (0x28, 0x01),
        on,
        "设置一拖二",
        "重读一拖二",
        lambda p: (p[0] & 0x01) if p else None,
    )


def set_touch(values):
    values = list(values)
    if len(values) != 5 or any(not 0 <= v <= 0xFF for v in values):
        raise ValueError("手势配置必须是 5 个 0..255 的字节")

    steps = []
    pre = send_cmd(0x2C, 0x02, "", timeout=1.0, retries=0)
    pre["label"] = "读取当前手势（写前）"
    steps.append(pre)
    before = _payload_of(pre)
    if before is not None and len(before) >= 5:
        before = before[:5]
    else:
        before = None

    # 8..15 没有官方动作文案，只允许保留设备原值，不允许新设。
    for i, value in enumerate(values):
        for shift in (4, 0):
            new_action = (value >> shift) & 0xF
            if new_action > 7:
                old_action = ((before[i] >> shift) & 0xF) if before else None
                if new_action != old_action:
                    raise ValueError("手势动作 id 仅支持 0..7；8..15 只能保留设备原值")

    write_result = send_cmd(0x2C, 0x03, bytes(values).hex(" "), timeout=0.5, retries=0)
    write_result["label"] = "写入手势（整包 5 字节）"
    write_result["no_reply_ok"] = True
    steps.append(write_result)
    set_error = _error_of(write_result)

    time.sleep(0.25)
    read_result = send_cmd(0x2C, 0x02, "", timeout=1.0, retries=1)
    read_result["label"] = "重读手势"
    steps.append(read_result)
    after_raw = _payload_of(read_result)
    after = after_raw[:5] if after_raw is not None and len(after_raw) >= 5 else None
    ok = after == values

    if ok:
        message = "写入后重读一致"
    elif set_error:
        message = f"设备拒绝：{set_error}"
    elif after is None:
        message = "写入已发送，但重读无响应"
    else:
        message = f"重读值 {_fmt_value(after)} 与写入值 {_fmt_value(values)} 不一致"

    extra = {"before": before, "requested": values, "after": after}
    if before is None:
        extra["warning"] = "写入前无法读取当前手势，已按提交的完整 5 字节写入"
    if set_error:
        extra["set_error"] = set_error
    return _finish("写入手势", steps, ok, message, **extra)


def set_tone(enabled=None, volume=None, index=None):
    steps = []
    pre = send_cmd(0x1C, 0x01, "", timeout=0.8, retries=0)
    pre["label"] = "读取当前提示音（写前）"
    steps.append(pre)
    before = _payload_of(pre)
    if before is not None and len(before) >= 3:
        before = [before[0] & 0x01, before[1] & 0xFF, before[2] & 0xFF]
    else:
        before = None
    if before is not None:
        base = before
    elif enabled is None or volume is None or index is None:
        raise ValueError("读取当前提示音失败，无法补齐未指定的字段；请同时提供 enabled、volume、index")
    else:
        base = [enabled, volume, index]

    enabled = base[0] if enabled is None else enabled
    volume = base[1] if volume is None else volume
    index = base[2] if index is None else index
    if enabled not in (0, 1):
        raise ValueError("提示音开关必须是 0/1")
    if not 0 <= volume <= 100:
        raise ValueError("提示音音量必须是 0..100")
    if not 0 <= index <= 255:
        raise ValueError("提示音组号必须是 0..255")

    payload = bytes([enabled, volume, index])
    write_result = send_cmd(0x1C, 0x02, payload.hex(" "), timeout=0.5, retries=0)
    write_result["label"] = "写入提示音（3 字节）"
    write_result["no_reply_ok"] = True
    steps.append(write_result)
    set_error = _error_of(write_result)

    time.sleep(0.2)
    read_result = send_cmd(0x1C, 0x01, "", timeout=1.0, retries=1)
    read_result["label"] = "重读提示音"
    steps.append(read_result)
    after_raw = _payload_of(read_result)
    after = ([after_raw[0] & 0x01, after_raw[1] & 0xFF, after_raw[2] & 0xFF]
             if after_raw is not None and len(after_raw) >= 3 else None)
    requested = [enabled, volume, index]
    ok = after == requested

    if ok:
        message = "写入后重读一致"
    elif set_error:
        message = f"设备拒绝：{set_error}"
    elif after is None:
        message = "写入已发送，但重读无响应"
    else:
        message = f"重读值 {_fmt_value(after)} 与写入值 {_fmt_value(requested)} 不一致"

    extra = {"before": before, "requested": requested, "after": after}
    if before is None:
        extra["warning"] = "写入前无法读取当前提示音，已按提交的完整 3 字节写入"
    if set_error:
        extra["set_error"] = set_error
    return _finish("设置提示音", steps, ok, message, **extra)


PRESETS = [
    {"name": "应用/固件版本", "feature": 0x00, "cmd": 0x05, "payload": ""},
    {"name": "支持的特性", "feature": 0x00, "cmd": 0x01, "payload": ""},
    {"name": "设备序列号", "feature": 0x00, "cmd": 0x03, "payload": ""},
    {"name": "左耳序列号", "feature": 0x00, "cmd": 0x14, "payload": ""},
    {"name": "右耳序列号", "feature": 0x00, "cmd": 0x15, "payload": ""},
    {"name": "传输信息", "feature": 0x00, "cmd": 0x0C, "payload": "02"},
    {"name": "ANC 状态", "feature": 0x40, "cmd": 0x03, "payload": ""},
    {"name": "ANC 切换配置", "feature": 0x40, "cmd": 0x29, "payload": ""},
    {"name": "手势当前", "feature": 0x2C, "cmd": 0x02, "payload": ""},
    {"name": "手势出厂默认", "feature": 0x2C, "cmd": 0x01, "payload": ""},
    {"name": "电量", "feature": 0x1A, "cmd": 0x01, "payload": "010203"},
    {"name": "LED 状态", "feature": 0x26, "cmd": 0x01, "payload": ""},
    {"name": "提示音", "feature": 0x1C, "cmd": 0x01, "payload": ""},
    {"name": "LHDC", "feature": 0x20, "cmd": 0x05, "payload": ""},
    {"name": "LC3", "feature": 0x20, "cmd": 0x01, "payload": ""},
    {"name": "LDAC", "feature": 0x20, "cmd": 0x02, "payload": ""},
    {"name": "一拖二", "feature": 0x28, "cmd": 0x01, "payload": ""},
    {"name": "一拖二设备", "feature": 0x28, "cmd": 0x05, "payload": ""},
]


# ---------------------------------------------------------------------------
# Web 页面
# ---------------------------------------------------------------------------
HTML = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MOONDROP Pudding 控制台</title>
<link rel="icon" href="data:,">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0c10;--surface:#12141a;--surface2:#181b24;--border:#1e2230;
  --text:#e2e8f0;--text2:#8b93a7;--dim:#4b5563;
  --anc:#4d8df5;--gain:#e68a2e;--bat:#22a06b;--tx:#e68a2e;--rx:#22a06b;
  --err:#ef4444;--warn:#d4a017;
}
body{font-family:system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);padding:14px;font-size:13px;line-height:1.5;min-height:100vh}
.app{max-width:1120px;margin:0 auto}
.hdr{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0 12px;border-bottom:1px solid var(--border);margin-bottom:12px;flex-wrap:wrap}
.hdr h1{font-size:14px;font-weight:650;letter-spacing:.2px}
.hdr .sub{font-size:10px;color:var(--dim);font-family:'SF Mono','Cascadia Code',Consolas,monospace;margin-top:2px}
.hdr-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.chip{font-size:9px;font-family:'SF Mono',Consolas,monospace;color:var(--text2);border:1px solid var(--border);background:var(--surface);border-radius:4px;padding:2px 7px;white-space:nowrap}
.chip.demo{color:var(--warn);border-color:rgba(212,160,23,.4);background:rgba(212,160,23,.08)}
.st{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text2);font-family:'SF Mono',Consolas,monospace}
.st-d{width:6px;height:6px;border-radius:50%;background:var(--dim);flex:none}
.st-d.ok{background:var(--rx);box-shadow:0 0 6px rgba(34,160,107,.45)}
.st-d.off{background:var(--err);opacity:.7}
.st-d.wait{background:var(--warn);animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.25}}

.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:10px}
.span2{grid-column:span 2}
@media(max-width:760px){.grid{grid-template-columns:1fr}.span2{grid-column:auto}}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:9px;overflow:hidden;min-width:0}
.panel.anc{border-top:2px solid var(--anc)}
.panel.gain{border-top:2px solid var(--gain)}
.panel.bat{border-top:2px solid var(--bat)}
.panel.led{border-top:2px solid #a78bfa}
.panel.extra{border-top:2px solid #38bdf8}
.panel.touch{border-top:2px solid #f472b6}
.panel.tone{border-top:2px solid #fbbf24}
.ph{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 12px 7px;font-size:10px;text-transform:uppercase;letter-spacing:1px;font-weight:650}
.panel.anc .ph{color:var(--anc)}.panel.gain .ph{color:var(--gain)}.panel.bat .ph{color:var(--bat)}
.panel.led .ph{color:#a78bfa}.panel.extra .ph{color:#38bdf8}.panel.touch .ph{color:#f472b6}.panel.tone .ph{color:#fbbf24}
.pv{font-family:'SF Mono',Consolas,monospace;font-size:11px;font-weight:600;color:var(--text);padding:1px 6px;border-radius:3px;background:var(--bg);text-transform:none;letter-spacing:0}
.ph-right{display:flex;align-items:center;gap:6px}
.pb{padding:0 12px 11px}

.seg-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(86px,1fr));gap:5px}
.seg{padding:7px 4px;border-radius:5px;border:1px solid var(--border);background:var(--bg);color:var(--text2);font-family:inherit;font-size:11px;font-weight:500;cursor:pointer;transition:all .12s;text-align:center;line-height:1.25}
.seg:hover{border-color:var(--dim);color:var(--text);background:var(--surface2)}
.seg .s{display:block;font-family:'SF Mono',Consolas,monospace;font-size:8px;color:var(--dim);margin-top:1px}
.panel.anc .seg.a{color:#9cc2ff;border-color:var(--anc);background:rgba(77,141,245,.12);box-shadow:0 0 8px rgba(77,141,245,.12)}
.panel.gain .seg.a{color:#f5b56d;border-color:var(--gain);background:rgba(230,138,46,.12);box-shadow:0 0 8px rgba(230,138,46,.12)}
.note{font-size:9px;color:var(--dim);margin-top:7px}
.note.warn{color:var(--warn)}

.bat-row{display:flex;align-items:center;gap:8px;padding:4px 0}
.bat-label{font-size:10px;color:var(--text2);min-width:3.2em}
.bat-bar{flex:1;height:7px;background:var(--bg);border-radius:4px;overflow:hidden;border:1px solid rgba(255,255,255,.02)}
.bat-fill{display:block;height:100%;width:0;border-radius:4px;background:var(--bat);transition:width .3s}
.bat-fill.low{background:var(--err)}
.bat-pct{font-size:10px;font-family:'SF Mono',Consolas,monospace;color:var(--text2);min-width:3.2em;text-align:right}
.bat-mini{font-size:9px;color:var(--dim);font-family:'SF Mono',Consolas,monospace;margin-top:6px}

.row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;border-top:1px solid var(--border)}
.row:first-child{border-top:0}
.row-main{min-width:0;flex:1}
.row-right{display:flex;align-items:center;gap:10px;flex:none}
.rl{font-size:11px;font-weight:600}
.rs{font-size:9px;color:var(--dim);margin-top:1px;font-family:'SF Mono',Consolas,monospace}
.kv{font:10px 'SF Mono',Consolas,monospace;color:var(--text2);min-width:1.8em;text-align:right}
.mini{font-size:10px;color:var(--dim);padding-top:7px;border-top:1px solid var(--border);margin-top:5px;font-family:'SF Mono',Consolas,monospace}
.mini b{color:var(--text2);font-weight:600}
.warnline{font-size:10px;color:var(--warn);margin-top:6px;min-height:0}

.btn{padding:5px 10px;border-radius:5px;border:1px solid var(--border);background:var(--bg);color:var(--text2);font-family:inherit;font-size:10px;font-weight:500;cursor:pointer;transition:.12s;white-space:nowrap}
.btn:hover{border-color:var(--dim);color:var(--text);background:var(--surface2)}
.btn.primary{border-color:var(--anc);background:rgba(77,141,245,.12);color:#9cc2ff}
.btn.primary:hover{background:rgba(77,141,245,.22)}
.btn.tiny{padding:4px 8px;font-size:9px}
.btn:disabled,.icon:disabled{opacity:.35;cursor:not-allowed}
.icon{width:22px;height:22px;line-height:20px;padding:0;text-align:center;border-radius:4px;border:1px solid var(--border);background:var(--bg);color:var(--text2);cursor:pointer;font-size:12px}
.icon:hover{border-color:var(--dim);color:var(--text);background:var(--surface2)}

.tg{position:relative;width:38px;height:21px;border-radius:11px;background:var(--bg);border:1px solid var(--border);cursor:pointer;transition:.15s;flex:none;padding:0}
.tg::after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;border-radius:50%;background:var(--text2);transition:.15s}
.tg.on{background:rgba(77,141,245,.25);border-color:var(--anc)}
.tg.on::after{left:19px;background:#8fb8ff}
.tg:disabled{opacity:.35;cursor:not-allowed}

.touch-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.touch-legend{font-size:9px;color:var(--dim);line-height:1.7}
.touch-legend b{color:var(--text2);font-weight:600}
table.touchtable{width:100%;border-collapse:collapse;table-layout:fixed}
.touchtable th{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);font-weight:650;text-align:left;padding:3px 5px}
.touchtable th:nth-child(1){width:118px}
.touchtable th:nth-child(2),.touchtable th:nth-child(3){width:auto}
.touchtable th:nth-child(4){width:38px;text-align:center}
.touchtable td{border-top:1px solid var(--border);padding:5px;vertical-align:middle}
.touchtable tr:first-child td{border-top:0}
.gl{font-size:11px;font-weight:600;white-space:nowrap}
.gd{font-size:8px;color:var(--dim);font-family:'SF Mono',Consolas,monospace}
select.sel{width:100%;padding:5px 6px;border-radius:5px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-family:inherit;font-size:11px}
select.sel:focus{outline:none;border-color:var(--anc)}
select.sel:disabled{opacity:.45}
.hexbyte{font-family:'SF Mono',Consolas,monospace;font-size:10px;color:var(--text2);text-align:center}
.touch-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:9px}
.hexline{font:10px 'SF Mono',Consolas,monospace;color:var(--text2);background:var(--bg);border:1px solid var(--border);border-radius:5px;padding:6px 8px;margin-top:7px;white-space:pre-wrap;word-break:break-all;line-height:1.7}
.hexline b{color:var(--text);font-weight:600}
.dirty{display:none;font-size:9px;color:var(--warn);border:1px solid rgba(212,160,23,.35);background:rgba(212,160,23,.06);border-radius:3px;padding:1px 5px;white-space:nowrap}

input[type=range]{appearance:none;-webkit-appearance:none;width:100%;height:4px;border-radius:2px;background:var(--border);outline:none;margin:7px 0}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:var(--anc);border:2px solid var(--surface);cursor:pointer}
input[type=range]::-moz-range-thumb{width:12px;height:12px;border-radius:50%;background:var(--anc);border:2px solid var(--surface);cursor:pointer}
.num{font-family:'SF Mono',Consolas,monospace;font-size:10px;color:var(--text);background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:3px 5px;width:64px}
.tone-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:8px}

.toolbar{display:flex;flex-direction:column;align-items:stretch;gap:8px;padding:9px 12px;background:var(--surface);border:1px solid var(--border);border-radius:9px;margin-bottom:10px}
.tool-group{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0;width:100%}
.tool-group.custom{justify-content:flex-start;border-top:1px solid var(--border);padding-top:8px}
.tool-group.custom .btn{margin-left:auto}
.tl{font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--dim);font-weight:650;white-space:nowrap}
.presets{display:flex;gap:4px;flex-wrap:wrap;min-width:0}
.cf{display:inline-flex;align-items:center;gap:3px;flex-shrink:0}
.cf label{font-size:8px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim)}
.cf input{width:42px;padding:4px 5px;border-radius:3px;border:1px solid var(--border);background:var(--bg);color:var(--text);font:10px 'SF Mono',Consolas,monospace}
.cf input.w{width:118px}
.cf.grow{flex:1;min-width:170px}
.cf.grow input{width:100%}

.log{background:var(--surface);border:1px solid var(--border);border-radius:9px;overflow:hidden}
.log-head{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid var(--border)}
.log-head h3{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);font-weight:650}
.log-head .right{display:flex;align-items:center;gap:8px;font-size:9px;color:var(--dim);font-family:'SF Mono',Consolas,monospace}
#log{max-height:360px;overflow-y:auto;padding:7px 9px}
.em{color:var(--dim);font-size:11px;padding:18px 0;text-align:center}
.le{background:var(--surface2);border-left:3px solid var(--border);border-radius:0 5px 5px 0;margin-bottom:6px;padding:5px 8px}
.le:last-child{margin-bottom:0}
.le.ok{border-left-color:var(--rx)}
.le.warn{border-left-color:var(--warn)}
.le.err{border-left-color:var(--err);background:rgba(239,68,68,.04)}
.le-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:2px;font-size:9px;color:var(--dim)}
.le-h .tag{font-weight:650;letter-spacing:.3px;color:var(--text2)}
.lr{display:flex;align-items:baseline;gap:7px;font-family:'SF Mono',Consolas,monospace;min-width:0}
.ld{font-size:9px;font-weight:700;letter-spacing:.4px;min-width:16px;flex:none}
.ld.tx{color:var(--tx)}.ld.rx{color:var(--rx)}
.lhx{font-size:10px;color:var(--text2);word-break:break-all;min-width:0}
.meta{font-size:8px;color:var(--dim);margin-left:auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46%}
.summary{font-size:10px;color:var(--text);margin:2px 0 0 23px;word-break:break-word}
.summary.errtext{color:#fca5a5}
.summary.dim{color:var(--dim)}
.summary.warn{color:var(--warn)}
button:disabled{opacity:.35;cursor:not-allowed}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%) translateY(8px);opacity:0;pointer-events:none;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:8px 14px;font-size:11px;transition:.18s;z-index:50;box-shadow:0 8px 30px rgba(0,0,0,.45);max-width:calc(100vw - 32px);text-align:center}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.toast.ok{border-color:rgba(34,160,107,.55);color:#b7f0d4}
.toast.err{border-color:rgba(239,68,68,.6);color:#fecaca}

dialog{border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:10px;padding:0;width:min(540px,calc(100vw - 28px));max-height:calc(100vh - 28px);overflow:auto;margin:auto;box-shadow:0 24px 70px rgba(0,0,0,.6)}
dialog:modal{inset:0;margin:auto}
dialog::backdrop{background:rgba(0,0,0,.62);backdrop-filter:blur(2px)}
.dlg-h{padding:12px 16px 10px;border-bottom:1px solid var(--border);font-size:12px;font-weight:650}
.dlg-b{padding:11px 16px}
.dlg-b p{font-size:10px;color:var(--text2);line-height:1.7;margin-bottom:8px}
.dlg-f{display:flex;justify-content:flex-end;gap:8px;padding:10px 16px;border-top:1px solid var(--border)}
.hexbox{font:11px 'SF Mono',Consolas,monospace;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:7px 9px;white-space:pre-wrap;word-break:break-all;line-height:1.8;margin-bottom:8px}
.hexbox b{color:var(--text)}
.diff{width:100%;border-collapse:collapse;font-size:10px}
.diff th{text-align:left;color:var(--dim);font-weight:600;font-size:9px;padding:3px 5px;border-bottom:1px solid var(--border)}
.diff td{padding:4px 5px;border-bottom:1px solid rgba(30,34,48,.65);vertical-align:top}
.diff tr:last-child td{border-bottom:0}
.diff tr.chg td{color:#f5b56d}
.diff .arrow{color:var(--dim);text-align:center;width:18px}
</style></head><body>
<div class="app">

<div class="hdr">
  <div>
    <h1>MOONDROP Pudding</h1>
    <div class="sub">MD-TWS-056 · GAIA V3 · SPP</div>
  </div>
  <div class="hdr-right">
    <span class="chip demo" id="demoChip" style="display:none">DEMO 假设备</span>
    <span class="chip" id="fwChip">固件 —</span>
    <div class="st"><span class="st-d" id="std"></span><span id="stt">连接中…</span></div>
    <button class="btn" id="refreshBtn">刷新全部</button>
  </div>
</div>

<div class="grid">

<div class="panel anc span2">
  <div class="ph"><span>降噪 · 五档</span><span class="pv" id="ancVal">—</span></div>
  <div class="pb">
    <div class="seg-grid" id="ancSeg">
      <button class="seg ctl" data-v="00"><span>关闭</span><span class="s">0x00</span></button>
      <button class="seg ctl" data-v="01"><span>自适应</span><span class="s">0x01</span></button>
      <button class="seg ctl" data-v="02"><span>通透</span><span class="s">0x02</span></button>
      <button class="seg ctl" data-v="03"><span>抗风噪</span><span class="s">0x03</span></button>
      <button class="seg ctl" data-v="04"><span>降噪</span><span class="s">0x04</span></button>
    </div>
    <div class="note" id="ancCfg" title="40 29 回包：STATE / ANC ON / ANC OFF / TRANSPARENT / ORDER，仅展示">切换配置 —</div>
  </div>
</div>

<div class="panel bat">
  <div class="ph"><span>电量</span><span class="ph-right"><span class="pv" id="batVal">—</span><button class="icon ctl" id="batRefresh" title="刷新电量">↻</button></span></div>
  <div class="pb">
    <div class="bat-row"><span class="bat-label">左耳</span><span class="bat-bar"><span class="bat-fill" id="batL"></span></span><span class="bat-pct" id="batLT">--</span></div>
    <div class="bat-row"><span class="bat-label">右耳</span><span class="bat-bar"><span class="bat-fill" id="batR"></span></span><span class="bat-pct" id="batRT">--</span></div>
    <div class="bat-row"><span class="bat-label">充电盒</span><span class="bat-bar"><span class="bat-fill" id="batC"></span></span><span class="bat-pct" id="batCT">--</span></div>
    <div class="bat-mini">1A 01 · 0xFF 表示不可用</div>
  </div>
</div>

<div class="panel gain">
  <div class="ph"><span>增益</span><span class="pv" id="gainVal">—</span></div>
  <div class="pb">
    <div class="seg-grid" id="gainSeg">
      <button class="seg ctl" data-v="00"><span>高</span><span class="s">0x00</span></button>
      <button class="seg ctl" data-v="01"><span>中</span><span class="s">0x01</span></button>
      <button class="seg ctl" data-v="02"><span>低</span><span class="s">0x02</span></button>
    </div>
    <div class="note">1E 02 · 写入后自动重读</div>
  </div>
</div>

<div class="panel led">
  <div class="ph"><span>指示灯</span><span class="pv" id="ledVal">—</span></div>
  <div class="pb">
    <div class="row">
      <div class="row-main"><div class="rl">耳机指示灯</div><div class="rs">26 01 读 / 26 02 写</div></div>
      <button class="tg ctl" id="ledSw" role="switch" aria-checked="false" aria-label="指示灯开关"></button>
    </div>
    <div class="note">开关状态以 26 01 重读为准</div>
  </div>
</div>

<div class="panel extra">
  <div class="ph"><span>编码与连接</span><span class="pv">扩展</span></div>
  <div class="pb">
    <div class="row">
      <div class="row-main"><div class="rl">LHDC</div><div class="rs">20 05 读 / 20 06 写</div></div>
      <div class="row-right"><span class="kv" id="lhdcVal">—</span><button class="tg ctl" id="lhdcSw" role="switch" aria-checked="false" aria-label="LHDC 开关"></button></div>
    </div>
    <div class="row">
      <div class="row-main"><div class="rl">一拖二</div><div class="rs">28 01 读 / 28 02 写</div></div>
      <div class="row-right"><span class="kv" id="obtVal">—</span><button class="tg ctl" id="obtSw" role="switch" aria-checked="false" aria-label="一拖二开关"></button></div>
    </div>
    <div class="mini">LC3 <b id="lc3Val">—</b> · LDAC <b id="ldacVal">—</b> · 超时 <b id="obtTimeoutVal">—</b></div>
    <div class="warnline" id="codecWarn"></div>
  </div>
</div>

<div class="panel touch span2">
  <div class="ph"><span>手势 · 5 行 × 左右耳</span><span class="pv" id="touchVal">—</span></div>
  <div class="pb">
    <div class="touch-top">
      <div class="touch-legend">
        2C 02 读当前 / 2C 01 读出厂默认 / 2C 03 写<br>
        每字节：<b>高 4 位 = 左耳</b>，<b>低 4 位 = 右耳</b>；写入必须整包 5 字节
      </div>
      <div class="touch-actions" style="margin-top:0">
        <span class="dirty" id="touchDirtyTag">有未应用修改</span>
        <button class="btn ctl" id="touchReload">重新读取</button>
        <button class="btn ctl" id="touchDefaults">载入出厂默认</button>
        <button class="btn primary ctl" id="touchApply">应用 5 字节…</button>
      </div>
    </div>
    <table class="touchtable" id="touchTable">
      <thead><tr><th>手势</th><th>左耳</th><th>右耳</th><th>字节</th></tr></thead>
      <tbody>
        <tr><td><div class="gl">单击</div><div class="gd">single</div></td><td><select class="sel ctl" id="tl0" data-idx="0"></select></td><td><select class="sel ctl" id="tr0" data-idx="0"></select></td><td class="hexbyte" id="tb0">00</td></tr>
        <tr><td><div class="gl">双击</div><div class="gd">double</div></td><td><select class="sel ctl" id="tl1" data-idx="1"></select></td><td><select class="sel ctl" id="tr1" data-idx="1"></select></td><td class="hexbyte" id="tb1">00</td></tr>
        <tr><td><div class="gl">三击</div><div class="gd">triple</div></td><td><select class="sel ctl" id="tl2" data-idx="2"></select></td><td><select class="sel ctl" id="tr2" data-idx="2"></select></td><td class="hexbyte" id="tb2">00</td></tr>
        <tr><td><div class="gl">长按 1 秒</div><div class="gd">ones</div></td><td><select class="sel ctl" id="tl3" data-idx="3"></select></td><td><select class="sel ctl" id="tr3" data-idx="3"></select></td><td class="hexbyte" id="tb3">00</td></tr>
        <tr><td><div class="gl">长按 3 秒</div><div class="gd">threes</div></td><td><select class="sel ctl" id="tl4" data-idx="4"></select></td><td><select class="sel ctl" id="tr4" data-idx="4"></select></td><td class="hexbyte" id="tb4">00</td></tr>
      </tbody>
    </table>
    <div class="hexline">当前　 <b id="touchHexBefore">—</b><br>待写入 <b id="touchHexAfter">—</b></div>
    <div class="note warn" id="touchWarn"></div>
  </div>
</div>

<div class="panel tone span2">
  <div class="ph"><span>提示音</span><span class="pv" id="toneVal">—</span></div>
  <div class="pb">
    <div class="row">
      <div class="row-main"><div class="rl">提示音开关</div><div class="rs">1C 01 读 / 1C 02 写 · 3 字节整包</div></div>
      <button class="tg ctl" id="toneSw" role="switch" aria-checked="false" aria-label="提示音开关"></button>
    </div>
    <div class="row">
      <div class="row-main"><div class="rl">音量 <span class="num" id="toneVolLabel" style="border:0;background:transparent;padding:0">60</span></div>
        <input type="range" id="toneVol" class="ctl" min="0" max="100" value="60"></div>
    </div>
    <div class="row">
      <div class="row-main"><div class="rl">提示音组号（0–255）</div><div class="rs">原始组号，范围 0-255 · 不同组对应不同提示音包，切换可能同步固件</div></div>
      <input type="number" id="toneIndex" class="num ctl" min="0" max="255" value="1" aria-label="提示音组号（0-255）" title="原始组号，范围 0-255">
    </div>
    <div class="tone-actions"><span class="dirty" id="toneDirtyTag">有未应用修改</span><button class="btn primary ctl" id="toneApply">应用提示音</button></div>
  </div>
</div>

</div>

<div class="toolbar">
  <div class="tool-group"><span class="tl">快捷读取</span><div class="presets" id="presets"></div></div>
  <div class="tool-group custom">
    <span class="tl">自定义</span>
    <div class="cf"><label>F</label><input id="fi" value="40" maxlength="2"></div>
    <div class="cf"><label>C</label><input id="ci" value="03" maxlength="2"></div>
    <div class="cf grow"><label>Payload</label><input id="pi" placeholder="十六进制，可空"></div>
    <button class="btn primary ctl" id="sendBtn">发送</button>
  </div>
</div>

<div class="log">
  <div class="log-head"><h3>通信日志</h3><div class="right"><span id="logCount">0 条</span><button class="btn tiny" id="logClear">清空</button></div></div>
  <div id="log"><div class="em">等待设备…</div></div>
</div>

</div>

<dialog id="touchDlg">
  <div class="dlg-h">确认写入手势配置</div>
  <div class="dlg-b">
    <p>将一次写入完整 5 字节。未改动的行保持当前值；写入后会自动重读校验。</p>
    <div class="hexbox">当前　 <b id="dlgHexBefore">—</b><br>写入　 <b id="dlgHexAfter">—</b></div>
    <table class="diff"><thead><tr><th>手势</th><th>当前</th><th></th><th>修改后</th></tr></thead><tbody id="dlgDiff"></tbody></table>
    <div class="note warn" id="dlgWarn"></div>
  </div>
  <div class="dlg-f">
    <button class="btn" id="dlgCancel">取消</button>
    <button class="btn primary" id="dlgConfirm">确认写入 5 字节</button>
  </div>
</dialog>

<div class="toast" id="toast"></div>

<script>
const $ = function(id){ return document.getElementById(id); };

const S = {
  online:false, demo:false, fw:null,
  anc:null, ancCfg:null, gain:null, led:null,
  battery:[], touch:null, touchDefault:null, touchDirty:false, touchPending:null,
  tone:null, tonePending:null, toneDirty:false,
  lhdc:null, lc3:null, ldac:null, obt:null, obtTimeout:null
};
let busy = false;
let busyCount = 0;
let logTotal = 0;
let pendingTouch = null;
let toastTimer = null;

const MODE_NAMES = {0:'关闭',1:'自适应',2:'通透',3:'抗风噪',4:'降噪'};
const GAIN_NAMES = {0:'高',1:'中',2:'低'};
const TOUCH_ACTIONS = {0:'无',1:'播放/暂停',2:'上一曲',3:'下一曲',4:'音量+',5:'音量-',6:'语音助手',7:'降噪切换'};
const TOUCH_ROWS = ['单击','双击','三击','长按 1 秒','长按 3 秒'];
const BAT_NAMES = {1:'左耳',2:'右耳',3:'充电盒'};

function esc(value){
  return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
  });
}
function hex2(value){ return (value & 0xFF).toString(16).toUpperCase().padStart(2,'0'); }
function hexBytes(values){ return (values || []).map(function(v){ return hex2(v); }).join(' '); }
function now(){ return new Date().toLocaleTimeString('zh-CN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}); }

function toast(message, ok){
  const el = $('toast');
  el.textContent = message;
  el.className = 'toast show ' + (ok ? 'ok' : 'err');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function(){ el.className = 'toast'; }, 2800);
}

function setStatus(text, cls){
  $('stt').textContent = text;
  $('std').className = 'st-d' + (cls ? ' ' + cls : '');
}

function syncControls(){
  const locked = busy || !S.online;
  document.querySelectorAll('.ctl').forEach(function(el){ el.disabled = locked; });
  document.querySelectorAll('#fi,#ci,#pi').forEach(function(el){ el.disabled = locked; });
  $('refreshBtn').disabled = busy;
  const toneKnown = !!(S.tone && S.tone.length >= 3);
  ['toneSw','toneVol','toneIndex','toneApply'].forEach(function(id){
    const el = $(id);
    if(el) el.disabled = locked || !toneKnown;
  });
  const dlgConfirm = $('dlgConfirm');
  if(dlgConfirm) dlgConfirm.disabled = busy;
  if(!locked){
    const haveTouch = !!(S.touch && S.touch.length === 5);
    $('touchApply').disabled = !haveTouch;
    if(!haveTouch){
      document.querySelectorAll('#touchTable select').forEach(function(el){ el.disabled = true; });
    }
  }
}

function setBusy(value){
  busyCount = Math.max(0, busyCount + (value ? 1 : -1));
  busy = busyCount > 0;
  if(busy){
    setStatus('通信中…','wait');
  }else if(S.online){
    setStatus(S.demo ? '已连接 · DEMO' : '已连接','ok');
  }else{
    setStatus('未连接','off');
  }
  syncControls();
}

function setOnline(ok, text){
  S.online = !!ok;
  setStatus(text || (S.online ? (S.demo ? '已连接 · DEMO' : '已连接') : '未连接'), S.online ? 'ok' : 'off');
  syncControls();
}

function appendLog(el){
  const box = $('log');
  const first = box.firstElementChild;
  if(first && first.classList.contains('em')) box.innerHTML = '';
  box.appendChild(el);
  while(box.children.length > 160) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
  logTotal += 1;
  $('logCount').textContent = logTotal + ' 条';
}

function frameMeta(d){
  if(!d) return '';
  return 'F:0x' + hex2(d.feature) + ' ' + (d.feature_name || '') + ' · C:0x' + hex2(d.cmd);
}

function logStep(step){
  if(!step) return;
  const d = step.decoded || null;
  const tx = step.tx || null;
  const txRaw = (tx && tx.raw) || step.tx_raw || '';
  const rxRaw = step.rx_raw || '';
  let cls = 'warn';
  if(rxRaw){
    cls = (d && d.frame_type === 'error') ? 'err' : 'ok';
  }else if(step.error && !step.no_reply_ok){
    cls = 'err';
  }

  let body = '';
  if(txRaw){
    body += '<div class="lr"><span class="ld tx">TX</span><span class="lhx">' + esc(txRaw) + '</span><span class="meta">' + esc(frameMeta(tx)) + '</span></div>';
  }
  if(rxRaw){
    body += '<div class="lr"><span class="ld rx">RX</span><span class="lhx">' + esc(rxRaw) + '</span><span class="meta">' + esc(frameMeta(d)) + '</span></div>';
    if(d && d.summary) body += '<div class="summary' + (d.frame_type === 'error' ? ' errtext' : '') + '">' + esc(d.summary) + '</div>';
    else if(!d) body += '<div class="summary warn">收到无法解析的帧</div>';
  }else if(step.no_reply_ok){
    body += '<div class="summary dim">无 ACK（正常，随后重读校验）</div>';
  }else if(step.error){
    body += '<div class="summary errtext">' + esc(step.error) + '</div>';
  }
  if(step.warning) body += '<div class="summary warn">' + esc(step.warning) + '</div>';

  const el = document.createElement('div');
  el.className = 'le ' + cls;
  el.innerHTML = '<div class="le-h"><span class="tag">' + esc(step.label || '交换') + '</span><span>' + now() + '</span></div>' + body;
  appendLog(el);
}

function addErrLog(label, message){
  const el = document.createElement('div');
  el.className = 'le err';
  el.innerHTML = '<div class="le-h"><span class="tag">' + esc(label) + '</span><span>' + now() + '</span></div>' +
    '<div class="summary errtext">' + esc(message) + '</div>';
  appendLog(el);
}

function syncTonePending(){
  if(S.tone && S.tone.length >= 3){
    S.tonePending = {enabled:S.tone[0] & 1, volume:S.tone[1] & 0xFF, index:S.tone[2] & 0xFF};
  }else{
    S.tonePending = {enabled:1, volume:60, index:1};
  }
  S.toneDirty = false;
}

function absorb(decoded){
  if(!decoded || decoded.frame_type !== 'response') return;
  const f = decoded.feature_base;
  const c = decoded.cmd_base;
  const p = decoded.payload || [];
  if(f === 0x00){
    if(c === 0x05 && decoded.ascii) S.fw = decoded.ascii;
  }else if(f === 0x1A){
    if(decoded.battery) S.battery = decoded.battery;
  }else if(f === 0x1E){
    if((c === 1 || c === 2) && p.length) S.gain = p[0];
  }else if(f === 0x26){
    if((c === 1 || c === 2) && p.length) S.led = p[0] & 1;
  }else if(f === 0x40){
    if((c === 3 || c === 4) && p.length) S.anc = p[0];
    else if(c === 0x29 && p.length >= 5) S.ancCfg = p.slice(0,5);
  }else if(f === 0x2C){
    if(p.length >= 5){
      if(c === 1) S.touchDefault = p.slice(0,5);
      else if(!S.touchDirty && (c === 2 || c === 3)) S.touch = p.slice(0,5);
    }
  }else if(f === 0x1C){
    if((c === 1 || c === 2) && p.length >= 3){
      S.tone = [p[0] & 1, p[1] & 0xFF, p[2] & 0xFF];
      if(!S.toneDirty) syncTonePending();
    }
  }else if(f === 0x20){
    if(c === 1 && p.length) S.lc3 = p[0] & 1;
    else if(c === 2 && p.length) S.ldac = p[0] & 1;
    else if(c === 5 && p.length) S.lhdc = p[0] & 1;
  }else if(f === 0x28){
    if(c === 1 && p.length) S.obt = p[0] & 1;
    else if(c === 3 && p.length) S.obtTimeout = p[0];
  }
}

function absorbSteps(steps){
  (steps || []).forEach(function(step){
    if(step && step.matched !== false) absorb(step.decoded);
  });
}

function applyState(st){
  if(!st) return;
  if(st.firmware) S.fw = st.firmware;
  if(Number.isInteger(st.anc)) S.anc = st.anc;
  if(Array.isArray(st.anc_config) && st.anc_config.length >= 5) S.ancCfg = st.anc_config.slice(0,5);
  if(Number.isInteger(st.gain)) S.gain = st.gain;
  if(Number.isInteger(st.led)) S.led = st.led;
  if(Array.isArray(st.battery)) S.battery = st.battery;
  if(Array.isArray(st.touch) && st.touch.length >= 5 && !S.touchDirty) S.touch = st.touch.slice(0,5);
  if(Array.isArray(st.tone) && st.tone.length >= 3){
    S.tone = st.tone.slice(0,3);
    if(!S.toneDirty) syncTonePending();
  }
  if(Number.isInteger(st.lhdc)) S.lhdc = st.lhdc;
  if(Number.isInteger(st.lc3)) S.lc3 = st.lc3;
  if(Number.isInteger(st.ldac)) S.ldac = st.ldac;
  if(Number.isInteger(st.onebringtwo)) S.obt = st.onebringtwo;
  if(Number.isInteger(st.onebringtwo_timeout)) S.obtTimeout = st.onebringtwo_timeout;
}

function renderAnc(){
  const m = S.anc;
  $('ancVal').textContent = (m == null) ? '—' : (MODE_NAMES[m] || ('未知 0x' + hex2(m))) + ' · 0x' + hex2(m);
  document.querySelectorAll('#ancSeg .seg').forEach(function(b){
    b.classList.toggle('a', m != null && parseInt(b.dataset.v,16) === m);
  });
  $('ancCfg').textContent = S.ancCfg ? ('切换配置 ' + S.ancCfg.map(hex2).join(' ')) : '切换配置 —';
}

function renderBattery(){
  const ids = {1:'L',2:'R',3:'C'};
  const summary = [];
  [1,2,3].forEach(function(id){
    const item = (S.battery || []).find(function(b){ return b.id === id; });
    const fill = $('bat' + ids[id]);
    const text = $('bat' + ids[id] + 'T');
    if(!item || item.level === 0xFF){
      fill.style.width = '0%';
      fill.classList.remove('low');
      text.textContent = item ? '不可用' : '--';
      summary.push(BAT_NAMES[id] + ' ' + (item ? '不可用' : '--'));
    }else{
      const level = Math.max(0, Math.min(100, item.level));
      fill.style.width = level + '%';
      fill.classList.toggle('low', level <= 20);
      text.textContent = level + '%';
      summary.push(BAT_NAMES[id] + ' ' + level + '%');
    }
  });
  $('batVal').textContent = S.battery && S.battery.length ? summary.join(' · ') : '—';
}

function renderGain(){
  const g = S.gain;
  $('gainVal').textContent = (g == null) ? '—' : (GAIN_NAMES[g] || ('未知 0x' + hex2(g))) + ' · 0x' + hex2(g);
  document.querySelectorAll('#gainSeg .seg').forEach(function(b){
    b.classList.toggle('a', g != null && parseInt(b.dataset.v,16) === g);
  });
}

function setSwitch(id, on){
  const el = $(id);
  el.classList.toggle('on', !!on);
  el.setAttribute('aria-checked', on ? 'true' : 'false');
}

function renderLed(){
  $('ledVal').textContent = S.led == null ? '—' : (S.led ? '开' : '关');
  setSwitch('ledSw', S.led === 1);
}

function renderExtras(){
  $('lhdcVal').textContent = S.lhdc == null ? '—' : (S.lhdc ? '开' : '关');
  $('obtVal').textContent = S.obt == null ? '—' : (S.obt ? '开' : '关');
  setSwitch('lhdcSw', S.lhdc === 1);
  setSwitch('obtSw', S.obt === 1);
  $('lc3Val').textContent = S.lc3 == null ? '—' : (S.lc3 ? '开' : '关');
  $('ldacVal').textContent = S.ldac == null ? '—' : (S.ldac ? '开' : '关');
  $('obtTimeoutVal').textContent = S.obtTimeout == null ? '—' : (S.obtTimeout + ' 秒');
  $('codecWarn').textContent = (S.lhdc === 1 && S.obt === 1) ? 'LHDC 与一拖二互斥，设备可能自动关闭其一' : '';
}

function actionOptions(selected, current){
  const parts = [];
  for(let v=0; v<8; v++){
    parts.push('<option value="' + v + '"' + (v === selected ? ' selected' : '') + '>' + esc(TOUCH_ACTIONS[v]) + ' (' + v + ')</option>');
  }
  if(selected > 7){
    parts.push('<option value="' + selected + '" selected>未定义 (' + selected + ')</option>');
  }else if(current != null && current > 7){
    parts.push('<option value="' + current + '" disabled>未定义 (' + current + ')</option>');
  }
  return parts.join('');
}

function touchPair(value){
  if(value == null) return '—';
  const left = TOUCH_ACTIONS[(value >> 4) & 0xF] || ('未定义' + ((value >> 4) & 0xF));
  const right = TOUCH_ACTIONS[value & 0xF] || ('未定义' + (value & 0xF));
  return 'L ' + left + ' / R ' + right;
}

function readTouchSelects(){
  const out = [];
  for(let i=0; i<5; i++){
    const left = parseInt($('tl' + i).value, 10) & 0xF;
    const right = parseInt($('tr' + i).value, 10) & 0xF;
    out.push(((left << 4) | right) & 0xFF);
  }
  return out;
}

function updateTouchBytes(pending){
  for(let i=0; i<5; i++) $('tb' + i).textContent = hex2(pending[i]);
}

function renderTouchPreview(){
  const before = S.touch;
  const pending = (S.touchDirty && S.touchPending) ? S.touchPending : (before || [0,0,0,0,0]);
  $('touchHexBefore').textContent = before ? hexBytes(before) : '未读取';
  $('touchHexAfter').textContent = hexBytes(pending);
  $('touchDirtyTag').style.display = S.touchDirty ? 'inline-block' : 'none';
  $('touchVal').textContent = before ? hexBytes(before) : '—';
  $('touchWarn').textContent = S.touch ? '' : '尚未读取到当前手势，先点击「重新读取」再编辑';
}

function renderTouch(){
  const current = S.touch;
  let pending;
  if(S.touchDirty && S.touchPending){
    pending = S.touchPending.slice();
  }else{
    pending = current ? current.slice() : [0,0,0,0,0];
  }
  for(let i=0; i<5; i++){
    const byte = pending[i] & 0xFF;
    const cur = current ? current[i] : null;
    $('tl' + i).innerHTML = actionOptions((byte >> 4) & 0xF, cur == null ? null : (cur >> 4) & 0xF);
    $('tr' + i).innerHTML = actionOptions(byte & 0xF, cur == null ? null : cur & 0xF);
    $('tb' + i).textContent = hex2(byte);
  }
  renderTouchPreview();
}

function renderTone(){
  if(!S.tonePending) syncTonePending();
  const p = S.tonePending;
  setSwitch('toneSw', !!p.enabled);
  $('toneVol').value = p.volume;
  $('toneVolLabel').textContent = p.volume;
  $('toneIndex').value = p.index;
  $('toneVal').textContent = S.tone ? ((S.tone[0] & 1 ? '开' : '关') + ' · 音量 ' + S.tone[1] + ' · 组号 ' + S.tone[2]) : '—';
  $('toneDirtyTag').style.display = S.toneDirty ? 'inline-block' : 'none';
}

function renderAll(){
  $('fwChip').textContent = '固件 ' + (S.fw || '—');
  $('demoChip').style.display = S.demo ? '' : 'none';
  renderAnc();
  renderBattery();
  renderGain();
  renderLed();
  renderExtras();
  renderTouch();
  renderTone();
  syncControls();
}

async function apiCall(path, label){
  setBusy(true);
  try{
    const response = await fetch(path, {cache:'no-store'});
    const text = await response.text();
    let data;
    try{
      data = JSON.parse(text);
    }catch(err){
      throw new Error('响应解析失败: ' + text.slice(0,120));
    }
    if(!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    if(Array.isArray(data.steps)){
      data.steps.forEach(logStep);
      absorbSteps(data.steps);
    }
    if(data.error && !data.steps) throw new Error(data.error);
    renderAll();
    return data;
  }catch(err){
    addErrLog(label || path, err.message || String(err));
    toast(err.message || String(err), false);
    throw err;
  }finally{
    setBusy(false);
  }
}

async function refreshAll(){
  try{
    const data = await apiCall('/api/state', '全量刷新');
    S.demo = !!data.demo;
    applyState(data.state || {});
    setOnline(!!data.online, data.online ? (S.demo ? '已连接 · DEMO' : '已连接') : '设备未响应');
    renderAll();
    if(data.online) toast('状态已刷新', true);
  }catch(err){
    setOnline(false, '设备未响应');
    renderAll();
  }
}

async function refreshBattery(silent){
  try{
    const data = await apiCall('/api/send?feature=26&cmd=1&payload=010203', '读取电量');
    const step = data.steps && data.steps[0];
    if(!step || step.error || !step.decoded){
      if(!silent) toast((step && step.error) || '电量读取失败', false);
      return;
    }
    renderAll();
    if(!silent) toast('电量已刷新', true);
  }catch(err){
    if(!silent) toast('电量读取失败', false);
  }
}

async function setAnc(mode){
  try{
    const data = await apiCall('/api/set/anc?mode=' + mode, '设置降噪');
    toast(data.message || (data.ok ? '已生效' : '写入未生效'), !!data.ok);
  }catch(err){}
}

async function setGain(level){
  try{
    const data = await apiCall('/api/set/gain?level=' + level, '设置增益');
    toast(data.message || (data.ok ? '已生效' : '写入未生效'), !!data.ok);
  }catch(err){}
}

async function toggleLed(){
  const target = (S.led === 1) ? 0 : 1;
  try{
    const data = await apiCall('/api/set/led?on=' + target, '设置指示灯');
    toast(data.message || (data.ok ? '已生效' : '写入未生效'), !!data.ok);
  }catch(err){}
}

async function toggleLhdc(){
  const target = (S.lhdc === 1) ? 0 : 1;
  try{
    const data = await apiCall('/api/set/lhdc?on=' + target, '设置 LHDC');
    toast(data.message || (data.ok ? '已生效' : '写入未生效'), !!data.ok);
  }catch(err){}
}

async function toggleOnebringtwo(){
  const target = (S.obt === 1) ? 0 : 1;
  try{
    const data = await apiCall('/api/set/multipoint?on=' + target, '设置一拖二');
    toast(data.message || (data.ok ? '已生效' : '写入未生效'), !!data.ok);
  }catch(err){}
}

function touchChanged(){
  S.touchPending = readTouchSelects();
  S.touchDirty = true;
  updateTouchBytes(S.touchPending);
  renderTouchPreview();
  syncControls();
}

async function reloadTouch(){
  if(busy) return;
  try{
    const data = await apiCall('/api/send?feature=44&cmd=2', '读取当前手势');
    const step = data.steps && data.steps[0];
    const d = step && step.decoded;
    const payload = d && d.payload;
    if(d && d.frame_type === 'response' && payload && payload.length >= 5){
      S.touch = payload.slice(0,5);
      S.touchDirty = false;
      S.touchPending = null;
      renderAll();
      toast('已读取当前手势', true);
    }else{
      throw new Error('没有拿到 5 字节手势配置');
    }
  }catch(err){ toast(err.message || '读取手势失败', false); }
}

async function loadTouchDefaults(){
  if(busy) return;
  try{
    const data = await apiCall('/api/send?feature=44&cmd=1', '读取手势出厂默认');
    const step = data.steps && data.steps[0];
    const d = step && step.decoded;
    const payload = d && d.payload;
    if(d && d.frame_type === 'response' && payload && payload.length >= 5){
      S.touchDefault = payload.slice(0,5);
      S.touchPending = payload.slice(0,5);
      S.touchDirty = true;
      renderAll();
      toast('已载入出厂默认：确认后再写入', true);
    }else{
      throw new Error('没有拿到出厂默认手势');
    }
  }catch(err){ toast(err.message || '读取出厂默认失败', false); }
}

function openTouchDialog(){
  const before = S.touch;
  const after = (S.touchDirty && S.touchPending) ? S.touchPending.slice() : (before ? before.slice() : readTouchSelects());
  pendingTouch = after.slice();
  $('dlgHexBefore').textContent = before ? hexBytes(before) : '未读取（将直接写入提交值）';
  $('dlgHexAfter').textContent = hexBytes(after);
  $('dlgWarn').textContent = before ? '' : '写入前无法读取当前手势；后端仍会尝试读取并校验。';
  $('dlgDiff').innerHTML = TOUCH_ROWS.map(function(name, i){
    const oldByte = before ? before[i] : null;
    const newByte = after[i];
    const changed = oldByte != null && oldByte !== newByte;
    return '<tr class="' + (changed ? 'chg' : '') + '"><td>' + esc(name) + '</td><td>' + esc(touchPair(oldByte)) +
      '</td><td class="arrow">' + (changed ? '→' : '=') + '</td><td>' + esc(touchPair(newByte)) + '</td></tr>';
  }).join('');
  $('touchDlg').showModal();
}

async function writeTouch(values){
  if(busy){ toast('通信中，请稍候', false); return; }
  if(!S.online){ toast('设备未连接', false); return; }
  try{
    const data = await apiCall('/api/set/touch?hex=' + values.map(hex2).join(''), '写入手势');
    if(Array.isArray(data.after) && data.after.length === 5) S.touch = data.after.slice(0,5);
    if(data.ok){
      S.touchDirty = false;
      S.touchPending = null;
    }else{
      S.touchDirty = true;
      S.touchPending = values.slice();
    }
    renderAll();
    toast(data.message || (data.ok ? '手势已写入' : '手势写入未生效'), !!data.ok);
  }catch(err){
    S.touchDirty = true;
    S.touchPending = values.slice();
    renderAll();
  }
}

async function applyTone(){
  if(!(S.tone && S.tone.length >= 3)){
    toast('尚未读取到提示音配置，请先刷新', false);
    return;
  }
  if(busy){ toast('通信中，请稍候', false); return; }
  if(!S.tonePending) syncTonePending();
  const pending = S.tonePending;
  const query = 'enabled=' + (pending.enabled ? 1 : 0) + '&volume=' + Math.round(pending.volume) + '&index=' + Math.round(pending.index);
  try{
    const data = await apiCall('/api/set/tone?' + query, '设置提示音');
    if(Array.isArray(data.after) && data.after.length >= 3) S.tone = data.after.slice(0,3);
    if(data.ok){
      S.toneDirty = false;
      syncTonePending();
    }else{
      S.toneDirty = true;
    }
    renderAll();
    toast(data.message || (data.ok ? '提示音已写入' : '提示音写入未生效'), !!data.ok);
  }catch(err){
    S.toneDirty = true;
    renderAll();
  }
}

async function sendCustom(){
  if(busy){ toast('通信中，请稍候', false); return; }
  if(!S.online){ toast('设备未连接', false); return; }
  const feature = parseInt($('fi').value, 16);
  const cmd = parseInt($('ci').value, 16);
  if(Number.isNaN(feature) || Number.isNaN(cmd)){
    toast('F / C 必须是十六进制，例如 40 / 03', false);
    return;
  }
  const payload = $('pi').value.trim();
  if(payload && !/^[0-9a-fA-F\s]+$/.test(payload)){
    toast('Payload 只能包含十六进制字符', false);
    return;
  }
  if(payload.replace(/\s/g,'').length % 2 !== 0){
    toast('Payload 长度必须是偶数', false);
    return;
  }
  try{
    const data = await apiCall('/api/send?feature=' + feature + '&cmd=' + cmd + '&payload=' + encodeURIComponent(payload), '自定义命令');
    const step = data.steps && data.steps[0];
    if(!step || step.error || !step.decoded){
      toast((step && step.error) || '未收到响应', false);
      return;
    }
    toast('命令已发送', true);
  }catch(err){}
}

async function sendPreset(preset){
  if(busy){ toast('通信中，请稍候', false); return; }
  if(!S.online){ toast('设备未连接', false); return; }
  try{
    const data = await apiCall('/api/send?feature=' + preset.feature + '&cmd=' + preset.cmd + '&payload=' + encodeURIComponent(preset.payload || ''), '快捷: ' + preset.name);
    const step = data.steps && data.steps[0];
    if(!step || step.error || !step.decoded){
      toast((step && step.error) || '未收到响应', false);
      return;
    }
    toast(preset.name + ' 已读取', true);
  }catch(err){}
}

function bindEvents(){
  $('refreshBtn').addEventListener('click', refreshAll);
  $('batRefresh').addEventListener('click', function(){ refreshBattery(false); });

  $('ancSeg').addEventListener('click', function(event){
    const button = event.target.closest('.seg');
    if(button) setAnc(parseInt(button.dataset.v, 16));
  });
  $('gainSeg').addEventListener('click', function(event){
    const button = event.target.closest('.seg');
    if(button) setGain(parseInt(button.dataset.v, 16));
  });
  $('ledSw').addEventListener('click', toggleLed);
  $('lhdcSw').addEventListener('click', toggleLhdc);
  $('obtSw').addEventListener('click', toggleOnebringtwo);

  for(let i=0; i<5; i++){
    $('tl' + i).addEventListener('change', touchChanged);
    $('tr' + i).addEventListener('change', touchChanged);
  }
  $('touchReload').addEventListener('click', reloadTouch);
  $('touchDefaults').addEventListener('click', loadTouchDefaults);
  $('touchApply').addEventListener('click', openTouchDialog);
  $('dlgCancel').addEventListener('click', function(){ $('touchDlg').close(); });
  $('dlgConfirm').addEventListener('click', function(){
    const values = pendingTouch ? pendingTouch.slice() : null;
    $('touchDlg').close();
    if(values) writeTouch(values);
  });
  $('touchDlg').addEventListener('close', function(){ pendingTouch = null; });

  $('toneSw').addEventListener('click', function(){
    if(!S.tonePending) syncTonePending();
    S.tonePending.enabled = S.tonePending.enabled ? 0 : 1;
    S.toneDirty = true;
    renderTone();
    syncControls();
  });
  $('toneVol').addEventListener('input', function(event){
    if(!S.tonePending) syncTonePending();
    S.tonePending.volume = parseInt(event.target.value, 10) || 0;
    S.toneDirty = true;
    $('toneVolLabel').textContent = S.tonePending.volume;
    $('toneDirtyTag').style.display = 'inline-block';
  });
  $('toneIndex').addEventListener('input', function(event){
    if(!S.tonePending) syncTonePending();
    const value = parseInt(event.target.value, 10);
    if(!Number.isNaN(value)){
      S.tonePending.index = Math.max(0, Math.min(255, value));
      S.toneDirty = true;
      $('toneDirtyTag').style.display = 'inline-block';
    }
  });
  $('toneApply').addEventListener('click', applyTone);

  $('sendBtn').addEventListener('click', sendCustom);
  ['fi','ci','pi'].forEach(function(id){
    $(id).addEventListener('keydown', function(event){
      if(event.key === 'Enter') sendCustom();
    });
  });
  $('logClear').addEventListener('click', function(){
    logTotal = 0;
    $('logCount').textContent = '0 条';
    $('log').innerHTML = '<div class="em">日志已清空</div>';
  });
}

async function loadPresets(){
  try{
    const response = await fetch('/api/presets', {cache:'no-store'});
    const list = await response.json();
    const box = $('presets');
    list.forEach(function(preset){
      const button = document.createElement('button');
      button.className = 'btn tiny ctl';
      button.textContent = preset.name;
      button.title = 'F:0x' + hex2(preset.feature) + ' C:0x' + hex2(preset.cmd) + (preset.payload ? ' payload ' + preset.payload : '');
      button.addEventListener('click', function(){ sendPreset(preset); });
      box.appendChild(button);
    });
    syncControls();
  }catch(err){
    addErrLog('加载快捷命令', err.message);
  }
}

document.querySelectorAll('.ctl').forEach(function(el){ el.disabled = true; });
$('touchWarn').textContent = '尚未读取到当前手势，先点击「重新读取」再编辑';
bindEvents();
loadPresets();
refreshAll();
setInterval(function(){ if(S.online && !busy) refreshBattery(true); }, 60000);
</script></body></html>"""


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------
def _req_int(q, key, lo, hi):
    raw = q.get(key, [None])[0]
    if raw is None:
        raise ValueError(f"缺少参数 {key}")
    try:
        value = int(str(raw), 0)
    except (TypeError, ValueError):
        raise ValueError(f"参数 {key} 必须是整数")
    if not lo <= value <= hi:
        raise ValueError(f"参数 {key} 超出范围 {lo}..{hi}")
    return value


def _opt_int(q, key, lo, hi):
    if key not in q:
        return None
    return _req_int(q, key, lo, hi)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._html(HTML)
            return
        is_write = parsed.path == "/api/send" or parsed.path.startswith("/api/set/")
        if is_write and not self._same_origin_request():
            self._json({"error": "拒绝跨源写入请求"}, 403)
            return
        try:
            query = parse_qs(parsed.query)
            result = self._route(parsed.path, query)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:
            self._json({"error": f"服务器错误: {exc}"}, 500)
            return
        if result is None:
            self._json({"error": "未知接口"}, 404)
        else:
            self._json(result)

    def _same_origin_request(self):
        """拒绝浏览器发起的跨源写请求。

        无 Origin/Referer 的调用（curl、脚本）放行；现代浏览器的
        Sec-Fetch-Site 会直接暴露跨站请求，旧浏览器则靠 Origin/Referer 判断。
        """
        site = self.headers.get("Sec-Fetch-Site")
        if site and site not in ("same-origin", "none"):
            return False
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return False
        # 只接受本机访问，避免 DNS rebinding 把 Host 伪造成攻击者域名。
        host_name = host.rsplit(":", 1)[0].lower() if ":" in host else host.lower()
        if host_name not in ("127.0.0.1", "localhost"):
            return False
        expected = f"http://{host}"
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") != expected:
            return False
        referer = self.headers.get("Referer")
        if referer and not (referer == expected or referer.startswith(expected + "/")):
            return False
        return True

    def _route(self, path, q):
        global device_online
        if path == "/api/status":
            return {
                "connected": bool(ser is not None and ser.is_open),
                "online": device_online,
                "port": getattr(ser, "port", None),
                "demo": isinstance(ser, MockSerial),
            }
        if path == "/api/check":
            result = send_cmd(0x00, 0x05, "", timeout=1.2, retries=1)
            result["label"] = "探测设备"
            device_online = result.get("decoded") is not None
            return {
                "online": device_online,
                "demo": isinstance(ser, MockSerial),
                "port": getattr(ser, "port", None),
                "steps": [result],
                "result": result,
            }
        if path == "/api/presets":
            return PRESETS
        if path == "/api/state":
            return read_state()
        if path == "/api/send":
            feature = _req_int(q, "feature", 0, 0xFF)
            cmd = _req_int(q, "cmd", 0, 0xFF)
            payload = q.get("payload", [""])[0]
            result = send_cmd(feature, cmd, payload)
            result["label"] = "自定义命令"
            return {
                "steps": [result],
                "tx": result.get("tx"),
                "rx_raw": result.get("rx_raw"),
                "decoded": result.get("decoded"),
                "error": result.get("error"),
            }
        if path == "/api/set/anc":
            return set_anc(_req_int(q, "mode", 0, 4))
        if path == "/api/set/gain":
            return set_gain(_req_int(q, "level", 0, 2))
        if path == "/api/set/led":
            return set_led(_req_int(q, "on", 0, 1))
        if path == "/api/set/lhdc":
            return set_lhdc(_req_int(q, "on", 0, 1))
        if path == "/api/set/multipoint":
            return set_onebringtwo(_req_int(q, "on", 0, 1))
        if path == "/api/set/touch":
            raw = "".join(str(q.get("hex", [""])[0]).split())
            if len(raw) != 10:
                raise ValueError("hex 必须是 5 字节（10 个十六进制字符）")
            try:
                values = list(bytes.fromhex(raw))
            except ValueError:
                raise ValueError("hex 含非法十六进制字符")
            return set_touch(values)
        if path == "/api/set/tone":
            enabled = _opt_int(q, "enabled", 0, 1)
            volume = _opt_int(q, "volume", 0, 100)
            index = _opt_int(q, "index", 0, 255)
            return set_tone(enabled=enabled, volume=volume, index=index)
        return None

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _score_serial_port(port):
    """给蓝牙串口打分：MOONDROP VID 优先，远端 SPP 服务端口次之，本机口最后。"""
    hwid = (port.hwid or "").upper()
    desc = (port.description or "").upper()
    if "BTHENUM" in hwid:
        if "1101" not in hwid:
            return -1
    elif not (("蓝牙" in desc or "BLUETOOTH" in desc)
              and ("串行" in desc or "SERIAL" in desc)):
        return -1

    score = 0
    if "05D6" in hwid:
        score += 100
    if "VID&" in hwid:
        score += 30
    if "LOCALMFG" in hwid:
        score -= 100
    return score


def find_moondrop_port():
    """自动查找 MOONDROP 蓝牙串口 (VID=0x05D6)，找不到再退回远端 SPP 串口。"""
    import serial.tools.list_ports
    candidates = []
    for port in serial.tools.list_ports.comports():
        score = _score_serial_port(port)
        if score >= 0:
            candidates.append((score, port.device))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def main():
    global ser
    port = None
    web_port = 8080
    demo = False
    demo_noack = False
    demo_latency = 0.0
    find_port = False
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            print(__doc__)
            return
        if arg == "--port" and i + 1 < len(args):
            port = args[i + 1]
            i += 2
        elif arg == "--web-port" and i + 1 < len(args):
            try:
                web_port = int(args[i + 1])
            except ValueError:
                print(f"  无效 Web 端口: {args[i + 1]}")
                return
            i += 2
        elif arg == "--demo":
            demo = True
            i += 1
        elif arg == "--demo-noack":
            demo_noack = True
            i += 1
        elif arg == "--demo-latency" and i + 1 < len(args):
            try:
                demo_latency = max(0.0, float(args[i + 1]))
            except ValueError:
                print(f"  无效延迟: {args[i + 1]}")
                return
            i += 2
        elif arg == "--find-port":
            find_port = True
            i += 1
        elif arg.upper().startswith("COM"):
            port = arg
            i += 1
        else:
            print(f"  忽略未知参数: {arg}")
            i += 1

    if find_port:
        print(port or find_moondrop_port() or "NONE")
        return

    if demo:
        ser = MockSerial(noack=demo_noack, latency=demo_latency)
        print("  DEMO 模式：未连接真实设备，使用内置假设备")
        print(f"  假设备: 固件 {ser._fw.decode()} · 电量 左{ser._battery[1]}% 右{ser._battery[2]}% 盒{ser._battery[3]}%")
        if demo_noack:
            print("  假设备: SET 命令不返回 ACK（模拟真机行为，写后仍会重读）")
        if demo_latency:
            print(f"  假设备: 模拟延迟 {demo_latency:.2f}s")
    else:
        if not port:
            port = find_moondrop_port()
        if not port:
            print("  未找到 MOONDROP 蓝牙串口")
            print("  用法: python tools/webtest.py [--port COMx] [--web-port 8080] [--demo]")
            return
        print(f"  串口: {port}")
        try:
            ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=2)
            print(f"  {port} OK")
        except Exception as exc:
            print(f"  {port} 打开失败: {exc}")
            return

    server = ThreadingHTTPServer(("127.0.0.1", web_port), Handler)
    server.daemon_threads = True
    print(f"  http://127.0.0.1:{web_port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if ser and ser.is_open:
            ser.close()
        server.server_close()


if __name__ == "__main__":
    main()
