# MOONDROP Pudding 蓝牙协议逆向分析

> 注：本文是早期逆向记录，部分 Feature 命名已被后续 APK/真机取证修正：
> `0x2C` 实为手势 TOUCHV2（不是电池）、`0x1A` 为电池、`0x1C` 为提示音、
> `0x26` 为指示灯、`0x28` 为一拖二、`0x20 cmd 0x05` 为 LHDC。
> 协议以实现与 README 为准，早期结论保留作过程记录。
> 另：`Len` 以 payload 字节数为准（feature/cmd 不计入），第 4 字节抓包始终为 `0x00`。

> 基于 btsnoop HCI 抓包（5 次）+ DEX 反编译分析 + 杰理 SDK 文档 + 实测验证
>
> 设备: MOONDROP Pudding (MD-TWS-056)，杰理芯片 (Jieli VID=0x05D6, PID=0x000A)
> 固件: 3.5.2 | MAC: D2:D1:13:AB:67:2
> APP: MOONDROP Link v2.23.1c (Flutter + Conexant EQ SDK + 高通 GAIA V3 SDK)
> 服务器: `http://47.104.217.27:8080/venus`（当前 502，已迁移或下线）

---

## 1. 协议格式（已确认）

```
FF 04 [Len:2 BE] [Seq:1] [Vendor:1] [Feature:1] [Cmd:1] [Payload...]
```

| 字段 | 偏移 | 大小 | 说明 |
|------|------|------|------|
| SOP | 0 | 2 | 固定 `FF 04` |
| Len | 2 | 2 BE | = Payload.size（feature/cmd 不计入） |
| Seq | 4 | 1 | 抓包始终为 `0x00`；早期记为“每包递增”，也可能是 16 位 Vendor `0x001D` 的高字节，待确认 |
| Vendor | 5 | 1 | 固定 `0x1D`（杰理 Vendor ID 低字节） |
| Feature | 6 | 1 | 功能域 ID |
| Cmd | 7 | 1 | 功能域内命令号 |
| Payload | 8 | 变长 | 命令参数 |

**总包长** = 8 + Payload.size

**响应规则**：响应的 Feature = 请求的 Feature | 0x01（最低位置 1）

**Trailing Byte（存疑）**：早期记录称 TX 包末尾可能多 1 字节（`0x9A`/`0x29`），但现有抓包样本、`webtest.build_tx` 与 `GaiaCodec.encode` 都没有该字节。若真机上确实存在，应视为 Len 之外的多余字节并在解析时忽略。

---

## 2. Feature ID 一览

| Feature | 响应 Feature | 用途 | 状态 |
|---------|-------------|------|------|
| 0x00 | 0x01 | 基础查询（固件版本、序列号、设备ID、配置、设备状态） | ✓ 已确认 |
| 0x0A | 0x0B | EQ 参数读写（频率/gain/Q 编码已破解） | ✓ 实测验证 |
| 0x1A | 0x1B | 电池电量（早期记为“设备管理”） | ✓ 实测验证 |
| 0x1C | 0x1D | 提示音（开关/音量/组号） | ✓ 协议总表确认 |
| 0x1E | 0x1F | Gain 增益控制 | ✓ 实测验证 |
| 0x20 | 0x21 | 编解码器（LC3/LDAC/LHDC） | ✓ 已确认 |
| 0x26 | 0x27 | 指示灯开关（早期记为“固件校验”） | ✓ APK 确认 |
| 0x28 | 0x29 | 一拖二（状态/超时/设备列表；早期记为配对设备信息） | ✓ APK 确认 |
| 0x2C | 0x2D | 手势 TOUCHV2（5 字节 × 左右耳半字节；早期误记为电池通知） | ✓ APK + 真机确认 |
| 0x40 | 0x41 | ANC 降噪控制 | ✓ 实测验证 |

> 早期单独记录的 `0x27` RX `00` 应视为 `0x26` 指示灯查询的响应（响应 Feature = 请求 Feature | 0x01），不再单列。

### DEX 反编译发现但 btsnoop 未见的可能功能

APP 反编译（MOONDROP Link v2.23.1c）显示使用了高通 GAIA V3 SDK，内置以下插件：

