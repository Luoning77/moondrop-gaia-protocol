"""红阶段回归测试：暴露上游 PR 评审提出的 5 个问题。

对应关系（评审编号 -> 用例）：
    问题 1  sendCustom()/sendPreset() 把错误帧/未匹配帧当成功
            -> test_issue1_error_frame_not_success
            -> test_issue1_unmatched_frame_not_success
    问题 2  send_cmd() 中 `if last_rx: break` 让无关通知提前终止重试
            -> test_issue2_notification_does_not_stop_retry
            -> test_issue2_matched_error_frame_counts_as_matched（回归基准，应通过）
            -> test_issue2_keeps_all_received_frames（诊断信息丢失）
    问题 3  _set_verify/set_touch/set_tone 在 SET 被明确拒绝时仍可能 ok=True
            -> test_issue3_set_rejected_but_state_already_expected
            -> test_issue3_touch_rejected_but_state_already_expected
            -> test_issue3_tone_rejected_but_state_already_expected
            -> test_issue3_set_noack_still_ok（回归基准，应通过）
    问题 4  Kotlin parseCodecSwitch() 未知值返回 false（归 T4，Python 侧不测）
    问题 5  _take_frame/_recv_frame 的 Len 无上限、坏帧后无法重同步
            -> test_issue5_bad_len_resync
            -> test_issue5_bad_len_resync_recv_frame
            -> test_issue5_split_and_coalesced（回归基准，应通过）
            -> test_decode_packet_oversized_len
            -> test_decode_packet_accepts_max_len（回归基准，应通过）

第二批（T3 修复后需要）：
    问题 5  -> test_issue5_bad_vendor_resync（坏 Vendor=0x99 帧后重同步）
            -> test_issue5_len_513_resync（Len=513 重同步 + 511/512/513 三点边界）
            -> test_issue5_cross_frame_swallow（Len 能凑够时跨帧吞并）
            -> test_issue5_mockserial_bad_len（MockSerial.write 324-347 同类缺陷）
    问题 2  -> test_issue2_retry_does_not_clear_valid_carry（send_cmd 666 行 clear 丢半帧）
    问题 4  -> test_issue4_python_summary_unknown_codec（_summarize 未知编解码值的 Python 镜像）

红阶段说明：本文件在未修复的 tools/webtest.py 上运行，标注为「问题复现」的用例
预期失败；标注为「回归基准」的用例预期通过，用于确认修复没有把既有正确行为改坏。
修好 webtest.py 后重新运行，全部用例应为 green。

当前基线（未修复 webtest.py）：20 个用例，16 failed / 4 passed，约 4 秒。
4 个通过项均为「回归基准」，不是问题复现不了。

运行：python -m pytest tools\\test_webtest.py -v
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import webtest  # noqa: E402  （webtest 顶层 import serial，需要 pyserial）

# 与 src/main/kotlin/com/moondrop/protocol/codec/GaiaCodec.kt 的 MAX_PAYLOAD 对齐。
MAX_PAYLOAD = 512


# ---------------------------------------------------------------------------
# 帧构造辅助
# ---------------------------------------------------------------------------
def _frame(feature, cmd, payload=b""):
    return webtest.build_tx(feature, cmd, payload)


def _response(feature, cmd, payload=b""):
    """设备响应帧：Feature 最低位置 1，Cmd 最高位为 0。"""
    return webtest.build_tx(feature | 0x01, cmd & 0x7F, payload)


def _device_error(feature, cmd, code):
    """设备错误帧：Feature 最低位置 1，Cmd 最高位置 1，payload 为错误码。"""
    return webtest.build_tx(feature | 0x01, (cmd & 0x7F) | 0x80, bytes([code]))


def _notification(feature, cmd, payload=b""):
    """设备主动通知帧：Feature 最低位为 0，Cmd 最高位置 1。"""
    return webtest.build_tx(feature & 0xFE, (cmd & 0x7F) | 0x80, payload)


# ---------------------------------------------------------------------------
# 假串口：实现 send_cmd/_recv_frame 用到的 pyserial 子集
# ---------------------------------------------------------------------------
class FakeSerial:
    """可编排的假串口。

    responder(feature, cmd, payload) -> bytes
        每次 write 解析出请求帧后调用，返回值作为设备应答注入接收缓冲。
        feature/cmd/payload 是请求帧的字节，测试里按 (feature, cmd) 分发。
    writes
        每次 write 的原始字节，用来统计重试是否真的发生。
    feed()/feed_chunks()
        直接向接收缓冲注入数据；chunks 用多个 segment 模拟拆包
        （in_waiting 只暴露当前 segment，使 _recv_frame 逐段 read）。
    """

    def __init__(self, responder=None):
        self.is_open = True
        self.port = "FAKE"
        self.responder = responder
        self.writes = []       # 每次 write 的原始数据
        self.requests = []     # 解析出的 (feature, cmd, payload)
        self._segments = []    # 接收缓冲，按 segment 存放以模拟拆包
        self._pending = bytearray()  # 一次 write 里没写完整的半帧

    # ---- 注入数据 ----
    def feed(self, data):
        if data:
            self._segments.append(bytes(data))

    def feed_chunks(self, chunks):
        for chunk in chunks:
            self.feed(chunk)

    # ---- pyserial 兼容接口 ----
    @property
    def in_waiting(self):
        return len(self._segments[0]) if self._segments else 0

    def read(self, n):
        if not self._segments:
            return b""
        segment = self._segments[0]
        take = min(n, len(segment))
        out = bytes(segment[:take])
        rest = segment[take:]
        if rest:
            self._segments[0] = rest
        else:
            self._segments.pop(0)
        return out

    def write(self, data):
        raw = bytes(data)
        self.writes.append(raw)
        buf = bytes(self._pending) + raw
        self._pending = bytearray()
        replies = bytearray()
        rest = buf
        while len(rest) >= 8:
            length = (rest[2] << 8) | rest[3]
            total = 8 + length
            if len(rest) < total:
                break
            packet = rest[:total]
            rest = rest[total:]
            self.requests.append((packet[6], packet[7], packet[8:]))
            if self.responder:
                reply = self.responder(packet[6], packet[7], packet[8:])
                if reply:
                    replies += reply
        if rest:
            self._pending = bytearray(rest)
        self.feed(bytes(replies))
        return len(raw)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self._segments.clear()
        self._pending.clear()

    def close(self):
        self.is_open = False


def _simple_device(rules):
    """rules: {(feature, cmd): bytes | callable(payload, count) -> bytes}

    callable 的 count 表示该 (feature, cmd) 第几次被请求，从 1 开始。
    """
    counts = {}

    def respond(feature, cmd, payload):
        key = (feature, cmd)
        counts[key] = counts.get(key, 0) + 1
        rule = rules.get(key)
        if rule is None:
            return b""
        if callable(rule):
            return rule(payload, counts[key])
        return rule

    device = FakeSerial(respond)
    device.counts = counts
    return device


def _install(device):
    webtest.ser = device
    webtest._rx_carry.clear()
    return device


@pytest.fixture(autouse=True)
def _serial_guard():
    """每个用例前后恢复模块级串口状态，避免用例互相污染。"""
    saved_ser = webtest.ser
    webtest.ser = None
    webtest._rx_carry.clear()
    yield
    webtest.ser = saved_ser
    webtest._rx_carry.clear()


# ---------------------------------------------------------------------------
# 评审第 1 条：错误帧不得被判为成功
# ---------------------------------------------------------------------------
def is_success(result):
    """期望语义（评审第 1 条）：错误帧 / 未匹配帧 / 超时都不是成功。

    期望 webtest 提供一个统一的成功判定（例如 send_cmd 结果里的 ok/success 字段，
    或模块级 is_success()/classify() 函数），前端 sendCustom()/sendPreset() 不再靠
    「有 decoded 且无 error 键」猜成功。当前实现没有该判定，本 helper 只认显式字段：
    返回 True/False，后端完全没有显式判定时返回 None。
    """
    if not isinstance(result, dict):
        return None
    for key in ("ok", "success", "succeeded"):
        if key in result:
            return bool(result[key])
    for key in ("error_name", "device_error", "set_error"):
        if result.get(key):
            return False
    status = result.get("status")
    if isinstance(status, str):
        return status.lower() in ("ok", "success")
    return None


# 前端 sendCustom()/sendPreset() 当前的判定方式（对应 HTML 里 2043/2057 行）：
#     const step = data.steps && data.steps[0];
#     if(!step || step.error || !step.decoded){ ...失败... } else { ...「命令已发送」... }
# 这个条件只检查「有没有解码结果」，完全不看 decoded.frame_type，所以错误帧会走进成功分支。
def _frontend_judges_success(step):
    return bool(step) and not step.get("error") and bool(step.get("decoded"))


class _FakeHandler:
    """_route 不使用 self，这里只为调用未绑定方法提供占位实例。"""


def test_issue1_error_frame_not_success():
    """设备用错误帧拒绝请求时，前端路径（/api/send）不能把它判为成功。"""
    device = _install(_simple_device({
        # 请求 (F=0x40, C=0x04) 设置 ANC 模式，设备回错误码 5（参数无效）
        (0x40, 0x04): _device_error(0x40, 0x04, 5),
    }))
    query = {"feature": ["64"], "cmd": ["4"], "payload": ["05"]}  # 十进制 64=0x40, 4=0x04
    payload = webtest.Handler._route(_FakeHandler(), "/api/send", query)

    step = payload["steps"][0]
    decoded = step.get("decoded") or {}
    assert decoded.get("frame_type") == "error", (
        f"前置条件不成立：期望设备错误帧到达并解码为 error，实际 decoded={decoded!r}"
    )
    # 先确认 bug 的触发条件：前端现有判定会认为这条错误帧是成功的。
    frontend_ok = _frontend_judges_success(step)

    verdict = is_success(payload)
    if verdict is None:
        verdict = is_success(step)
    assert verdict is False, (
        "期望 /api/send 返回体给出「设备拒绝」的显式判定（如 ok=false 或 "
        "error_name/device_error），实际没有提供统一成功判定；"
        f"当前 payload keys={sorted(payload)}，step keys={sorted(step)}，"
        f"decoded.frame_type=error、decoded.payload={decoded.get('payload')!r}，"
        f"前端现有条件 step && !step.error && step.decoded = {frontend_ok}，会弹出「命令已发送」。"
        "对应评审第 1 条。"
    )


def test_issue1_unmatched_frame_not_success():
    """收到的帧与请求不匹配（matched=False）时，也不能判成功。"""
    _install(_simple_device({
        # 请求设置 ANC 模式，设备却回了一个无关的响应帧（Feature/Cmd 都对不上）
        (0x40, 0x04): _response(0x1A, 0x01, bytes([1, 82, 2, 79])),
    }))
    query = {"feature": ["64"], "cmd": ["4"], "payload": ["05"]}
    payload = webtest.Handler._route(_FakeHandler(), "/api/send", query)

    step = payload["steps"][0]
    assert step.get("matched") is False, (
        f"前置条件不成立：期望 matched=False，实际 {step.get('matched')!r}"
    )
    frontend_ok = _frontend_judges_success(step)

    verdict = is_success(payload)
    if verdict is None:
        verdict = is_success(step)
    assert verdict is False, (
        "期望 /api/send 对「未匹配响应」给出显式失败判定（如 ok=false / status='unmatched'），"
        f"实际没有统一成功判定；payload keys={sorted(payload)}、step keys={sorted(step)}、"
        f"step.warning={step.get('warning')!r}、matched=False，"
        f"前端现有条件 step && !step.error && step.decoded = {frontend_ok}，会弹出「命令已发送」。"
        "对应评审第 1 条。"
    )


# ---------------------------------------------------------------------------
# 评审第 2 条：无关通知不得提前终止重试
# ---------------------------------------------------------------------------
def test_issue2_notification_does_not_stop_retry():
    """先收到无关通知帧、目标响应缺失时，retries 必须真的重发。"""
    notify = _notification(0x00, 0x07, b"\x01")
    reply = _response(0x40, 0x03, b"\x02")

    def respond(_payload, count):
        return notify if count == 1 else reply

    device = _install(_simple_device({(0x40, 0x03): respond}))

    result = webtest.send_cmd(0x40, 0x03, "", timeout=0.15, retries=1)

    writes = len(device.writes)
    decoded = result.get("decoded") or {}
    assert writes == 2, (
        f"期望重试真的发生（初始 1 次 + 重试 1 次 = 2 次 write），实际 write 次数={writes}；"
        f"matched={result.get('matched')!r}，最后一次解码 frame_type={decoded.get('frame_type')!r}。"
        "send_cmd 在收到无关通知后命中 `if last_rx: break`，没走到重试。对应评审第 2 条。"
    )
    assert result.get("matched") is True, (
        f"期望第二次尝试拿到匹配响应 matched=True，实际 matched={result.get('matched')!r}，"
        f"decoded={decoded!r}。对应评审第 2 条。"
    )


def test_issue2_matched_error_frame_counts_as_matched():
    """回归基准：匹配到的设备错误帧也属于 matched（修复不能把它改成未匹配）。"""
    device = _install(_simple_device({
        (0x40, 0x04): _device_error(0x40, 0x04, 5),
    }))
    result = webtest.send_cmd(0x40, 0x04, "05", timeout=0.2, retries=0)

    decoded = result.get("decoded") or {}
    assert result.get("matched") is True, (
        f"期望匹配到的错误帧 matched=True，实际 matched={result.get('matched')!r}，"
        f"decoded={decoded!r}。对应评审第 2 条（回归基准）。"
    )
    assert decoded.get("frame_type") == "error", (
        f"期望 decoded.frame_type == 'error'，实际 {decoded.get('frame_type')!r}"
    )
    assert webtest._error_of(result) == "参数无效 (5)", (
        f"期望 _error_of 给出「参数无效 (5)」，实际 {webtest._error_of(result)!r}"
    )


def test_issue2_keeps_all_received_frames():
    """问题 2 的另一半：本次尝试收到的帧不能因为 break 而在结果里丢失。"""
    notify = _notification(0x00, 0x07, b"\x01")
    reply = _response(0x40, 0x03, b"\x02")

    def respond(_payload, count):
        return notify if count == 1 else reply

    device = _install(_simple_device({(0x40, 0x03): respond}))
    result = webtest.send_cmd(0x40, 0x03, "", timeout=0.15, retries=1)

    frames = None
    for key in ("frames", "rx_all", "all_frames"):
        value = result.get(key)
        if isinstance(value, list):
            frames = value
            break
    assert frames, (
        "期望 send_cmd 结果保留本次收到的全部帧（例如 frames/rx_all 列表）用于诊断，"
        f"实际 result keys={sorted(result)}；本应能看到通知帧 "
        f"{notify.hex(' ').upper()} 与响应帧 {reply.hex(' ').upper()}。对应评审第 2 条。"
    )


# ---------------------------------------------------------------------------
# 评审第 3 条：SET 被明确拒绝时不得因「重读值恰好一致」而 ok=True
# ---------------------------------------------------------------------------
def test_issue3_set_rejected_but_state_already_expected():
    """_set_verify 路径（set_anc）：SET 被拒绝，但设备本来就处于期望值。"""
    _install(_simple_device({
        (0x40, 0x04): _device_error(0x40, 0x04, 5),   # SET 被拒绝（参数无效）
        (0x40, 0x03): _response(0x40, 0x03, b"\x02"),  # 重读本来就是期望值 2
    }))
    result = webtest.set_anc(2)

    assert result.get("ok") is False, (
        "期望 SET 收到设备错误帧时 ok=False（明确失败优先于重读一致），"
        f"实际 ok={result.get('ok')!r}、message={result.get('message')!r}、"
        f"set_error={result.get('set_error')!r}、requested={result.get('requested')!r}、"
        f"after={result.get('after')!r}。对应评审第 3 条。"
    )


def test_issue3_touch_rejected_but_state_already_expected():
    """set_touch 路径：写手势被拒绝，但重读值与提交值相同。"""
    touch = bytes([0x11, 0x23, 0x66, 0x77, 0x00])
    _install(_simple_device({
        (0x2C, 0x02): _response(0x2C, 0x02, touch),        # 写前/重读都返回当前值
        (0x2C, 0x03): _device_error(0x2C, 0x03, 6),        # 写入被拒绝（状态错误）
    }))
    result = webtest.set_touch(list(touch))

    assert result.get("ok") is False, (
        "期望写入手势收到设备错误帧时 ok=False，"
        f"实际 ok={result.get('ok')!r}、message={result.get('message')!r}、"
        f"set_error={result.get('set_error')!r}、after={result.get('after')!r}。"
        "对应评审第 3 条（set_touch 路径）。"
    )


def test_issue3_tone_rejected_but_state_already_expected():
    """set_tone 路径：写提示音被拒绝，但重读值与提交值相同。"""
    _install(_simple_device({
        (0x1C, 0x01): _response(0x1C, 0x01, bytes([1, 60, 1])),
        (0x1C, 0x02): _device_error(0x1C, 0x02, 6),
    }))
    result = webtest.set_tone(enabled=1, volume=60, index=1)

    assert result.get("ok") is False, (
        "期望写入提示音收到设备错误帧时 ok=False，"
        f"实际 ok={result.get('ok')!r}、message={result.get('message')!r}、"
        f"set_error={result.get('set_error')!r}、after={result.get('after')!r}。"
        "对应评审第 3 条（set_tone 路径）。"
    )


def test_issue3_set_noack_still_ok():
    """回归基准：SET 无 ACK、重读一致时 ok=True（--demo-noack 语义不能改坏）。"""
    _install(webtest.MockSerial(noack=True))
    result = webtest.set_anc(2)

    assert result.get("ok") is True, (
        "期望「SET 无 ACK + 重读一致」仍判成功 ok=True（既有设计，不能改坏），"
        f"实际 ok={result.get('ok')!r}、message={result.get('message')!r}、"
        f"after={result.get('after')!r}。对应评审第 3 条（回归基准）。"
    )
    assert result.get("message") == "写入后重读一致", (
        f"期望 message='写入后重读一致'，实际 {result.get('message')!r}"
    )


# ---------------------------------------------------------------------------
# 评审第 5 条：坏 Len 帧后必须能重新同步出后续正常帧
# ---------------------------------------------------------------------------
# 坏帧：Len=0xFFFF，帧头合法但长度不可信。
BAD_FRAME = bytes([0xFF, 0x04, 0xFF, 0xFF, 0x00, 0x1D, 0x41, 0x03])
# 合法 ANC 响应：设置 ANC 后的查询响应，payload=[0x02]。
GOOD_FRAME = bytes([0xFF, 0x04, 0x00, 0x01, 0x00, 0x1D, 0x41, 0x03, 0x02])


def test_issue5_bad_len_resync():
    """_take_frame：坏 Len 帧后紧跟合法帧时，必须能重新同步到合法帧。

    这里不绑定具体实现方式，接受两种修复形态：
      A. 单次调用就丢弃坏帧头并返回合法帧（rest 为空）；
      B. 单次调用返回 (None, rest)，但 rest 已经跳过坏帧头、重新定位到合法帧起点，
         调用方下一轮即可取到。
    两种都算「重新同步成功」；当前实现把整个缓冲区原样退回，两者都不满足。
    """
    frame, rest = webtest._take_frame(bytearray(BAD_FRAME + GOOD_FRAME))

    resynced = (frame == GOOD_FRAME and bytes(rest) == b"") or \
               (frame is None and bytes(rest) == GOOD_FRAME)
    assert resynced, (
        "期望 _take_frame 把 Len=0xFFFF 的坏帧头当作错帧丢弃并重新同步到合法帧 "
        f"{GOOD_FRAME.hex(' ').upper()}，实际 frame={None if frame is None else frame.hex(' ').upper()}、"
        f"rest={bytes(rest).hex(' ').upper()}（缓冲区共 {len(BAD_FRAME + GOOD_FRAME)} 字节，"
        "远小于声明的 8+65535，且没有可用的超时兜底，会导致本次接收一直等到超时）。"
        "对应评审第 5 条。"
    )


def test_issue5_bad_len_resync_recv_frame():
    """_recv_frame：坏 Len 帧与合法帧同一批到达时，必须返回合法帧而不是超时。"""
    device = _install(FakeSerial())
    device.feed(BAD_FRAME + GOOD_FRAME)

    frame = webtest._recv_frame(0.2)

    decoded = webtest.decode_packet(frame) if frame else None
    assert frame == GOOD_FRAME, (
        "期望 _recv_frame 在坏帧头之后重新同步并返回合法帧 "
        f"{GOOD_FRAME.hex(' ').upper()}，实际返回 {frame.hex(' ').upper() if frame else '(空/超时)'}、"
        f"decoded={decoded!r}。当前实现会一直等 Len=65535 的超时。对应评审第 5 条。"
    )


def test_issue5_split_and_coalesced():
    """回归基准：拆包（两次 read）与粘包（一次 read 两帧）都必须正常工作。"""
    # --- 拆包：同一帧分两次 read ---
    device = _install(FakeSerial())
    device.feed_chunks([GOOD_FRAME[:4], GOOD_FRAME[4:]])
    split_frame = webtest._recv_frame(0.2)
    assert split_frame == GOOD_FRAME, (
        f"拆包场景：期望返回完整帧 {GOOD_FRAME.hex(' ').upper()}，"
        f"实际 {split_frame.hex(' ').upper() if split_frame else '(空/超时)'}。对应评审第 5 条（回归基准）。"
    )

    # --- 粘包：一次 read 带回两帧，先返回第一帧，第二帧留在 carry ---
    webtest._rx_carry.clear()
    second_frame = _response(0x40, 0x03, b"\x01")
    device = _install(FakeSerial())
    device.feed(GOOD_FRAME + second_frame)
    first = webtest._recv_frame(0.2)
    second = webtest._recv_frame(0.2)
    assert first == GOOD_FRAME and second == second_frame, (
        f"粘包场景：期望依次取出 {GOOD_FRAME.hex(' ').upper()} / {second_frame.hex(' ').upper()}，"
        f"实际 {first.hex(' ').upper() if first else '(空)'} / {second.hex(' ').upper() if second else '(空)'}。"
        "对应评审第 5 条（回归基准）。"
    )


def test_decode_packet_oversized_len():
    """decode_packet 对超过 MAX_PAYLOAD 的 Len 必须拒绝（与 Kotlin GaiaCodec 对齐）。"""
    oversized_len = MAX_PAYLOAD + 1
    data = (bytes([0xFF, 0x04, (oversized_len >> 8) & 0xFF, oversized_len & 0xFF,
                   0x00, 0x1D, 0x41, 0x03]) + bytes(oversized_len))
    decoded = webtest.decode_packet(data)

    assert decoded is None, (
        f"期望 decode_packet 对 Len={oversized_len}（> MAX_PAYLOAD={MAX_PAYLOAD}）返回 None，"
        f"实际返回 {decoded!r}。Kotlin GaiaCodec.decode 已有同样的上限检查，Python 侧缺失。"
        "对应评审第 5 条。"
    )


def test_decode_packet_accepts_max_len():
    """回归基准：Len 恰好等于 MAX_PAYLOAD 时仍应接受（避免修复时差一错误）。"""
    data = (bytes([0xFF, 0x04, (MAX_PAYLOAD >> 8) & 0xFF, MAX_PAYLOAD & 0xFF,
                   0x00, 0x1D, 0x41, 0x03]) + bytes(MAX_PAYLOAD))
    decoded = webtest.decode_packet(data)
    assert decoded is not None, (
        f"期望 Len={MAX_PAYLOAD}（合法上限）仍被接受，实际返回 None。对应评审第 5 条（回归基准）。"
    )


# ===========================================================================
# 第二批（T3 修复后需要）：坏 vendor、Len=513、跨帧吞并、重试清 carry、
# MockSerial 坏 Len、_summarize 未知编解码值。
# ===========================================================================

# 坏 vendor 帧：帧头 FF 04 与 Len 都合法，但 Vendor=0x99 != 0x1D。
# 前 8 字节全部「看起来像帧」，所以只丢 1 字节重新扫描时要走过 9 字节才到下一帧起点。
BAD_VENDOR_FRAME = bytes([0xFF, 0x04, 0x00, 0x01, 0x00, 0x99, 0x41, 0x03, 0x04])


def test_issue5_bad_vendor_resync():
    """坏 vendor 帧（Vendor=0x99）后面紧跟合法帧时，必须能取出合法帧。

    与坏 Len 不同，这里的 Len 是合法的（1），帧结构自洽，只有 Vendor 不对；
    所以不能靠「长度超限」判坏，必须校验 Vendor，并丢 1 字节重新扫描
    （实测需要从 FF 04 处丢 9 字节才到达下一帧起点）。
    """
    buf = BAD_VENDOR_FRAME + GOOD_FRAME
    frame, rest = webtest._take_frame(bytearray(buf))

    # 接受两种修复形态：单次调用直接返回合法帧，或返回已重定位到合法帧起点的空帧 + rest。
    resynced = (frame == GOOD_FRAME and bytes(rest) == b"") or \
               (frame is None and bytes(rest) == GOOD_FRAME)
    assert resynced, (
        "期望把 Vendor=0x99 的坏帧当作错帧丢弃并重新同步到合法帧 "
        f"{GOOD_FRAME.hex(' ').upper()}，实际 frame="
        f"{None if frame is None else frame.hex(' ').upper()}、rest={bytes(rest).hex(' ').upper()}。"
        f"当前实现只校验 FF 04 头和 Len，不校验 Vendor（应为 0x1D），"
        f"于是把坏帧 {BAD_VENDOR_FRAME.hex(' ').upper()} 当成合法帧返回。对应评审第 5 条。"
    )

    # 补充：合法帧必须先被校验通过；若直接返回坏 vendor 帧则明确判红。
    assert frame != BAD_VENDOR_FRAME, (
        f"期望返回校验通过的合法帧，实际把坏 vendor 帧 {BAD_VENDOR_FRAME.hex(' ').upper()} "
        "当成帧返回（Vendor=0x99 != 0x1D）。对应评审第 5 条。"
    )


def test_issue5_len_513_resync():
    """Len=513（超限 1 字节）后紧跟合法帧时，必须重同步。

    与已有的 511/512/513 三点断言配合：511、512 合法可解析，513 必须被当作坏帧头。
    """
    over = MAX_PAYLOAD + 1  # 513
    bad = (bytes([0xFF, 0x04, (over >> 8) & 0xFF, over & 0xFF, 0x00, 0x1D, 0x41, 0x03])
           + bytes(over))

    # 1) _take_frame 层面：513 必须被判为坏帧头，能重同步到后面的合法帧。
    frame, rest = webtest._take_frame(bytearray(bad + GOOD_FRAME))
    resynced = (frame == GOOD_FRAME and bytes(rest) == b"") or \
               (frame is None and bytes(rest) == GOOD_FRAME)
    assert resynced, (
        f"期望 Len={over}（> MAX_PAYLOAD={MAX_PAYLOAD}）被当作坏帧头丢弃并重同步到 "
        f"{GOOD_FRAME.hex(' ').upper()}，实际 frame="
        f"{None if frame is None else (len(frame), frame[:8].hex(' ').upper())}、"
        f"rest_len={len(rest)}。当前实现无上限校验，会原样返回 521 字节的「帧」。"
        "对应评审第 5 条。"
    )

    # 2) 边界一致性：512 必须仍被视为合法长度，513 必须不合法。
    for length, should_be_valid in ((MAX_PAYLOAD - 1, True), (MAX_PAYLOAD, True), (over, False)):
        data = (bytes([0xFF, 0x04, (length >> 8) & 0xFF, length & 0xFF, 0x00, 0x1D, 0x41, 0x03])
                + bytes(length))
        ok = webtest.decode_packet(data) is not None
        assert ok is should_be_valid, (
            f"Len={length} 的合法性判断错误：期望 {'接受' if should_be_valid else '拒绝'}，"
            f"实际 {'接受' if ok else '拒绝'}（MAX_PAYLOAD={MAX_PAYLOAD}）。"
            "对应评审第 5 条（511/512/513 三点边界）。"
        )


def test_issue5_cross_frame_swallow():
    """Len 字段「能凑够」时，不得把后续合法帧当成 payload 吞掉。

    构造：Len=200 的帧头 + 190 字节填充 + 合法帧 G1(9B) + 合法帧 G2(9B)。
    Len=200 声明需要 208 字节，而缓冲区里恰好有 208 字节可用，
    于是一个不做内容校验的实现会把 G1、甚至 G2 整个吞进 payload。
    断言只有两种可接受结果：取不到帧（等待更多数据/判坏），
    或者取到的帧 payload 长度 <= MAX_PAYLOAD 且不包含后续完整合法帧。
    """
    filler_len = 190
    g1 = GOOD_FRAME
    g2 = _response(0x40, 0x03, b"\x01")
    header = bytes([0xFF, 0x04, 0x00, 0xC8, 0x00, 0x1D, 0x41, 0x03])  # Len = 200
    buf = header + bytes(filler_len) + g1 + g2

    frame, rest = webtest._take_frame(bytearray(buf))

    if frame is None:
        return  # 取不到帧是可接受的（等待更多数据，或判坏帧后重同步）

    payload = frame[8:]
    assert len(payload) <= MAX_PAYLOAD, (
        f"取到的帧 payload 长度 {len(payload)} 超过 MAX_PAYLOAD={MAX_PAYLOAD}，"
        f"帧={frame[:16].hex(' ').upper()}…。对应评审第 5 条。"
    )
    # 关键断言：不能把「完整的后续合法帧」当成 payload 内容吞进去。
    swallowed = []
    if g1 in payload:
        swallowed.append(f"G1={g1.hex(' ').upper()}")
    if g2 in payload:
        swallowed.append(f"G2={g2.hex(' ').upper()}")
    assert not swallowed, (
        "期望 Len=200 的帧不得把后续合法帧当成 payload 吞掉，实际 payload "
        f"（长度 {len(payload)}）包含 {', '.join(swallowed)}。"
        f"完整帧={frame.hex(' ').upper()}、rest={bytes(rest).hex(' ').upper()}。"
        "当前实现只按 Len 截取、不校验帧边界，会把紧随其后的合法帧整段吃掉导致丢响应。"
        "对应评审第 5 条。"
    )


def test_issue2_retry_does_not_clear_valid_carry():
    """重试不得清掉 carry 里已收到的合法帧（send_cmd 666 行 _rx_carry.clear()）。

    场景：设备一次只发来「合法帧头（前 8 字节）」，payload 在重试之后才到。
    第一次尝试把半帧留在 _rx_carry；若重试前无条件 clear，半帧丢失，
    第二次尝试只剩 payload 字节，无法再拼出帧。
    """
    frame_header = GOOD_FRAME[:8]
    frame_body = GOOD_FRAME[8:]

    class _StickyDevice(FakeSerial):
        """第 1 次 write 只发帧头，第 2 次 write 发 payload；不响应 reset_input_buffer。"""

        def __init__(self):
            super().__init__(None)
            self._plan = [frame_header, frame_body]

        def write(self, data):
            idx = min(len(self.writes), len(self._plan) - 1)
            self.writes.append(bytes(data))
            self.feed(self._plan[idx])
            return len(data)

        def reset_input_buffer(self):
            # 真机 reset_input_buffer 清的是驱动缓冲；_rx_carry 是应用层 carry，
            # 由 send_cmd 自己维护。这里模拟「已到达数据不会因为重试而回到设备」，
            # 即清掉的就是真丢掉了，_rx_carry 是唯一残存。
            super().reset_input_buffer()

    device = _install(_StickyDevice())
    result = webtest.send_cmd(0x40, 0x03, "", timeout=0.12, retries=1)

    assert result.get("matched") is True, (
        "期望重试时保留 carry 中已收到的半帧，第二次尝试补齐 payload 后匹配成功，"
        f"实际 matched={result.get('matched')!r}、error={result.get('error')!r}、"
        f"rx_raw={result.get('rx_raw')!r}、write 次数={len(device.writes)}。"
        "send_cmd 每次尝试都执行 `_rx_carry.clear()`（666 行），把上一次尝试收到的"
        "半帧丢掉了。对应评审第 2 条。"
    )


def test_issue5_mockserial_bad_len():
    """MockSerial 收到坏 Len 帧后，后续合法命令仍必须能处理。

    DEMO 假设备的 write() 里按 Len 切帧（324-347 行），没有上限校验：
    收到 FF 04 FF FF ... 时会把剩余字节全部存进 _pending 当作半帧，
    之后所有合法命令都被拼到这个半帧后面，永远出不来应答（in_waiting 恒为 0）。
    """
    mockser = webtest.MockSerial()
    mockser.write(BAD_FRAME)  # FF 04 FF FF 00 1D 41 03

    mockser.write(webtest.build_tx(0x40, 0x03))  # 合法读 ANC 命令
    waiting = mockser.in_waiting
    reply = mockser.read(waiting) if waiting else b""

    assert waiting > 0 and reply.startswith(b"\xFF\x04"), (
        "期望 MockSerial 把 Len=0xFFFF 的坏帧当错帧丢弃后，仍能正常应答后续合法命令，"
        f"实际 write 坏帧后 in_waiting={mockser.in_waiting}，再写合法命令后 in_waiting={waiting}、"
        f"read 得到 {reply.hex(' ').upper() or '(空)'}（pending 残留 {len(mockser._pending)} 字节）。"
        "这会让 --demo 模式在收到一次坏帧后彻底失联。对应评审第 5 条。"
    )
    decoded = webtest.decode_packet(reply)
    assert decoded is not None and decoded.get("cmd_base") == 0x03, (
        f"期望应答可解码且 cmd_base=0x03，实际 decoded={decoded!r}。对应评审第 5 条。"
    )


def test_issue4_python_summary_unknown_codec():
    """_summarize 对编解码域 payload[0] 为未知值（0x02/0xFF）时不得显示「开」。

    这是 Python 侧对评审第 4 条（Kotlin parseCodecSwitch 未知值语义）的镜像防护：
    0x00=关、0x01=开，其余值应显示「未知」，不能因为 `if payload[0]` 为真就报「开」。
    注意本条是否成立取决于 T4 是否把「未知值」语义同步到 Python 展示层。
    """
    unknown_results = []
    for code in (0x02, 0xFF):
        decoded = webtest.decode_packet(webtest.build_tx(0x21, 0x01, bytes([code])))
        summary = (decoded or {}).get("summary") or ""
        if "开" in summary:
            unknown_results.append((code, summary))
    assert not unknown_results, (
        "期望 _summarize 对未知编解码值不显示「开」，实际 "
        + "；".join(f"payload[0]=0x{code:02X} -> summary={summary!r}"
                   for code, summary in unknown_results)
        + "。当前实现用 `'开' if payload[0] else '关'`，把任意非零值都显示成「开」，"
        "与 Kotlin parseCodecSwitch 的 0x00/0x01/其余 三态语义不一致。对应评审第 4 条（Python 镜像）。"
    )


# ---------------------------------------------------------------------------
# 评审第 6 条：仍然残留的「decoded 存在即成功」判据
# ---------------------------------------------------------------------------
def _fast_read_state(monkeypatch):
    """read_state() 内部用的 timeout 是给真机调的（0.6~1.2s）。

    测试里设备要么立刻应答、要么完全不应答，不需要等那么久；
    这里把传给 send_cmd 的 timeout 统一压到 0.05s，让用例跑快些。
    """
    real_send_cmd = webtest.send_cmd

    def fast_send_cmd(feature, cmd, payload_hex="", timeout=1.0, retries=1):
        return real_send_cmd(feature, cmd, payload_hex,
                             timeout=min(timeout, 0.05), retries=retries)

    monkeypatch.setattr(webtest, "send_cmd", fast_send_cmd)


def test_issue6_read_state_error_frame_means_online(monkeypatch):
    """固件探活命中设备错误帧时，设备其实在线，不能判 offline 而跳过全部读取。

    触发条件：设备对 `00 05`（读固件）回错误帧。旧实现只判
    `probe.get("decoded") is None`，会把这种情况当成「设备不在」，
    直接返回 online=False 且跳过后面 12 项读取。
    """
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        (0x00, 0x05): _device_error(0x00, 0x05, 1),      # 设备拒绝读固件
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),  # 但其它读取正常
    }))
    result = webtest.read_state()

    assert result["online"] is True, (
        "期望固件探活收到设备错误帧时仍判 online=True（设备给了应答，说明在线），"
        f"实际 online={result['online']!r}、probe_status={result.get('probe_status')!r}。"
        "旧判据只检查 decoded 是否存在之外的情况会误判离线。对应评审第 6 条。"
    )
    assert result["state"].get("anc") == 0x02, (
        "期望设备在线时继续读取其余项并填充 state，"
        f"实际 state={result['state']!r}。探活命中错误帧不应跳过全部读取。对应评审第 6 条。"
    )
    assert result["answered"] is True, (
        "期望 answered=True（其余项里有匹配的响应帧），"
        f"实际 answered={result['answered']!r}。对应评审第 6 条。"
    )


def test_issue6_read_state_no_reply_is_offline(monkeypatch):
    """设备完全无应答时判 offline，并保持「快速失败、不逐项等超时」的行为。"""
    _fast_read_state(monkeypatch)
    _install(_simple_device({}))          # 任何命令都不回
    result = webtest.read_state()

    assert result["online"] is False, (
        f"期望设备无任何应答时 online=False，实际 {result['online']!r}。"
    )
    assert result["state"] == {}, (
        f"期望离线时 state 为空、跳过后续读取，实际 {result['state']!r}。"
    )
    assert len(result["steps"]) == 2, (
        "期望离线时只发两条探活命令（固件 + 电量兜底），不逐项等 12 项超时，"
        f"实际发了 {len(result['steps'])} 条。"
    )


def test_issue6_read_state_notification_is_not_online(monkeypatch):
    """只收到无关通知帧时不能据此判在线（通知不能证明设备响应了本次请求）。"""
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        # 探活请求没有匹配响应，但链路上有异步通知推送
        (0x00, 0x05): _notification(0x40, 0x03, bytes([0x01])),
    }))
    result = webtest.read_state()

    assert result["online"] is False, (
        "期望只收到无关通知帧时判 online=False（通知不能证明设备响应了本次请求），"
        f"实际 online={result['online']!r}、probe_status={result.get('probe_status')!r}。"
        "旧判据 any(decoded is not None) 会把通知帧算成在线证据。对应评审第 6 条。"
    )


def test_issue6_api_check_reports_answered_separately():
    """/api/check 要把「设备在线但拒绝」与「设备离线」区分开。"""
    _install(_simple_device({
        (0x00, 0x05): _device_error(0x00, 0x05, 1),
    }))
    payload = webtest.Handler._route(_FakeHandler(), "/api/check", {})

    assert payload["online"] is True, (
        "期望设备回错误帧时 online=True（设备给了应答），"
        f"实际 online={payload['online']!r}。对应评审第 6 条。"
    )
    assert payload["answered"] is False, (
        f"期望 answered=False（应答不符合请求），实际 {payload['answered']!r}。"
    )
    assert payload.get("status") == "device_error", (
        f"期望 status='device_error'，实际 {payload.get('status')!r}，"
        "前端需要它来显示「设备拒绝」而不是「设备离线」。对应评审第 6 条。"
    )
    assert payload.get("error_name"), (
        f"期望带上 error_name 便于前端显示具体拒绝原因，实际 {payload.get('error_name')!r}。"
    )


def test_issue6_battery_error_frame_not_success():
    """电量查询返回错误帧时，前端判据必须失败（否则页面提示「已刷新」但值没更新）。

    前端 refreshBattery() 当前判据是 `!step || step.error || !step.decoded`，
    要求改为使用 /api/send 返回的 data.ok，并要求电量 payload 真实存在。
    这里按修改后的正确判据断言后端返回的字段组合。
    """
    _install(_simple_device({
        (0x1A, 0x01): _device_error(0x1A, 0x01, 5),      # 电量查询被拒绝
    }))
    query = {"feature": ["26"], "cmd": ["1"], "payload": ["010203"]}  # 0x1A, 0x01
    payload = webtest.Handler._route(_FakeHandler(), "/api/send", query)

    step = payload["steps"][0]
    decoded = step.get("decoded") or {}
    assert decoded.get("frame_type") == "error", (
        f"前置条件不成立：期望电量查询收到错误帧，实际 decoded={decoded!r}"
    )
    # 错误帧路径下 decode_packet 不会设置 battery 字段（见 webtest.py 约 276 行）
    assert not decoded.get("battery"), (
        f"前置条件不成立：错误帧不应带 battery 字段，实际 {decoded.get('battery')!r}"
    )
    # 正确的前端判据：data.ok && decoded.battery
    frontend_ok = bool(payload.get("ok")) and bool(decoded.get("battery"))
    assert frontend_ok is False, (
        "期望电量读取被拒绝时前端判据为假，实际为真——页面会提示「电量已刷新」"
        f"但电量没有更新。payload ok={payload.get('ok')!r}、"
        f"status={payload.get('status')!r}、battery={decoded.get('battery')!r}。"
        "对应评审第 6 条。"
    )


def test_issue6_mark_online_requires_device_answer():
    """_mark_online 不能用「decoded 存在」判在线：通知帧不算设备应答。"""
    notification_only = [
        {"decoded": webtest.decode_packet(_notification(0x40, 0x03, bytes([1])))},
    ]
    webtest.device_online = False
    webtest._mark_online(notification_only)
    assert webtest.device_online is False, (
        "期望只有通知帧时 _mark_online 不把设备标记为在线（通知不能证明设备响应了请求），"
        f"实际 device_online={webtest.device_online!r}。对应评审第 6 条。"
    )

    error_frame = webtest.decode_packet(_device_error(0x40, 0x04, 5))
    webtest._mark_online([{"decoded": error_frame}])
    assert webtest.device_online is True, (
        "期望收到设备错误帧时 _mark_online 判在线（设备明确拒绝了命令，说明设备在），"
        f"实际 device_online={webtest.device_online!r}。对应评审第 6 条。"
    )


def test_issue6_firmware_requires_matched(monkeypatch):
    """固件版本必须校验 matched：不能把「其它命令」的响应当成固件版本。

    复现：请求 00 05（读固件），设备回一条 00 03（设备序列号）的响应。
    两者 frame_type 都是 response，但 matched=False，旧判据（只检查
    frame_type == "response"）会把序列号显示成页头的固件版本。
    """
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        # 请求 00 05，回的是 00 03 的响应（帧结构合法，但命令对不上）
        (0x00, 0x05): _response(0x00, 0x03, b"20560023326101203277"),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
    }))
    result = webtest.read_state()

    probe = result["steps"][0]
    assert probe.get("matched") is False, (
        f"前置条件不成立：期望探活帧 matched=False，实际 {probe.get('matched')!r}"
    )
    assert "firmware" not in result["state"], (
        "期望 matched=False 的帧不被当成固件版本，实际 firmware="
        f"{result['state'].get('firmware')!r}（这是 00 03 设备序列号）。"
        "旧判据只检查 frame_type == 'response'，没校验 matched。对应评审第 6 条。"
    )


def test_issue6_probe_ladder_falls_back_to_battery(monkeypatch):
    """固件查询无回帧、但其它命令正常应答时，不能判离线。

    真机上 00 00 / 00 03 确实无回帧（见报告 4.2 节），所以「无回帧」≠「设备不在」。
    修复后应有第二级探活（电量），任一有应答即视为在线并继续读取。
    """
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        # 00 05 无任何回帧
        (0x1A, 0x01): _response(0x1A, 0x01, bytes([1, 82, 2, 79, 3, 0xFF])),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
        (0x26, 0x01): _response(0x26, 0x01, bytes([1])),
    }))
    result = webtest.read_state()

    assert result["online"] is True, (
        "期望固件查询无回帧、但电量查询有应答时判 online=True，"
        f"实际 online={result['online']!r}、probe_status={result.get('probe_status')!r}。"
        "「无回帧」不等于「设备不在」。对应评审第 6 条。"
    )
    assert result["state"], (
        f"期望继续读取其余项并填充 state，实际 state={result['state']!r}。"
    )
    assert result["state"].get("anc") == 0x02, (
        f"期望 state 含 anc=0x02，实际 {result['state']!r}。"
    )


def test_issue6_firmware_matched_response_still_works(monkeypatch):
    """回归基准：固件查询正常匹配时，firmware 必须正常写入。"""
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        (0x00, 0x05): _response(0x00, 0x05, b"3.5.6"),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
    }))
    result = webtest.read_state()

    assert result["state"].get("firmware") == "3.5.6", (
        "期望正常匹配的固件响应仍能写入 state，"
        f"实际 firmware={result['state'].get('firmware')!r}。修改不能破坏正常路径。"
    )


def test_issue6_api_status_online_requires_connected(monkeypatch):
    """/api/status 的 online 不能在没有连接时返回 True（device_online 是陈旧值）。"""
    webtest.device_online = True          # 模拟上一次读取留下的在线状态
    webtest.ser = None                    # 串口已关闭
    payload = webtest.Handler._route(_FakeHandler(), "/api/status", {})

    assert payload["connected"] is False, f"前置条件：期望 connected=False，实际 {payload!r}"
    assert payload["online"] is False, (
        "期望串口未连接时 /api/status 的 online=False，"
        f"实际 online={payload['online']!r}。device_online 是全局陈旧值，"
        "必须与 connected 取与。对应评审第 6 条。"
    )


def test_issue6_read_state_aborts_on_dead_link(monkeypatch):
    """读到一半链路断掉时，不能逐项等满所有超时。

    构造：前两项（探活 + 电量兜底）正常应答，之后全部零接收。
    期望连续两项零接收后提前结束，steps 明显少于完整的 13 步。
    """
    _fast_read_state(monkeypatch)
    call_count = {"n": 0}

    def respond(feature, cmd, payload):
        call_count["n"] += 1
        # 前两次请求正常应答（固件探活 + 电量），之后链路静默
        if call_count["n"] <= 2:
            if (feature, cmd) == (0x00, 0x05):
                return _response(0x00, 0x05, b"3.5.6")
            if (feature, cmd) == (0x1A, 0x01):
                return _response(0x1A, 0x01, bytes([1, 82, 2, 79, 3, 0xFF]))
        return b""

    _install(FakeSerial(respond))
    result = webtest.read_state()

    assert result["aborted_early"] is True, (
        "期望连续两项零接收时提前结束并标记 aborted_early=True，"
        f"实际 aborted_early={result.get('aborted_early')!r}、"
        f"steps={len(result['steps'])} 条。没有守卫时会跑满 12 项各自超时。"
    )
    assert len(result["steps"]) <= 5, (
        f"期望提前结束后 steps 明显少于完整读取，实际发了 {len(result['steps'])} 条。"
    )
    assert result["state"].get("firmware") == "3.5.6", (
        f"期望链路断开前已读到的值仍保留，实际 state={result['state']!r}。"
    )


def test_issue6_read_state_does_not_abort_on_device_errors(monkeypatch):
    """设备回错误帧不算零接收，不能触发提前结束。

    真机上 LC3/LDAC 会回「不支持的命令」错误帧；这类响应证明链路正常，
    守卫必须继续读完，否则会漏读后面的项。
    """
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        (0x00, 0x05): _response(0x00, 0x05, b"3.5.6"),
        (0x1A, 0x01): _response(0x1A, 0x01, bytes([1, 82, 2, 79, 3, 0xFF])),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
        (0x40, 0x29): _response(0x40, 0x29, bytes([1, 1, 1, 1, 0])),
        (0x1E, 0x01): _response(0x1E, 0x01, bytes([1])),
        (0x26, 0x01): _response(0x26, 0x01, bytes([1])),
        (0x2C, 0x02): _response(0x2C, 0x02, bytes([0x11, 0x23, 0x77, 0x45, 0x66])),
        (0x1C, 0x01): _response(0x1C, 0x01, bytes([1, 64, 1])),
        (0x20, 0x05): _response(0x20, 0x05, bytes([0])),
        # LC3 / LDAC 连续两条错误帧：不是零接收
        (0x20, 0x01): _device_error(0x20, 0x01, 1),
        (0x20, 0x02): _device_error(0x20, 0x02, 1),
        (0x28, 0x01): _response(0x28, 0x01, bytes([1])),
        (0x28, 0x03): _response(0x28, 0x03, bytes([5])),
    }))
    result = webtest.read_state()

    assert result["aborted_early"] is False, (
        "期望设备回错误帧时不触发提前结束（错误帧证明链路正常），"
        f"实际 aborted_early={result['aborted_early']!r}、steps={len(result['steps'])} 条。"
    )
    assert len(result["steps"]) == 13, (
        f"期望读完全部 13 步，实际 {len(result['steps'])} 条（提前退出了）。"
    )
    assert result["state"].get("onebringtwo") == 1, (
        "期望错误帧之后的项仍然读到（onebringtwo 在 LC3/LDAC 之后），"
        f"实际 state={result['state']!r}。"
    )


# ---------------------------------------------------------------------------
# 第二轮复查追加：R1 / R2 / R3 / R4
# ---------------------------------------------------------------------------
def test_issue6_api_check_uses_same_probe_ladder(monkeypatch):
    """R1：/api/check 必须与 read_state 用同一套两级探活。

    否则同一台设备两个接口会给出相反结论：设备支持电量、不支持读固件时，
    /api/check 报离线而 /api/state 报在线。
    """
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        # 00 05 无回帧，其余正常 —— 与真机 00 00/00 03 无回帧同型
        (0x1A, 0x01): _response(0x1A, 0x01, bytes([1, 82, 2, 79, 3, 0xFF])),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
    }))
    check = webtest.Handler._route(_FakeHandler(), "/api/check", {})
    state = webtest.read_state()

    assert check["online"] is True, (
        "期望 /api/check 在固件无回帧、电量有应答时判 online=True，"
        f"实际 online={check['online']!r}、status={check.get('status')!r}。"
        "它仍是单发 00 05，没有接上两级探活。对应 R1。"
    )
    assert check["answered"] is True, (
        f"期望 answered=True（电量应答成功），实际 {check['answered']!r}。对应 R1。"
    )
    assert check["online"] == state["online"], (
        "期望 /api/check 与 read_state 对同一台设备给出相同结论，"
        f"实际 check.online={check['online']!r}、state.online={state['online']!r}。对应 R1。"
    )


def test_issue6_read_state_no_link_fails_fast(monkeypatch):
    """R4(c)：串口未打开时不该逐项刷 no_link，也不该标成 aborted_early。"""
    _fast_read_state(monkeypatch)
    webtest.ser = None
    result = webtest.read_state()

    assert result["online"] is False, f"期望 online=False，实际 {result['online']!r}。"
    assert result["connected"] is False, (
        f"期望 connected=False，实际 {result.get('connected')!r}。对应 R4(c)。"
    )
    assert result["aborted_early"] is False, (
        "期望串口未打开时 aborted_early=False（「没连上」不是「提前中断」），"
        f"实际 {result['aborted_early']!r}。对应 R4(c)。"
    )
    assert len(result["steps"]) <= 2, (
        f"期望最多 2 条探活（不重复发 no_link），实际 {len(result['steps'])} 条。对应 R4(c)。"
    )


def test_issue6_read_state_stops_when_only_notifications(monkeypatch):
    """R4(a)：只收到通知、从不应答时，必须尽早收工，不能跑满 13 步。

    两级探活都只拿到通知 → 判不出设备在，走「不存活」分支直接返回，
    比逐项读到守卫阈值更早收工。
    """
    _fast_read_state(monkeypatch)

    def respond(feature, cmd, payload):
        return _notification(0x40, 0x03, bytes([1]))

    _install(FakeSerial(respond))
    result = webtest.read_state()

    assert result["online"] is False, (
        f"期望只收到通知时 online=False（通知不能证明设备处理了请求），"
        f"实际 {result['online']!r}。对应 R4(a)。"
    )
    assert result["state"] == {}, (
        f"期望只有通知时不填充 state，实际 {result['state']!r}。对应 R4(a)。"
    )
    assert len(result["steps"]) <= 5, (
        "期望尽早收工（旧守卫用 rx_raw 判断，通知帧有 rx_raw 所以抓不到，"
        f"会跑满 13 步），实际只跑了 {len(result['steps'])} 步。对应 R4(a)。"
    )


def test_issue6_read_state_guard_stops_on_silent_tail(monkeypatch):
    """R4(a)：探活正常、但后续命令只收到通知时，守卫要按「连续未应答」收工。

    这条才真正走到守卫循环：前两级探活有应答（判为在线），之后每条只拿到
    一条通知。旧判据看 rx_raw（通知有值）不会计为未应答，会跑满 13 步。
    """
    _fast_read_state(monkeypatch)
    probe_keys = {(0x00, 0x05), (0x1A, 0x01)}

    def respond(feature, cmd, payload):
        if (feature, cmd) in probe_keys:
            if (feature, cmd) == (0x00, 0x05):
                return _response(0x00, 0x05, b"3.5.6")
            return _response(0x1A, 0x01, bytes([1, 82, 2, 79, 3, 0xFF]))
        # 其余命令只回异步通知，没有任何针对本次请求的应答
        return _notification(0x40, 0x81, bytes([1]))

    _install(FakeSerial(respond))
    result = webtest.read_state()

    assert result["aborted_early"] is True, (
        "期望探活后连续收到通知时触发守卫提前结束，"
        f"实际 aborted_early={result['aborted_early']!r}、steps={len(result['steps'])} 条。"
        "旧判据用 rx_raw（通知帧非空）判断，抓不到这种静默。对应 R4(a)。"
    )
    assert len(result["steps"]) < 13, (
        f"期望提前结束、不跑满 13 步，实际 {len(result['steps'])} 步。对应 R4(a)。"
    )
    assert result["online"] is True, (
        "期望探活阶段已证明设备在线，online=True，"
        f"实际 {result['online']!r}。"
    )


def test_issue6_read_state_keeps_going_on_device_errors(monkeypatch):
    """R4(b) 回归基准：设备回错误帧算已应答，不能误判断连。"""
    _fast_read_state(monkeypatch)
    rules = {
        (0x00, 0x05): _response(0x00, 0x05, b"3.5.6"),
        (0x1A, 0x01): _response(0x1A, 0x01, bytes([1, 82, 2, 79, 3, 0xFF])),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
        (0x40, 0x29): _response(0x40, 0x29, bytes([1, 1, 1, 1, 0])),
        (0x1E, 0x01): _response(0x1E, 0x01, bytes([1])),
        (0x26, 0x01): _response(0x26, 0x01, bytes([1])),
        (0x2C, 0x02): _response(0x2C, 0x02, bytes([0x11, 0x23, 0x77, 0x45, 0x66])),
        (0x1C, 0x01): _response(0x1C, 0x01, bytes([1, 64, 1])),
        (0x20, 0x05): _response(0x20, 0x05, bytes([0])),
        # 连续三条错误帧：仍算已应答
        (0x20, 0x01): _device_error(0x20, 0x01, 1),
        (0x20, 0x02): _device_error(0x20, 0x02, 1),
        (0x28, 0x01): _response(0x28, 0x01, bytes([1])),
        (0x28, 0x03): _response(0x28, 0x03, bytes([5])),
    }
    _install(_simple_device(rules))
    result = webtest.read_state()

    assert result["aborted_early"] is False, (
        "期望设备回错误帧时不触发提前结束，"
        f"实际 aborted_early={result['aborted_early']!r}、steps={len(result['steps'])} 条。"
    )
    assert result["state"].get("onebringtwo") == 1, (
        "期望错误帧之后的项仍然读到，"
        f"实际 state={result['state']!r}。对应 R4(b)。"
    )


def test_issue6_refresh_all_requires_state_data():
    """R2：refreshAll 不能用 data.online 判刷新成功。"""
    html = webtest.HTML
    assert "if(data.answered" in html, (
        "期望 refreshAll 用 data.answered 判断刷新成功，"
        "实际 HTML 里没有 data.answered。设备在线但拒绝全部读取时"
        "online=true、answered=false、state 为空，旧判据仍会提示「状态已刷新」。对应 R2。"
    )
    assert "if(data.online) toast('状态已刷新', true);" not in html, (
        "期望移除 `if(data.online) toast('状态已刷新', true);`（旧判据）。对应 R2。"
    )


def test_issue6_set_noack_with_notification_is_not_failure(monkeypatch):
    """R3：SET 无 ACK + 写窗口内恰来一条通知，不能被误报为写入失败。

    真机上 SET 不回 ACK 是正常现象，靠写后重读判定；此时若窗口内恰有异步
    推送（如 ANC 变更 40 84），matched=False、error=None 但 decoded 非空，
    旧判据会判「未收到匹配的响应帧」，把成功的写入报成失败。
    """
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        # SET 只回一条通知、不回 ACK
        (0x40, 0x04): _notification(0x40, 0x81, bytes([0x02])),
        # 重读返回目标值 2
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
    }))
    result = webtest.set_anc(2)

    assert result["ok"] is True, (
        "期望 SET 无 ACK + 窗口内有通知时仍按重读值判成功，"
        f"实际 ok={result['ok']!r}、message={result['message']!r}。"
        "旧判据 `matched is False and not write_error` 直接判失败。对应 R3。"
    )
    assert result["message"] == "写入后重读一致", (
        f"期望 message='写入后重读一致'，实际 {result['message']!r}。对应 R3。"
    )


def test_issue6_set_unmatched_other_command_still_fails(monkeypatch):
    """R3 回归基准：收到「其它命令的响应帧」仍必须判失败，不能放宽过头。"""
    _fast_read_state(monkeypatch)
    _install(_simple_device({
        # SET ANC 却收到电量域的响应帧
        (0x40, 0x04): _response(0x1A, 0x01, bytes([1, 82])),
        (0x40, 0x03): _response(0x40, 0x03, bytes([0x02])),
    }))
    result = webtest.set_anc(2)

    assert result["ok"] is False, (
        "期望收到其它命令的响应帧时判失败（数据没对上，不能靠重读兜底），"
        f"实际 ok={result['ok']!r}、message={result['message']!r}。对应 R3 放宽过度。"
    )

