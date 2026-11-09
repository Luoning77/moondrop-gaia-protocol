# PR #1 修复与验证报告

本报告针对上游维护者 **Luoning77** 在 [PR #1](https://github.com/Luoning77/moondrop-gaia-protocol/pull/1)（`Add full web control panel and demo device,fix README`）中提出的 `CHANGES_REQUESTED` 评审意见撰写。评审基于提交 `0a3c868`，结论为「请先修复以下问题，并补充一份可复核的验证报告，再进行合并」，同时要求随修复提交验证报告，至少覆盖修复对应关系、自动化测试结果、DEMO 场景、真机验证状态与构建限制/已知问题五项。

本文件为仓库内文档，随修复提交；评审要求的报告内容以本文件为准，PR 描述只作摘要与指路。

评审提出的 5 条意见（原文摘录，仅压缩表述）：

1. **[P1]** 自定义命令/快捷读取会把设备错误帧当成功（`tools/webtest.py:2040–2060`）。`sendCustom()` / `sendPreset()` 只检查 `step.decoded`，未判断 `decoded.frame_type === 'error'`、`step.matched === false`；请区分成功响应、设备拒绝、无匹配响应及超时，错误帧不能显示成功提示。
2. **[P1]** 无关通知帧会提前终止重试（`tools/webtest.py:648–705`，特别是 `if last_rx: break`）。请仅在得到匹配响应（包括匹配的设备错误）时结束等待/重试；无关通知不应耗尽重试机会，并保留相关帧的诊断信息。
3. **[P2]** SET 明确失败仍可能被「重读值相等」判为成功（`tools/webtest.py:751–786, 972–1109`）。请让明确拒绝/写入失败优先于值相等；仅在**没有明确失败、只是 SET 无 ACK** 时通过重读判定成功，ANC/Gain/LED/LHDC/一拖二、手势与提示音路径都应统一。
4. **[P2]** Kotlin 编解码器开关的未知状态被默认为 false（`src/main/kotlin/com/moondrop/protocol/ResponseParser.kt:80–86`）。请仅接受明确的 `0x00→false`、`0x01→true`，其余返回 `null`，并补测试。
5. **[P2]** Python 接收器缺少异常 Len 的上限与重同步（`tools/webtest.py:582–647`）。建议与 Kotlin `StreamDecoder` 采用一致的限长与重同步约束，并覆盖「坏帧 + 正常帧」及拆包/粘包场景。

5 条意见全部采纳并修复，无「不采纳」项。本报告中的每一条结论都可追溯到具体提交、命令输出或测试用例名；凡未实际执行的检查，均在第 5 节如实标注。真机验证已在 MOONDROP Pudding（固件 `3.5.6`）上完成主要场景，结果见第 4 节，其中包含两处与 DEMO 假设不一致的真机行为。

---

## 1. 修复对应关系

| 评审编号 | 严重级别 | 处理方式 | 改动文件 | 提交 SHA |
|---|---|---|---|---|
| 1 | P1 | 已修复：`send_cmd` 输出显式判定字段，前端不再靠 `step.decoded` 猜成功 | `tools/webtest.py`、`tools/test_webtest.py` | `2b9278a628f1eb8b71c2df6209bbddc12c0f0c47` |
| 2 | P1 | 已修复：删除 `if last_rx: break`，仅匹配帧结束重试；无关通知不消耗重试；全部收帧存入 `frames` | `tools/webtest.py`、`tools/test_webtest.py` | `2b9278a628f1eb8b71c2df6209bbddc12c0f0c47` |
| 3 | P2 | 已修复：抽出 `_classify_write()` 统一三处写入路径，明确失败优先于重读值相等 | `tools/webtest.py`、`tools/test_webtest.py` | `2b9278a628f1eb8b71c2df6209bbddc12c0f0c47` |
| 4 | P2 | 已修复：`parseCodecSwitch()` 改为 `0x00→false / 0x01→true / 其余→null`，新增 8 个单元测试 | `src/main/kotlin/com/moondrop/protocol/ResponseParser.kt`、`src/test/kotlin/com/moondrop/protocol/GaiaCodecTest.kt` | `5d179d6f5cf7f7e839053bda8bd737a644091cb1` |
| 5 | P2 | 已修复：新增 `MAX_PAYLOAD = 512` 与逐字节丢 1 重同步，与 Kotlin `StreamDecoder.drain()` 对齐 | `tools/webtest.py`、`tools/test_webtest.py` | `2b9278a628f1eb8b71c2df6209bbddc12c0f0c47` |

相关提交：

| 提交 | 说明 | 变更规模 |
|---|---|---|
| `2b9278a628f1eb8b71c2df6209bbddc12c0f0c47` | Fix review issues 1-3 and 5: explicit result status, retry, frame resync | `.gitignore`、`tools/test_webtest.py`(新增 730 行)、`tools/webtest.py`，共 1124 insertions / 107 deletions |
| `5d179d6f5cf7f7e839053bda8bd737a644091cb1` | Return null for undefined codec switch states | `ResponseParser.kt`、`GaiaCodecTest.kt`，共 73 insertions / 1 deletion |
| `7719c13ad7c0f23e435ca40cd5504cfd21dae581` | Ignore local zip archives | `.gitignore`，1 insertion |

`.gitignore` 的两处调整（评审未提及，但为让回归测试可复核所必需）：

- `2b9278a` 增加例外规则 `!tools/test_webtest.py`：原有规则 `tools/test_*.py` 会把本测试文件排除在版本库外，导致评审无法看到测试代码。该例外之后的规则是 `tools/run_*.py`、`tools/find_*.py` 等，与 `test_webtest.py` 不冲突，`git ls-files` 已确认 `tools/test_webtest.py` 入库。
- `7719c13` 增加 `/*.zip`：根目录的 `run-pudding.zip` 是本地产物，不应随 PR 提交。`git check-ignore -v run-pudding.zip` 输出 `.gitignore:82:/*.zip	run-pudding.zip`，确认生效。

各条意见的修复要点（依据实际代码，非计划）：

**问题 1**（`tools/webtest.py`，`send_cmd` 第 820–913 行）：`send_cmd` 现在返回显式的 `ok`（bool）、`status`（`ok` / `timeout` / `unparsed` / `device_error` / `unmatched`）、`error_name`、`matched`。`/api/send` 路由（第 2536–2554 行）透传这些字段。前端 `sendCustom()`（第 2297 行起）与 `sendPreset()`（第 2326 行起）改为 `if(!data.ok || !step)` 判定，失败原因由 `replyFailureText()`（第 2105–2117 行）翻译成「设备拒绝 / 收到响应但与本命令不匹配 / 收到无法解析的帧」等文案。原先的 `if(!step || step.error || !step.decoded)` 条件在错误帧场景下为 `true`，这正是评审指出的缺陷。

**问题 2**（`tools/webtest.py`，`send_cmd` 第 843–879 行）：删除 `if last_rx: break`，循环只在 `matched`（含匹配到的设备错误帧）时 `break`；无关通知既不结束重试也不消耗 `retries`；`retries` 上界仍在，不存在无限重发。每次收到的帧都追加到 `received`（`frames` 字段）用于诊断。附带收紧：`/api/send` 按命令决定重试次数（`_send_retries` + `WRITE_CMDS` 白名单，第 1003–1025 行），写命令不重发，读命令重试 1 次；编解码切换 `0x20/0x03`、`0x20/0x04`、`0x20/0x06` 绝不重发（会触发蓝牙重协商把连接打断）。

**问题 3**（`tools/webtest.py`，`_classify_write` 第 954–991 行）：`_set_verify`（第 1045–1067 行）、`set_touch`、`set_tone` 三处统一调用 `_classify_write`。判定优先级为：串口写失败 > 匹配到的设备拒绝 > 有 ACK > 未匹配 > 无 ACK（此时才用重读判定）> 重读失败。「SET 无 ACK 靠重读验证」的既有设计按评审要求保留：仅在没有任何明确失败、单纯无 ACK 时才由 `after == expected` 决定成功。

**问题 4**（`ResponseParser.kt` 第 80–99 行）：`parseCodecSwitch()` 改为 `when` 分支，`0x00 → false`、`0x01 → true`、其余（`0x02`、`0xFF` 等）`→ null`。KDoc 明确写出与官方 APK `V3CodecPlugin.publishLc3State/publishLdacState/publishLhdcState` 中 `bArr[0] == 1` 的差异是**有意为之**：APK 会把设备返回的未定义值静默判为「关闭」，本实现返回 `null` 以区分「确实关闭」与「无法识别」，与同库 `GainLevel` / `AncMode` 的 `fromValue` 行为一致。

**问题 5**（`tools/webtest.py`）：新增模块级常量 `MAX_PAYLOAD = 512`（第 24 行），与 `src/main/kotlin/com/moondrop/protocol/codec/GaiaCodec.kt:19` 的 `MAX_PAYLOAD` 对齐。`_take_frame_ex()`（第 667–695 行）按「帧头 → Vendor(0x1D) → Len 上限 → 是否收全」的顺序校验，返回三态（`ok` / `wait` / `bad`）；`_take_frame()` 与 `_recv_frame()`（第 698–817 行）在 `bad` 时逐字节丢 1 重同步，不用 `buf.find` 跳跃——跳跃会落回同一个错误帧头，与 Kotlin `StreamDecoder.drain()`（第 96 行起）的逐字节策略不一致。`decode_packet()`（第 232–281 行）同样加上限，且上限检查放在 `len(data) < 8 + length` 之前，避免 Len 损坏成 `0xFFFF` 时被误判为「数据未到齐」；`Len = 512` 仍合法。`MockSerial.write()`（第 340 行起）改用同一套切帧逻辑，此前一个坏 Len 会永久污染 `_pending`，之后所有命令都无应答。跨帧吞并（Len 能凑够、却把后续合法帧吃进 payload）也纳入坏帧判定（`_holds_embedded_frame()`，第 640–664 行）。

---

## 2. 自动化测试结果

### 2.1 Python

| 项目 | 内容 |
|---|---|
| 命令 | `python -m pytest tools\test_webtest.py -q`（仓库根目录） |
| 结果 | **20 passed**，耗时 3.11 s（本次写作时复跑 3.12 s / 3.13 s） |
| 修复前基线 | **16 failed / 4 passed**（同一测试文件在评审基线 `0a3c868` 的 `webtest.py` 上运行，约 4～5 s） |
| 编译检查 | `python -m py_compile tools\webtest.py` → exit 0 |
| Python | 3.14.2 |
| pytest | 9.1.1 |
| pyserial | 3.5 |
| 平台 | Windows 10 专业版（10.0.19045） |
| 测试文件 | `tools/test_webtest.py`，730 行，20 个用例 |

测试不依赖真实蓝牙：用实现了 pyserial 子集的 `FakeSerial`（`in_waiting` / `read` / `write` / `flush` / `reset_input_buffer` / `is_open` / `port`）注入应答，因此重试次数、坏帧重同步等断言都来自「实际 write 次数」和「注入字节序列」，不靠 sleep 计时。所有重试相关用例的 `timeout` 取 0.12～0.2 s，全套 20 个用例约 3.1 s 完成。

关键输出片段：

```
$ python -m pytest tools\test_webtest.py -q
....................                                                     [100%]
20 passed in 3.11s
```

```
$ python -m pytest tools\test_webtest.py -v
tools/test_webtest.py::test_issue1_error_frame_not_success PASSED        [  5%]
tools/test_webtest.py::test_issue1_unmatched_frame_not_success PASSED    [ 10%]
tools/test_webtest.py::test_issue2_notification_does_not_stop_retry PASSED [ 15%]
tools/test_webtest.py::test_issue2_matched_error_frame_counts_as_matched PASSED [ 20%]
tools/test_webtest.py::test_issue2_keeps_all_received_frames PASSED      [ 25%]
tools/test_webtest.py::test_issue3_set_rejected_but_state_already_expected PASSED [ 30%]
tools/test_webtest.py::test_issue3_touch_rejected_but_state_already_expected PASSED [ 35%]
tools/test_webtest.py::test_issue3_tone_rejected_but_state_already_expected PASSED [ 40%]
tools/test_webtest.py::test_issue3_set_noack_still_ok PASSED             [ 45%]
tools/test_webtest.py::test_issue5_bad_len_resync PASSED                 [ 50%]
tools/test_webtest.py::test_issue5_bad_len_resync_recv_frame PASSED      [ 55%]
tools/test_webtest.py::test_issue5_split_and_coalesced PASSED            [ 60%]
tools/test_webtest.py::test_decode_packet_oversized_len PASSED           [ 65%]
tools/test_webtest.py::test_decode_packet_accepts_max_len PASSED         [ 70%]
tools/test_webtest.py::test_issue5_bad_vendor_resync PASSED              [ 75%]
tools/test_webtest.py::test_issue5_len_513_resync PASSED                 [ 80%]
tools/test_webtest.py::test_issue5_cross_frame_swallow PASSED            [ 85%]
tools/test_webtest.py::test_issue2_retry_does_not_clear_valid_carry PASSED [ 90%]
tools/test_webtest.py::test_issue5_mockserial_bad_len PASSED             [ 95%]
tools/test_webtest.py::test_issue4_python_summary_unknown_codec PASSED   [100%]
```

用例与评审编号的对应：

| 评审编号 | 用例 |
|---|---|
| 1 | `test_issue1_error_frame_not_success`、`test_issue1_unmatched_frame_not_success` |
| 2 | `test_issue2_notification_does_not_stop_retry`、`test_issue2_matched_error_frame_counts_as_matched`、`test_issue2_keeps_all_received_frames`、`test_issue2_retry_does_not_clear_valid_carry` |
| 3 | `test_issue3_set_rejected_but_state_already_expected`、`test_issue3_touch_rejected_but_state_already_expected`、`test_issue3_tone_rejected_but_state_already_expected`、`test_issue3_set_noack_still_ok` |
| 4 | `test_issue4_python_summary_unknown_codec`（Python 侧镜像防护，Kotlin 侧见 2.2） |
| 5 | `test_issue5_bad_len_resync`、`test_issue5_bad_len_resync_recv_frame`、`test_issue5_split_and_coalesced`、`test_decode_packet_oversized_len`、`test_decode_packet_accepts_max_len`、`test_issue5_bad_vendor_resync`、`test_issue5_len_513_resync`、`test_issue5_cross_frame_swallow`、`test_issue5_mockserial_bad_len` |

**红阶段（修复前）基线**：把测试文件放到评审当时的提交 `0a3c868` 的 `tools/webtest.py` 上运行（仓库外临时目录，不改仓库文件），得到 `16 failed, 4 passed in 4.87s`。4 个通过项均为有意设置的「回归基准」，不是问题复现不出来：`test_issue2_matched_error_frame_counts_as_matched`、`test_issue3_set_noack_still_ok`、`test_issue5_split_and_coalesced`、`test_decode_packet_accepts_max_len`。代表性失败输出：

- 问题 1：`AssertionError: ... decoded.frame_type=error、decoded.payload=[5]，前端现有条件 step && !step.error && step.decoded = True，会弹出「命令已发送」`
- 问题 2：`AssertionError: 期望重试真的发生（初始 1 次 + 重试 1 次 = 2 次 write），实际 write 次数=1；matched=False，最后一次解码 frame_type='notification'`
- 问题 3：`AssertionError: 期望 SET 收到设备错误帧时 ok=False ... 实际 ok=True、message='写入后重读一致'、set_error='参数无效 (5)'、requested=2、after=2`
- 问题 5：`AssertionError: 期望 _take_frame 把 Len=0xFFFF 的坏帧头当作错帧丢弃并重新同步到合法帧 ... 实际 frame=None、rest=FF 04 FF FF 00 1D 41 03 FF 04 00 01 00 1D 41 03 02（缓冲区共 17 字节，远小于声明的 8+65535，且没有可用的超时兜底，会导致本次接收一直等到超时）`

### 2.2 Kotlin

| 项目 | 内容 |
|---|---|
| 命令 | `.\gradlew.bat test --console=plain --offline --rerun-tasks` |
| 结果 | `BUILD SUCCESSFUL`，`4 actionable tasks: 4 executed` |
| 测试计数 | `tests=50 failures=0 errors=0 skipped=0`（原 42 + 新增 8） |
| 测试报告 | `build/test-results/test/TEST-com.moondrop.protocol.GaiaCodecTest.xml` |
| Gradle | 9.4.1（wrapper，`gradle/wrapper/gradle-wrapper.properties`） |
| Kotlin | 2.0.21（`gradle/libs.versions.toml`） |
| JVM | JDK 17.0.4.1（`kotlin { jvmToolchain(17) }`） |

关键输出片段（本次复跑）：

```
> Task :compileKotlin
> Task :compileTestKotlin
> Task :test
BUILD SUCCESSFUL in 8s
4 actionable tasks: 4 executed
```

测试报告 XML 首行：

```xml
<testsuite name="com.moondrop.protocol.GaiaCodecTest" tests="50" skipped="0" failures="0" errors="0"
           timestamp="2026-11-09T11:51:58.394Z" hostname="DESKTOP-0N3LLBN" time="0.341">
```

**关于 `--rerun-tasks`**：第一次执行 `.\gradlew.bat test --offline`（不带 `--rerun-tasks`）时，`:test` 任务为 `UP-TO-DATE`（Gradle 增量判定，实际未执行测试），此时 XML 是上一次的结果，不能作为本次修复的验证证据。因此改用 `--rerun-tasks` 强制重跑，得到 `BUILD SUCCESSFUL in 10s`、`4 actionable tasks: 4 executed`，测试报告 XML 时间戳随之更新为 `2026-11-09T11:45:11Z`，内容为 `tests=50 failures=0 errors=0 skipped=0 time=0.395`。本报告表格中的 `11:51:58Z / time=0.341` 是撰写本报告时再次强制重跑的结果，与 `11:45:11Z` 那次一致（同为 50 全绿）。结论以「用 `--rerun-tasks` 强制重跑确认」为准，不采信 UP-TO-DATE 的旧结果。

**红绿验证**：把 `parseCodecSwitch()` 临时回退成旧实现（`return packet.payload[0] == 0x01.toByte()`）后重跑，`BUILD FAILED`，`tests=50 failures=4`，失败用例正是 0x02/0xFF 分支的 4 条：

```
parse codec switch unknown value 0x02 returns null()          expected: <null> but was: <false>
parse codec switch unknown value 0xff on lc3 returns null()   expected: <null> but was: <false>
parse codec switch unknown value 0xff on ldac returns null()  expected: <null> but was: <false>
parse codec switch unknown value 0xff on lhdc returns null()  expected: <null> but was: <false>
```

恢复为新实现后重跑，50 条全绿。该回退实验在仓库外的临时副本中进行（复制 `src/`、`gradle/`、`build.gradle.kts`、`settings.gradle.kts`、`gradlew*` 到临时目录），未修改仓库内的任何 Kotlin 文件。

新增 8 个用例（`GaiaCodecTest.kt` 第 303–359 行）：

| 用例名 | 覆盖点 |
|---|---|
| `parse codec switch 0x00 is false and 0x01 is true` | LC3/LDAC/LHDC 三入口的合法值映射 |
| `parse codec switch unknown value 0x02 returns null` | 0x02 独立断言（不与 0xFF 合并，避免只处理一个分支的 bug 漏测） |
| `parse codec switch unknown value 0xff on lc3 returns null` | 0xFF × LC3 |
| `parse codec switch unknown value 0xff on ldac returns null` | 0xFF × LDAC |
| `parse codec switch unknown value 0xff on lhdc returns null` | 0xFF × LHDC |
| `parse codec switch on error frame returns null` | Cmd 错误位（`0x81` / `0x82` / `0x85`） |
| `parse codec switch on notification returns null` | Feature 无响应位（`0x20`） |
| `parse codec switch empty payload returns null` | 空 payload 分支（此前无测试） |

原有的 `parse codec status by command id` 保持通过。

---

## 3. DEMO 场景验证

启动方式（每轮验证后进程均已停止，未留后台服务）：

```
python tools/webtest.py --demo --web-port 18099
python tools/webtest.py --demo --demo-noack --web-port 18097
python tools/webtest.py --demo --demo-latency 0.1 --web-port 18095
```

接口结果通过 `curl.exe` / `Invoke-RestMethod` 读取 JSON 后核对：

| 模式 | 场景 | 预期 | 实测 |
|---|---|---|---|
| `--demo` | `/api/state` 全量读取 | online=true，状态齐全 | online=true，固件 `3.5.2-demo` |
| `--demo` | 正常读 `F=0x40 C=0x03` | ok=true | ok=true，status=ok，matched=true |
| `--demo` | 设备拒绝 `F=0x40 C=0x7F` | 失败 | ok=false，status=device_error，error_name="不支持的命令 (1)" |
| `--demo` | `/api/set/anc?mode=2` | ok=true | ok=true，message="写入后重读一致" |
| `--demo` | `/api/set/anc?mode=9`（越界） | 参数错误 | HTTP 400，`{"error": "参数 mode 超出范围 0..4"}` |
| `--demo-noack` | `/api/state` | online=true | online=true，anc=1 |
| `--demo-noack` | `/api/set/anc?mode=3` | ok=true，SET 无 ACK | ok=true，message="写入后重读一致"；SET 步骤 status=timeout、matched=False、no_reply_ok=True |
| `--demo-noack` | `/api/set/gain?level=2` | ok=true | ok=true，message="写入后重读一致" |
| `--demo-latency 0.1` | `/api/state` | online=true | online=true |
| `--demo-latency 0.1` | `/api/set/led?on=0` | ok=true | ok=true，after=0 |
| `--demo-latency 0.1` | 设备拒绝 `F=0x40 C=0x7F` | 失败 | ok=false，error_name="不支持的命令 (1)" |

修复前的对照（同一场景、旧版 `webtest.py`）：`/api/send?feature=0x40&cmd=0x7F` 返回体只有 `keys=['decoded', 'error', 'rx_raw', 'steps', 'tx']`，`decoded.frame_type=error`，`step.error=None`，即前端旧条件 `!step.error && step.decoded` 为 `True`，页面会提示「命令已发送」。修复后同一请求返回 `ok=false`、`status=device_error`、`error_name="不支持的命令 (1)"`。

DEMO 的假设备是简化模型（`MockSerial`，`tools/webtest.py` 第 284 行起），其应答逻辑与真实固件不完全等价；表中「实测」只代表本仓库假设备与本地 Web API 链路的行为，不构成真机结论。真机验证结果与两者的差异见第 4 节。

评审要求覆盖的四类场景（成功 / 设备拒绝 / 超时 / 通知抢先到达）分别落到哪里，如实说明如下：

| 评审要求的场景 | 验证方式 | 说明 |
|---|---|---|
| 成功 | DEMO 实测 | 上表 `--demo`、`--demo-noack`、`--demo-latency` 各行的 ok=true 项 |
| 设备拒绝 | DEMO 实测 | 上表 `F=0x40 C=0x7F` 各行，返回 `status=device_error`、`error_name="不支持的命令 (1)"` |
| 超时 | DEMO 实测（仅 SET 无 ACK 一种） | `--demo-noack` 下 `/api/set/anc?mode=3` 的 SET 步骤 status=timeout、matched=False；`MockSerial` 对已知命令都会应答、对未知命令回错误帧，因此 DEMO 模式下无法构造「读命令完全无响应」的超时 |
| 通知抢先到达 | **仅单元测试，未在 DEMO 中复现** | `MockSerial` 不会在响应前主动插播异步通知，DEMO 模式下无法构造该时序。该场景由 `test_issue2_notification_does_not_stop_retry`（先回无关通知、第二次 write 才回目标响应，断言 write 次数=2 且 matched=True）与 `test_issue2_keeps_all_received_frames`（断言通知帧与响应帧都保留在 `frames`）覆盖 |
| 无匹配响应（`status=unmatched`） | **仅单元测试，未在 DEMO 中复现** | `MockSerial` 对未知命令回「不支持的特性/命令」错误帧（属于 `device_error`），对已知命令总回匹配帧，因此 DEMO 下拿不到 `unmatched`。实测传 `feature=0x41`（响应位 Feature）会被当作未知请求回 `status=timeout`，也不是 `unmatched`。该状态由 `test_issue1_unmatched_frame_not_success` 覆盖 |

即「通知抢先到达」与「无匹配响应」两类**没有 DEMO 级证据**，只有单元测试证据；如果复审要求 DEMO 级别的复现，需要给 `MockSerial` 增加「响应前先插播通知」和「回无关响应帧」的可编程开关——本轮未做，因为那属于修改 DEMO 假设备的行为，超出了本次修复的范围。

---

## 4. 真机验证状态

**已验证（部分场景）。**

### 4.1 设备与环境

| 项 | 值 |
|---|---|
| 设备 | MOONDROP Pudding（MD-TWS-056） |
| 固件版本 | `3.5.6`（`F=0x00 C=0x05` 读取，ASCII `33 2E 35 2E 36`） |
| 连接方式 | Windows 蓝牙 SPP，RFCOMM 串口 |
| 串口 | `COM8`，`BTHENUM\{00001101-...}_VID&000105D6_PID&000A`（VID `0x05D6` = 水月雨） |
| 波特率 | 115200 |
| 自动检测 | `python tools/webtest.py --find-port` → `COM8`（正确选中，未误选同机的 `COM7` 本地虚拟口） |

### 4.2 只读读取（13 项）

均通过真实串口收发验证，`status=ok`、`matched=true`：

| 读取项 | 命令 | 实测结果 |
|---|---|---|
| 应用/固件版本 | `00 05` | `3.5.6` |
| 支持的特性 | `00 01` | `00 00 02 01 01 05 01 0D 01 0E 01 0F 01 10 01 13 01 14 01 16 01 20 01` |
| 传输信息 | `00 0C` P=`02` | `02 00 00 00 80` |
| 左耳序列号 | `00 14` | ASCII `20560023326101203277` |
| 右耳序列号 | `00 15` | ASCII `20560023326101204688` |
| 电量 | `1A 01` | 左耳 100%、右耳 100%、充电盒 `FF`（不可用） |
| ANC 模式 | `40 03` | `04`（降噪） |
| ANC 切换配置 | `40 29` | `01 01 01 01 00` |
| 增益 | `1E 01` | `01`（中） |
| 指示灯 | `26 01` | `01`（开） |
| 手势 | `2C 02` | `11 23 77 45 66` |
| 提示音 | `1C 01` | 开 / 音量 64 / 组号 1 |
| LHDC | `20 05` | `00`（关） |
| 一拖二 | `28 01` | `01`（开） |

**真机不支持的命令**（返回 `状态错误` 或 `不支持的命令`，与预期一致）：

| 命令 | 真机返回 |
|---|---|
| `00 03` 设备序列号 | 无响应（超时） |
| `00 00` GAIA 版本 | 无响应（超时） |
| `20 01` LC3 | `21 81 01` 不支持的命令 (1) |
| `20 02` LDAC | `21 82 01` 不支持的命令 (1) |

### 4.3 写入路径（幂等验证，写回当前值，未改变用户设置）

| 项 | 结果 |
|---|---|
| SET 是否回 ACK | **回 ACK**。`40 04 04` → `41 04 04`；`1E 02 01` → `1F 02 01`；`26 02 01` → `27 02 01`。连续 5 次重复验证一致 |
| 面板 `set_anc` / `set_gain` / `set_led` / `set_tone` | 全部 `ok=true`、`message="写入后重读一致"`，写入前置步骤 `status=ok`、`matched=true` |
| 手势写入 | `11 23 77 45 66` 写回，`ok=true` |
| 设备拒绝（不支持的 Cmd） | `F=0x40 C=0x7F` → `41 FF 01`，判定 `ok=false`、`status=device_error`、`error_name="不支持的命令 (1)"` |
| 越界参数 | `anc mode=9`、`gain=9`、`led=9` 在 API 层被拦截为 HTTP 400；直接发帧时设备**回正向 ACK 但值不生效**（读回仍为原值），详见 4.5 |

### 4.4 面板端到端（真实串口 + HTTP）

`python tools/webtest.py COM8 --web-port 18070`：

| 接口 | 实测 |
|---|---|
| `/api/status` | `connected=true`、`port=COM8`、`demo=false` |
| `/api/state` | `online=true`，耗时 **0.67 s**，读出 11 项状态；仅 LC3/LDAC 两项 `device_error`（设备不支持） |
| `/api/send?feature=64&cmd=3` | `ok=true`、`status=ok`、`matched=true` |
| `/api/send?feature=64&cmd=127` | `ok=false`、`status=device_error`、`error_name="不支持的命令 (1)"` |
| `/api/send?feature=96&cmd=1` | `ok=false`、`status=timeout`、`error="无响应"` |
| `/api/set/anc`、`/api/set/gain`、`/api/set/led`、`/api/set/tone`、`/api/set/touch` | 全部 `ok=true`、`message="写入后重读一致"` |
| 参数校验 | `mode=9` / `level=9` / `on=9` 均返回 HTTP 400 |

验证结束后设备状态与验证前一致（ANC=降噪、增益=中、指示灯=开、LHDC=关、一拖二=开），未改变用户设置。

### 4.5 真机发现的三处与 DEMO 不一致的行为

1. **SET 命令真机会回 ACK**，而 `--demo-noack` 假设的是「SET 不回 ACK」。因此「写后重读」在真机上不是唯一判定路径——`_classify_write()` 的「有 ACK 时采信 ACK」分支在真机上同样生效，两个分支都验证到了。**这意味着 `--demo-noack` 是一个比真机更严格的测试场景，不是真机真实行为。**

2. **设备对未定义参数值不报错，回正向 ACK 但不生效**：`1E 02 09`（增益=9）返回 `1F 02 09`，但读回仍是原值 `01`；`26 02 09`、`40 04 09` 同理。设备不做参数校验，把校验责任留给上位机。当前面板的 `_req_int` 范围校验（HTTP 400）是**必要的第一道防线**，本轮已验证有效。

3. **连续写同一 ANC 值偶发 `状态错误 (6)`**：在无间隔连发 5 个不同模式时，`anc=1/2/3/4` 的第 2 次尝试各出现一次 `41 84 06`（状态错误）。将间隔放宽到 1.5 s 后，每个模式连续 3 次全部成功。判定为设备状态机切换中的短暂拒绝，不是确定性约束；面板每次操作间隔远大于该值，不影响正常使用。**该行为在 DEMO 中无法复现，属真机特有。**

### 4.6 仍未在真机验证的场景

| 场景 | 原因 |
|---|---|
| 通知抢先到达（问题 2 的触发条件） | 实际观测到的通知只有一条：`40 81 04`（ANC 状态变更推送，在 SET anc=0 被拒后出现）。未能构造「设备在查询响应前主动推送通知」的时序 |
| 真实链路 Len 字段损坏 | 蓝牙 SPP 链路稳定，无法主动注入坏帧；该场景由单元测试与 DEMO 假串口覆盖 |
| 蓝牙重协商影响 | 未验证 `20 03/04/06` 在重连场景下的行为；且真机 LC3/LDAC 直接返回「不支持的命令」，该功能在当前固件上不可用 |
| 一拖二、提示音的实际听感效果 | 仅验证读写协议层，未做听觉确认 |

原始 TX/RX 十六进制记录见本节各表；完整逐条日志在验证时已留存，如需可另行提供。

---

## 5. 构建限制与已知问题

### 5.1 Gradle 代理

仓库 `gradle.properties` 写死了固定代理：

```properties
systemProp.http.proxyHost=127.0.0.1
systemProp.http.proxyPort=7890
systemProp.https.proxyHost=127.0.0.1
systemProp.https.proxyPort=7890
```

本机实测结果：

| 现象 | 实测 |
|---|---|
| `127.0.0.1:7890` 是否监听 | 未监听（TcpClient 连接超时） |
| `127.0.0.1:7897` 是否监听 | 监听（本机实际使用的代理端口） |
| PowerShell 未加引号传 `-Dhttps.proxyPort=7897` | 构建直接失败：`Task '.proxyPort=7897' not found in root project 'moondrop-pudding-protocol'`。用一个探测批处理确认根因：PowerShell 调用 `.bat` 时把该参数拆成了 `-Dhttps` + `.proxyPort=7897`（cmd.exe 下则完整传递）。这很可能是「命令行 `-D` 压不过 `systemProp`」这一印象的来源。 |
| PowerShell 加引号传 `'-Dhttps.proxyPort=7897'` | 通过 init script 打印 system property 验证：`https.proxyPort=7897`，**覆盖成功**，`systemProp` 不是不可覆盖的 |
| 同上，但 `--no-daemon` | 同样为 `7897`，排除 daemon 缓存旧值的干扰 |
| cmd.exe 中未加引号传 `-Dhttps.proxyPort=7897` | 同样为 `7897`，覆盖成功 |

结论（按实测修正）：在 PowerShell 里按常规写法传 `-D` 时，`systemProp.*` 实际生效，代理仍指向不可用的 7890，构建在配置阶段失败——从结果看确实「压不过」。但根因不是 Gradle 的优先级，而是 PowerShell 调用 `.bat` 时把 `-Dhttps.proxyPort=7897` 拆成了两个 token，Gradle 只收到残缺参数。换成加引号的写法（或在 cmd.exe 下）即可正常覆盖。由于这一写法差异对使用者不直观、且 `gradlew.bat` 的报错（`Task '.proxyPort=7897' not found`）指向任务名而非参数，实际使用中仍建议按「`--offline` 或临时改 `gradle.properties`」处理。

本次验证的规避方式：**不改仓库配置**，使用 `--offline` 配合已缓存的依赖完成构建（`~/.gradle/wrapper/dists/gradle-9.4.1-bin` 已存在，`gradle-9.4.1-bin.zip.ok` 标记完整；首次构建需下载 130MB 发行包，本次未触发下载）。若需要在干净环境联网构建，可选任一方式：临时修改 `gradle.properties` 的代理端口；或用 PowerShell 加引号的 `-Dhttps.proxyHost=127.0.0.1 '-Dhttps.proxyPort=7897'`（注意 http/https 两组都要传，实测只传 https 时 `http.proxyPort` 仍为 7890）。该环境问题不随 PR 修改 `gradle.properties`，避免把个人代理配置带入仓库。

### 5.2 未运行的检查

| 检查 | 状态 | 原因 |
|---|---|---|
| `./gradlew build`（完整构建） | **未运行** | 评审要求「Kotlin 至少运行 `./gradlew build`（含单元测试）」，本次实际只运行了 `test`。原因：任务范围仅涉及单元测试；`build` 比 `test` 多出的主要是 `assemble` 打包步骤，而本仓库 `build.gradle.kts` 未配置 detekt/ktlint 等静态检查插件。需要说明的是，本次 `test` 执行过程中 `:jar` 已被触发（构建输出含 `> Task :jar`），但 `build` 任务本身未执行，故不应据此推断「完整构建成功」。 |
| Android 端集成验证 | **未做** | 本仓库是纯 Kotlin 协议库（`build.gradle.kts` 仅应用 `org.jetbrains.kotlin.jvm`，`jvmToolchain(17)`），无 Android 模块，不存在该类验证对象。 |
| Python 3.8 真实环境验证 | **未做** | 代码按 Python 3.8+ 编写（未使用 3.9+ 语法特性），但只在 Python 3.14.2 上实际运行过。 |
| 真机验证 | **部分完成** | 见第 4 节：只读读取、写入路径、面板端到端已验证；通知抢先到达、Len 损坏、蓝牙重协商未验证。 |

### 5.3 已知问题与取舍

- `MAX_PAYLOAD = 512` 是本仓库自选的阈值，GAIA 协议文档未规定该上限（`tools/webtest.py` 第 20–24 行注释已写明）。选 512 是为了与 Kotlin `GaiaCodec.MAX_PAYLOAD` 保持一致；若真机存在大于 512 字节的合法 payload，该上限会误判为坏帧，需真机验证后调整。
- `_holds_embedded_frame()` 是启发式判定，触发条件刻意收得很窄（内嵌帧结尾必须正好等于本帧 payload 结尾，或紧接下一个 `FF 04` 帧头），以避免误杀 payload 中偶然含 `FF 04` 的正常帧；但不存在「必然正确」的形式化证明，真机出现异常大 payload 时需复核。
- 写命令不重发是有意取舍：网络抖动导致写命令超时时仍判失败，也不会自动重发，以避免重复执行与编解码重协商。这是安全性优先于成功率的取舍，非缺陷。
- 重试路径中存在 `time.sleep(0.08)` 的固定间隔，以及 `_set_verify` 中 `time.sleep(0.2)` 的写后等待。前者是重试间隔，后者是「写后等待设备生效」，用于真机时序；测试通过缩短 `timeout` 而非消除该等待来控制耗时（全套 20 用例约 3.1 s）。
- `MockSerial` 是简化假设备，只覆盖面板用到的命令子集，不能替代真实固件的协议一致性测试。

---

## 6. 附加修复（评审未提出，一并修正）

以下问题是在修复评审 5 条意见的过程中，由回归测试与代码复核发现的同类缺陷，已一并修正；每项都有对应的失败表现（测试或复现路径）：

| 编号 | 问题 | 处理 | 位置 | 覆盖测试 |
|---|---|---|---|---|
| A1 | `_error_of()` 不校验 `matched`：其它命令的错误帧会被误算成本次 SET 的拒绝理由 | 增加 `result.get("matched") is not True → None` 校验 | `webtest.py` 第 925–940 行 | `test_issue2_matched_error_frame_counts_as_matched`（断言 `_error_of(result) == "参数无效 (5)"`） |
| A2 | `no_reply_ok` 无条件置位：真实的串口写失败也被标成「无 ACK（正常）」，前端日志因此显示为正常 | 改为条件置位，仅当 `matched is False` 且 `error == '无响应'` 且无 `decoded` 时标记（`_write_no_reply_ok`） | `webtest.py` 第 943–951 行，`_set_verify` 第 1055–1056 行、第 1279–1280、1327–1328 行 | `test_issue3_set_noack_still_ok`（应保持 no_reply_ok=True）、问题 3 三条拒绝用例（no_reply_ok 不得掩盖失败） |
| A3 | `_rx_carry.clear()` 位于重试循环内：重试会把上一轮已收到但未交付的合法帧清掉，重试反而加速丢帧 | 只清物理缓冲 `ser.reset_input_buffer()`，carry 改为每次 `send_cmd` 开始时清一次，重试时保留 | `webtest.py` 第 838–842 行（开头发清一次）与第 848–850 行（重试只清物理缓冲） | `test_issue2_retry_does_not_clear_valid_carry` |
| A4 | `MockSerial.write()` 用同一套无上限切帧：一个坏 Len 会永久污染 `_pending`，之后所有命令都无应答 | 复用 `_take_frame_ex()` 的三态逻辑，坏帧丢 1 字节重同步，`wait` 时保留半帧 | `webtest.py` 第 340–361 行 | `test_issue5_mockserial_bad_len` |
| A5 | `/api/send` 的 `retries` 固定为默认值，问题 2 放宽重试窗口后写命令可能被重复执行 | 新增 `WRITE_CMDS` 白名单与 `_retry_safe()` / `_send_retries()`，写命令 0 次重试、读命令 1 次 | `webtest.py` 第 1000–1025 行，`/api/send` 第 2540 行 | 由 `_send_retries` 行为验证（`(0x40,0x04)→0`、`(0x40,0x03)→1`、`(0x20,0x03)→0`、`(0x20,0x01)→1`），未单独建用例 |
| A6 | `_summarize()` 把编解码域任意非零值都显示为「开」，与问题 4 的三态语义不一致 | 改为 `0x00 → 关`、`0x01 → 开`、其余 → `未知(0xNN)` | `webtest.py` 第 179–190 行 | `test_issue4_python_summary_unknown_codec` |

另外，问题 5 的修复过程中还顺带修正了两处（已并入第 1 节问题 5 描述，不重复计数）：`decode_packet()` 的 Len 上限检查顺序（必须在「长度不足」判断之前），以及 Vendor 校验必须先于长度校验（否则 Len 刚好凑够时会把后续合法帧吞进 payload）。

---

## 7. 后续计划

1. **补齐真机验证**：第 4 节已完成只读读取、写入路径与面板端到端，以下场景尚未在硬件上确认，按优先级排列：
   - 通知抢先到达：实测只观察到一条 `40 81 04`（ANC 变更推送），未构造出「查询响应前主动推送」的时序；
   - 真实链路 Len 字段损坏与半帧/粘包：蓝牙 SPP 链路稳定，无法主动注入；
   - 蓝牙重协商对 `20 03/04/06` 的影响：当前固件 LC3/LDAC 直接返回「不支持的命令」，该功能暂不可用；
   - 一拖二与提示音的实际听感：仅验证协议层读写。

   已确认的真机行为（第 4.5 节）与 DEMO 假设有两处差异，后续若调整 DEMO 假设备应以此为准：真机 SET **会**回 ACK；设备对越界参数**回正向 ACK 但不生效**（校验责任在上位机）。
2. **完整构建**：在联网或临时改代理的条件下执行 `./gradlew build`（含单元测试与打包），确认 `build` 任务本身通过，补上第 5.2 节标注的空缺。
3. **EQ 语义与基础域 `0x00` 命令语义的后续校正**：依据仓库外的逆向审计记录 `D:\DSHarness\moondrop\_inspect\apk_control_id_audit.md`（该文件不随 PR 提交），至少包含：
   - 基础域 `0x00`：`0x07` 在 APK 中是「注册通知」而非「EQ 状态」，`0x0C`/`0x0D` 是传输信息/传输参数（`0x0D` 为写），`0x14`/`0x15` 分别是左耳/右耳序列号而非通用序列号/设备 ID；当前 `PRESETS`、`MockSerial` 基础域与 `_summarize` 的标签需同步 APK 语义；
   - EQ 域 `0x0A`：`0x00` 为 EQ 状态、`0x03` 为写 EQ Set、`0x05`/`0x06` 为读/写用户配置，与现有「带宽/参数读/参数写」的命名不完全一致，需按 `V3MusicProcessingPlugin` 重新命名并复核 `0x05`/`0x06` 的读写方向。
4. **同类解析器未知值语义**：`parseCodecSwitch` 已改为三态，但其它布尔型解析器仍会把未定义值静默归入某个合法状态，本轮按「不改协议常量、不改其它解析器」的范围约束未改动：
   - `parseLed`（`ResponseParser.kt:102–108`）与 `parseOnebringtwoState`（第 131–137 行）用 `(payload[0] and 0x01) == 1` 判定，`0x02` 之类的未定义值会被静默判为 false；
   - `parseVoiceConfig`（第 111–117 行）对 enabled 字段同样做 `and 0x01` 掩码；
   - `parseTouchConfig`（第 120–128 行）原样透传 5 字节，不做取值校验。

   建议下一轮按 `parseCodecSwitch` 的三态模式（`0x00 → false`、`0x01 → true`、其余 → `null`）统一处理并补测试。