| 插件 | 说明 | 备注 |
|------|------|------|
| `V3PowerControlPlugin` | 电源控制 | 可能走 BLE |
| `V3PowerTimeoutPlugin` | 电源超时 | 可能走 BLE |
| `V3StatisticsPlugin` | 统计信息 | 可能走 BLE |
| `LedPublisher` | LED 控制 | 可能走 BLE |
| `VoicePublisher` | 语音提示 | 可能走 BLE |
| `VoiceUIPublisher` | 语音 UI | 可能走 BLE |
| `BatteryPublisher` | 电量 | SPP 已有 0x1A/0x1B |
| `ANCPublisher` | ANC (AncV2) | SPP 已验证可用 |
| `V3SpatialAudioPlugin` | 空间音频 | ❌ 此设备不支持 |
| `UpgradePublisher` | 固件升级 | ❌ 需要水月雨服务器，不使用 |

---

## 3. 已确认命令详情

### 3.1 基础查询 (Feature=0x00)

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x01 | 支持的命令列表 | (空) | 命令列表（格式待确认） | ✓ |
| 0x05 | 固件版本 | (空) | ASCII 字符串，如 "3.5.2" | ✓ |
| 0x07 | 子命令查询 | 子命令 ID | 响应数据 | ⚠️ 功能待确认 |
| 0x0C | 配置查询 | 参数 ID | 配置值 | ✓ |
| 0x0D | 设备状态 | 待解析 | `07 00 00 00 04` | ✓ |
| 0x13 | 未知查询 | (空) | `03` | ⚠️ 仅见一次 |
| 0x14 | 序列号 (L) | (空) | ASCII 字符串 | ✓ |
| 0x15 | 设备 ID (R) | (空) | ASCII 字符串 | ✓ |

#### 配置查询 (Cmd=0x0C) 参数 ID

| 参数 ID | RX Payload | 含义 |
|---------|-----------|------|
| 0x02 | `00 00 00 80` | ⚠️ 不确定 |
| 0x03 | `00 00 00 80` | ⚠️ 不确定 |
| 0x04 | `00 00 00 80` | ⚠️ 可能是音频配置标志位 |
| 0x06 | `00 00 00 01` | ⚠️ 不确定 |

---

### 3.2 ANC 控制 (Feature=0x40)

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x03 | ANC 状态查询 | (空) | 1 字节：当前模式 | ✓ |
| 0x04 | ANC 模式设置 | 1 字节：目标模式 | 1 字节：确认模式 | ✓ |
| 0x29 | 可用模式查询 | (空) | 5 字节：各模式可用性 | ✓ |
| 0x81 | ANC 状态通知 | — | 1 字节：新模式值 | ⚠️ 异步推送 |
| 0x84 | 错误通知 | — | 1 字节：错误码 | ⚠️ 异步推送 |

#### ANC 模式值（实测确认）

| 值 | 模式 | 状态 | 说明 |
|----|------|------|------|
| 0x00 | 关闭 | ✓ | |
| 0x01 | 自适应 | ✓ | 降噪子模式 |
| 0x02 | 通透 | ✓ | 独立 ANC 模式 |
| 0x03 | 抗风噪 | ✓ | 降噪子模式 |
| 0x04 | 降噪（恢复上次子模式） | ✓ | 降噪组入口 |

**降噪组逻辑**：
- `0x04` 是降噪组入口，SET 后恢复上次使用的子模式（0x01 或 0x03）
- `0x02`（通透）是独立模式，不在降噪组内
- `0x01`（自适应）和 `0x03`（抗风噪）是降噪组内的子模式

#### ANC 实测交互（抓包 2 验证）

```
→ FF 04 00 00 00 1D 40 03          ← FF 04 00 01 00 1D 41 03 04  (初始: 降噪组入口)
→ FF 04 00 01 00 1D 40 04 00       ← FF 04 00 01 00 1D 41 04 00  ✓ 关闭
→ FF 04 00 01 00 1D 40 04 01       ← FF 04 00 01 00 1D 41 04 01  ✓ 自适应
→ FF 04 00 01 00 1D 40 04 03       ← FF 04 00 01 00 1D 41 04 03  ✓ 抗风噪
→ FF 04 00 01 00 1D 40 04 01       ← FF 04 00 01 00 1D 41 04 01  ✓ 自适应
→ FF 04 00 01 00 1D 40 04 03       ← FF 04 00 01 00 1D 41 04 03  ✓ 抗风噪
→ FF 04 00 01 00 1D 40 04 01       ← FF 04 00 01 00 1D 41 04 01  ✓ 自适应
```

#### 错误码

| 码 | 含义 |
|----|------|
| 0x06 | ANC 设置失败（模式不支持或状态冲突） |

---

### 3.3 Gain 控制 (Feature=0x1E)

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x01 | Gain 查询 | (空) | 1 字节：当前级别 | ✓ |
| 0x02 | Gain 设置 | 1 字节：目标级别 | 1 字节：确认级别 | ✓ |

#### Gain 级别（实测确认）

| 值 | 级别 |
|----|------|
| 0x00 | 高 (High) |
| 0x01 | 中 (Medium) |
| 0x02 | 低 (Low) |

---

### 3.4 编解码器 / LC3 / LDAC / LHDC 控制 (Feature=0x20)

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x01 | LC3 状态查询 | (空) | 1 字节 | ✓ 实测确认 |
| 0x02 | LDAC 状态查询 | (空) | 1 字节：0x01=开, 0x00=关 | ✓ 协议总表确认 |
| 0x03 | LC3 开关设置 | 1 字节：0x00=关, 0x01=开 | 1 字节：确认 | ✓ 协议总表确认 |
| 0x04 | LDAC 开关设置 | 1 字节：0x00=关, 0x01=开 | 1 字节：确认 | ✓ 协议总表确认 |
| 0x05 | LHDC 状态查询 | (空) | 1 字节：0x01=开, 0x00=关 | ✓ 实测确认（早期误记为 LDAC） |
| 0x06 | LHDC 开关设置 | 1 字节：0x00=关, 0x01=开 | 1 字节：确认 | ✓ btsnoop 确认 |

#### LHDC 开关 btsnoop 验证

```
→ FF 04 00 00 00 1D 20 05          ← FF 04 00 01 00 1D 21 05 01  (LHDC ON)
→ FF 04 00 01 00 1D 20 06 00       ← FF 04 00 02 00 1D 21 06 00  ✓ Set OFF
→ FF 04 00 00 00 1D 20 05          ← FF 04 00 01 00 1D 21 05 00  (LHDC OFF)
```

> 注：上面 SET 回包记录为 Len=2 但只写出 1 字节 payload（`00`），与 `Len = payload.size` 不符，疑似记录截断/漏字节；如要以该样本为准，应回看 btsnoop 原始帧确认。

---

### 3.5 电池电量 (Feature=0x1A)

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x00 | 查询支持的电池 | (空) | `01 02` | ✓ |
| 0x01 | 查询指定电池 | `[ID...]`（示例 `01 02`） | `[ID:1][level:1]...` | ✓ 实测验证 |

#### 电量数据（Feature=0x1A → 响应 0x1B）

```
→ FF 04 00 02 00 1D 1A 01 01 02    TX 查询
← FF 04 00 06 00 1D 1B 01 01 64 02 64 03 5E  RX 响应
```

| 设备 | ID | 电量 | 含义 |
|------|----|------|------|
| 左耳 | 0x01 | 0x64 = 100 | 左耳电量 100% |
| 右耳 | 0x02 | 0x64 = 100 | 右耳电量 100% |
| 充电盒 | 0x03 | 0x5E = 94 | 充电盒电量 94% |

电量范围 0-100 (0x00-0x64)。两次 btsnoop 抓包数据一致。

---

### 3.6 一拖二 / 配对设备信息 (Feature=0x28)

> 本节命令在 README 中按一拖二解释（0x01 状态、0x02 开关、0x03 超时、0x04 写超时、0x05 设备列表、0x06 翻页、0x07 断开），早期记录为配对设备信息；两者映射到同一组命令，语义以 README 为准。

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x01 | 一拖二状态（早期记为设备信息） | (空) | `00` | ✓ |
| 0x03 | 一拖二超时（早期记为设备子类型） | (空) | `04`（秒？） | ✓ |
| 0x05 | 一拖二设备列表（早期记为连接设备名） | (空) | `00` + 6字节ID + ASCII名称 | ✓ |

#### 设备名响应格式

```
00 [设备ID:6] [Name:ASCII]
```

btsnoop 示例：`00 52 3e 85 63 9c b0 52 6f 78 79 20 4d 69 20 31 34` → "Roxy Mi 14"

---

### 3.7 手势 TOUCHV2 (Feature=0x2C/0x2D)

> 本节早期误记为电池通知；0x2C 实为手势 TOUCHV2，0x01 读出厂默认、0x02 读当前配置、0x03 整包写入 5 字节（见 README）。下面保留原始观察供对照。

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x01 | 读出厂默认 | (空) | 5 字节手势配置 | ✓ |
| 0x02 | 读当前配置 | (空) | 5 字节手势配置 | ✓ |
| 0x03 | 写配置 | 5 字节（早期记录为 6 字节，待复核） | 5 字节回显/确认 | ⚠️ 待复核 |

5 个字节依次为单击/双击/三击/长按1秒/长按3秒，高 4 位左耳、低 4 位右耳（动作表见 README）。

---

### 3.8 EQ 参数 (Feature=0x0A/0x0B) ✅ 已破解

| Cmd | 功能 | TX Payload | RX Payload | 状态 |
|-----|------|-----------|-----------|------|
| 0x03 | EQ 带宽查询 | 2 字节 | 1 字节 | ✓ |
| 0x05 | EQ 参数查询 | 2 字节 `[band_set:1] [band_count:1]` | EQ 数据 | ✓ |
| 0x06 | EQ 参数设置 | EQ 数据 | EQ 数据（回显） | ✓ |

#### EQ 数据格式

```
[band_set:1] [band_count:1] [reserved:2] [band_data × count]
```

每个 band **7 字节**：

```
[freq:2 BE=Hz] [gain:1] [gain_coef:1] [0x00:1] [Q:2 BE]
```

| 字段 | 偏移 | 大小 | 编码 | 说明 |
|------|------|------|------|------|
| freq | 0 | 2 BE u16 | Hz | 中心频率，如 0x0037 = 55Hz |
| gain | 2 | 1 | 见下文 | 增益，范围 -12 ~ +3 dB |
| gain_coef | 3 | 1 | 设备自动派生 | biquad 滤波器系数，随 gain 变化，与 Q 无关 |
| reserved | 4 | 1 | 固定 0x00 | |
| Q | 5-6 | 2 BE u16 | 见下文 | Q 值，范围 0.30 ~ 10.00 |

#### Gain 编码 ✅ 实测确认

```
编码: byte = (-gain_dB × 16) mod 256
解码: if byte ≤ 192 → gain = -byte / 16
      if byte ≥ 208 → gain = (256 - byte) / 16
```

| gain_dB | byte | hex |
|---------|------|-----|
| +3 | 208 | 0xD0 |
| +1 | 240 | 0xF0 |
| 0 | 0 | 0x00 |
| -1 | 16 | 0x10 |
| -6 | 96 | 0x60 |
| -12 | 192 | 0xC0 |

验证数据（抓包 3，gain=-1,-2,-3,-4,-5,-6）：

| Band | gain_dB | byte | hex | 公式验证 |
|------|---------|------|-----|---------|
| 0 | -1 | 16 | 0x10 | -16/16 = -1.0 ✓ |
| 1 | -2 | 32 | 0x20 | -32/16 = -2.0 ✓ |
| 2 | -3 | 48 | 0x30 | -48/16 = -3.0 ✓ |
| 3 | -4 | 64 | 0x40 | -64/16 = -4.0 ✓ |
| 4 | -5 | 80 | 0x50 | -80/16 = -5.0 ✓ |
| 5 | -6 | 96 | 0x60 | -96/16 = -6.0 ✓ |

#### Q 编码 ✅ 实测确认

```
编码: bytes[5:6] = 65536 - Q × 60 (BE u16)
解码: Q = (65536 - bytes[5:6]_BE_u16) / 60
```

| Q | bytes[5:6] | hex |
|---|-----------|-----|
| 0.30 | 65518 | 0xFFEE |
| 1.00 | 65476 | 0xFFC4 |
| 1.50 | 65446 | 0xFFA6 |
| 2.00 | 65416 | 0xFF88 |
| 3.00 | 65356 | 0xFF4C |
| 4.00 | 65296 | 0xFF10 |
| 5.00 | 65236 | 0xFED4 |
| 6.00 | 65176 | 0xFE98 |
| 10.00 | 64936 | 0xFE08 |

验证数据（抓包 4/5，Q=1~6）：

| Band | Q | bytes[5:6] | hex | 公式验证 |
|------|---|-----------|-----|---------|
| 0 | 1.00 | 65476 | 0xFFC4 | (65536-65476)/60 = 1.00 ✓ |
| 1 | 2.00 | 65416 | 0xFF88 | (65536-65416)/60 = 2.00 ✓ |
| 2 | 3.00 | 65356 | 0xFF4C | (65536-65356)/60 = 3.00 ✓ |
| 3 | 4.00 | 65296 | 0xFF10 | (65536-65296)/60 = 4.00 ✓ |
| 4 | 5.00 | 65236 | 0xFED4 | (65536-65236)/60 = 5.00 ✓ |
| 5 | 6.00 | 65176 | 0xFE98 | (65536-65176)/60 = 6.00 ✓ |

#### gain_coef (byte[3]) — biquad 滤波器系数

此字节是 **Conexant EQ 引擎的双二阶滤波器（biquad）系数**，由标准 DSP 公式从频率、增益、Q 值、滤波器类型、采样率计算得出。

**抓包 5 验证**（固定 55Hz，只改 Q，gain 不变）：

```
gain=-6.9, Q=1.5: byte3=0xF3(243)
gain=-6.9, Q=2.0: byte3=0xF3(243)  ← Q 变了，byte3 不变
gain=-6.9, Q=3.0: byte3=0xF3(243)  ← Q 变了，byte3 不变
gain=-6.9, Q=4.0: byte3=0xF3(243)  ← Q 变了，byte3 不变
```

→ **byte[3] 完全由 gain 决定，与 Q 无关。**

**抓包 4 验证**（byte[3] 随 gain 变化）：

| gain_dB | byte[3] |
|---------|--------|
| -1.8 | 0xCC (204) |
| -3.0 | 0x0B (11) |
| -5.0 | 0x13 (19) |
| -6.9 | 0xF3 (243) |

**DEX 反编译发现**：
- 计算类：`com.conexant.cnxtusbcheadset.Eq2Coeff`
- 计算方法：`getF3EQCoefficientList`（支持 24-bit 和 32-bit 系数）
- 输入参数：`frequency`, `gain`, `qFactor`, `filterType`, `sampleRate`
- 滤波器类型：`EQ_PEAKING_FILTER`, `EQ_HIGH_SHELF_FILTER`, `EQ_LOW_SHELF_FILTER`, `EQ_HIGH_PASS_FILTER`, `EQ_LOW_PASS_FILTER`
- 最大 band 数：`MAX_BAND_INDEX_FREEMAN3 = 9`（10 个 band）
- 设备代号：Freeman3

> 发送 EQ 数据时 byte[3] 可填 `0x00`，设备的 EQ 引擎会从 freq/gain/Q 自行重算。

#### band_set 预设

| band_set | band_count | 说明 |
|----------|-----------|------|
| 0x00 | 6 | 6-band 预设 |
| 0x07 | 9 | 9-band 预设 |

APP 每次连接读取并写回两组 EQ 参数，做预设同步。

#### 完整编码示例

设置 band 0: 55Hz, gain=-6dB, Q=3.0：
```
freq:   0x0037 (55Hz)
gain:   0x60 (96 = 0x60, -96/16 = -6dB)
coef:   0x00 (设备自行计算)
reserv: 0x00
Q:      65536 - 3.0×60 = 65356 = 0xFF4C

band bytes: 00 37 60 00 00 FF 4C
```

---

## 4. 连接初始化序列

每次 SPP 连接建立后，APP 按以下顺序查询：

```
 1. F=0x00 C=0x01           支持的命令列表
 2. F=0x00 C=0x0D           设备状态 [07,00,00,00,04]
 3. F=0x00 C=0x07           子命令查询（逐个 feature ID）
 4. F=0x00 C=0x0C [0x04]    配置查询
 5. F=0x00 C=0x0C [0x02]    配置查询
 6. F=0x00 C=0x0C [0x03]    配置查询
 7. F=0x00 C=0x0C [0x06]    配置查询
 8. F=0x00 C=0x05           固件版本 "3.5.2"
 9. F=0x40 C=0x03           ANC 状态
10. F=0x40 C=0x29           ANC 可用模式
11. F=0x1E C=0x01           Gain 状态
12. F=0x20 C=0x05           LHDC 状态（早期记为 LDAC）
13. F=0x26 C=0x01           指示灯状态（早期记为固件校验）
14. F=0x1C C=0x01 [FF FF FF] 提示音配置
15. F=0x28 C=0x01           一拖二状态（早期记为设备信息）
16. F=0x28 C=0x03           一拖二超时 (→ 0x04)
17. F=0x28 C=0x05           一拖二设备列表（早期记为连接设备名）
18. F=0x00 C=0x14           序列号 (L)
19. F=0x00 C=0x15           设备 ID (R)
20. F=0x1A C=0x00           查询支持的电池
21. F=0x1A C=0x01           电量查询
22. F=0x0A C=0x03           EQ 带宽查询
23. F=0x0A C=0x05 [00 06]   6-band EQ 参数
24. F=0x0A C=0x05 [07 09]   9-band EQ 参数
```

---

## 5. DEX 反编译发现

### APP 架构

- **应用框架**: Flutter (Dart)
- **EQ 库**: Conexant (现属 Synaptics) `cnxtusbcheadset` SDK
- **蓝牙协议库**: 高通 GAIA V3 SDK (`com.qualcomm.qti.gaiaclient`)
- **依赖注入**: Koin

### 关键类

| 类名 | 说明 |
|------|------|
| `com.conexant.cnxtusbcheadset.Eq2Coeff` | EQ 参数→biquad 系数转换 |
| `com.conexant.cnxtusbcheadset.EQBandParam` | EQ band 参数 |
| `com.conexant.cnxtusbcheadset.EQCoeffsList` | EQ 系数列表 |
| `com.conexant.cnxtusbcheadset.EQParamList` | EQ 参数列表 |
| `com.conexant.genericfeature.BandEQCoefficient` | band 系数 |
| `com.conexant.genericfeature.EQParam` | EQ 参数 |
| `com.qualcomm.qti.gaiaclient` | GAIA V3 客户端 SDK |
| `com.moondroplab.moondrop.moondrop_app.AutoEqLib` | AutoEQ 原生库 |
| `com.moondroplab.communication.usb.util.IIRFilterCalculatorNative` | IIR 滤波器计算 (Native) |

### EQ 滤波器类型

| 常量 | 说明 |
|------|------|
| `EQ_PEAKING_FILTER` | 峰值滤波器（最常用） |
| `EQ_HIGH_SHELF_FILTER` | 高频搁架 |
| `EQ_LOW_SHELF_FILTER` | 低频搁架 |
| `EQ_HIGH_PASS_FILTER` | 高通 |
| `EQ_LOW_PASS_FILTER` | 低通 |
| `EQ_UNKNOWN_FILTER` | 未知 |

### EQ 参数字段

```
frequency   - 中心频率 (Hz)
gain        - 增益 (dB)
qFactor     - Q 值
filterType  - 滤波器类型
sampleRate  - 采样率 (默认 DEFAULT_SAMPLERATE)
```

### EQ 相关日志字符串

```
saveEQParamsToFlash: save coefficient -> convert eq to coefficient: band:
saveEQParamsToFlash: save coefficient -> band index:
saveEQParamsToFlash: save coefficient -> sampleRateIndex:
saveEQParamsToFlash: save custom EQ!
getF3EQCoefficientList 24bits => EQ Coefficient list: band =
getF3EQCoefficientList 32 bits => EQ Coefficient list: band =
getF3EQCoefficientList: MAX_BAND_INDEX_FREEMAN3 = 9
setFreeman3EQ: eqCoeff == null
setEQParam: RC_INVALID_PARAMETER
```

### ANC 相关发现

- 使用 GAIA V3 的 `AncV2` Feature
- 支持 `supportAdaptiveANC`（自适应降噪）
- `handleGetANCMode` / `handleSetANCMode`
- `handleGetANCAction` / `handleSetANCAction`
- `onANCActionReceived` → 异步通知

### 服务器 API 端点

从 DEX strings 提取到的 MOONDROP 后端服务器：

```
基础地址: http://47.104.217.27:8080/venus
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `/apk/getApkVersionCode` | GET/POST | APP 版本检查 |
| `/apk/doDownload?apkVersionCode=` | GET | APP 下载 |
| `/fwFile/getFileList` | GET | 固件文件列表 |
| `/users/mobile/login` | POST | 用户登录 |
| `/users/mobile/register` | POST | 用户注册 |

> 服务器当前返回 502，可能已迁移或下线。

### 其他功能（反编译可见，SPP 未见）

| 功能 | 类/方法 | 说明 |
|------|---------|------|
| 空间音频 | `V3SpatialAudioPlugin` | ❌ 此设备不支持 |
| 电源控制 | `V3PowerControlPlugin` | 可能走 BLE |
| LED 控制 | `LedPublisher` | 可能走 BLE |
| 语音提示 | `VoicePublisher` | 可能走 BLE |
| 固件升级 | `UpgradePublisher` | ❌ 需要水月雨服务器 |
| LHDC 编码 | `publishLhdcState` | 可能走 BLE |
| 左右平衡 | `publishLeftRightBalance` | 可能走 BLE |

---

## 6. 待解决问题

| # | 问题 | 优先级 | 备注 |
|---|------|--------|------|
| 1 | 0x2C/0x2D 手势动作值映射 | 低 | 5 字节手势已确认；0x08-0x0F 无官方文案（见 README） |
| 2 | 0x1C/0x1D 提示音组号语义 | 低 | TX `FF FF FF` → RX `01 33 01`，组号范围 0-255 |
| 3 | 0x00 C=0x01 支持命令列表解析 | 中 | 24 字节 payload 的结构 |
| 4 | 0x00 C=0x07 子命令查询的具体含义 | 中 | 与支持命令列表的关系 |
| 5 | 配置参数 0x02/0x03/0x04/0x06 | 低 | |
| 6 | 0x26 指示灯开关状态格式 | 低 | README 记为开关；早期记为固件校验 |
| 7 | 0x27 回包归属（LED 响应？） | 低 | 早期单列，现按响应位归到 0x26 |
| 8 | 0x28 设备名前 6 字节是否为 MAC | 低 | |
| 9 | SET 响应 [1][2] 字节含义 | 低 | 实测文档记录的问题 |
| 10 | Trailing Byte 是否存在 | 低 | 现有样本与实现均未包含，待复核 |
| 11 | BLE GATT 通道的功能 | 中 | 反编译显示很多功能走 BLE |
| 12 | BLE RCSP 协议逆向 | 中 | 杰理私有音频/通知协议 |
| 13 | 服务器 API 完整结构 | 中 | 当前 502，需抓 APP 网络请求 |
| 14 | 空间音频 | — | ❌ 此设备不支持 |
| 15 | 固件升级 | — | ❌ 需要水月雨服务器 |

---

## 7. 抓包环境

| 抓包 | 文件 | 大小 | 目的 | 结果 |
|------|------|------|------|------|
| 1 | `btsnoop_hci_260712_211827.log` | 1.2 MB | 协议基础分析 | 发现所有 Feature ID |
| 2 | `btsnoop_hci_260712_223002.log` | 980 KB | ANC 子模式验证 | 确认 0x01=自适应, 0x03=抗风噪 |
| 3 | `btsnoop_hci_260713_121058.log` | 744 KB | EQ 参数破解 | 确认 gain/Q 编码公式 |
| 4 | `btsnoop_hci_260713_123058.log` | 1.8 MB | EQ 单变量测试 | Q 公式 100% 确认，byte[3] 与 Q 无关 |
| 5 | `btsnoop_hci_260713_130140.log` | 444 KB | EQ Q 变量测试 | 确认 byte[3] 完全由 gain 决定 |

设备: MOONDROP Pudding, 固件 3.5.2, 连接手机: Roxy Mi 14 (Xiaomi)
抓包方式: Android btsnoop HCI log
共解析: 8311 HCI 记录 → 799 RFCOMM 帧 → 379+ GAIA 包

---

## 8. BLE 补充

SPP 之外，设备还支持 BLE 连接：

- **BLE 蓝牙名**: TWS-056-BLE
- **协议**: RCSP（杰理私有），非标准 GATT
- **数据头**: `00 19` 开头
- **L2CAP CID**: 0xC3FF-0xFFFF（动态）
- **OTA GATT Service**: `0000ae00-0000-1000-8000-00805f9b34fb`
  - Write: `0000ae01` (write without response)
  - Notify: `0000ae02` (notify)

btsnoop BLE 分析（handle 0xEDC, 3267 RCSP 包）：
- **未发现 GAIA 命令**（FF 04 模式在 RCSP 数据中仅 6 次，均为音频数据巧合）
- RCSP 主要承载音频流和设备通知
- GAIA 控制命令仅通过 SPP RFCOMM 传输

> 反编译显示很多功能（电源控制、LED、语音、LHDC 等）可能走 BLE GATT 通道，但 btsnoop 中未捕获到对应的 GATT 写入操作。
