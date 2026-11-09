package com.moondrop.protocol

/**
 * MOONDROP GAIA V3 协议常量定义。
 *
 * 基于实测 MOONDROP Pudding (杰理芯片) btsnoop 抓包数据 (2026-07)。
 *
 * TX/RX 格式:
 *   FF 04 [Len:2 BE] [Seq:1] [Vendor:1] [FeatureID:1] [CmdID:1] [Payload...]
 *   Len = payload.size
 *   总包长 = 8 + payload.size
 *   第 4 字节抓包始终为 0x00（可能是 16 位 Vendor 0x001D 的高字节，未确认）
 *
 * 响应位: Feature ID 的 bit 0 (Feature | 0x01 = 响应)
 *
 * 协议结构 (抓包确认):
 *   大部分查询: Feature=0x00, Cmd=功能号, 响应 Feature=0x01
 *   ANC 控制:   Feature=0x40, Cmd=子功能,  响应 Feature=0x41
 *   Gain 控制:  Feature=0x1E, Cmd=子功能,  响应 Feature=0x1F
 *   编解码器:   Feature=0x20, Cmd=子功能,  响应 Feature=0x21
 */
object GaiaConstants {

    // ========== 传输层 ==========
    const val VENDOR_ID: Int = 0x001D
    const val HEADER_0: Byte = 0xFF.toByte()
    const val HEADER_1: Byte = 0x04

    // ========== Feature ID (抓包确认) ==========
    /** 基础查询 Feature (固件版本、序列号、设备ID、EQ、配置、设备状态等) */
    const val FEATURE_BASE: Int = 0x00
    /** ANC 降噪控制 */
    const val FEATURE_ANC: Int = 0x40
    /** Gain 增益控制 */
    const val FEATURE_GAIN: Int = 0x1E
    /** 编解码器 (LC3/LDAC/LHDC) */
    const val FEATURE_CODEC: Int = 0x20
    /** EQ 参数读写 */
    const val FEATURE_EQ: Int = 0x0A
    /** 指示灯 */
    const val FEATURE_LED: Int = 0x26
    /** 一拖二 (ONEBRINGTWO) */
    const val FEATURE_ONEBRINGTWO: Int = 0x28
    /** 电池电量（Feature=0x1A，README/实测确认） */
    const val FEATURE_BATTERY: Int = 0x1A
    /** 提示音（VOICE） */
    const val FEATURE_VOICE: Int = 0x1C
    /** 手势 TOUCHV2（Feature=0x2C，APK + 真机确认） */
    const val FEATURE_TOUCH: Int = 0x2C

    // ========== Cmd ID - 基础域 (Feature=0x00, APK V3BasicPlugin 确认) ==========
    /** GAIA 版本 */
    const val CMD_GAIA_VERSION: Int = 0x00
    /** 支持的特性（首字节 more，后接 `[featureId][version]` 成对） */
    const val CMD_SUPPORTED_FEATURES: Int = 0x01
    /** 支持的特性（下一页，同样为成对格式） */
    const val CMD_SUPPORTED_FEATURES_NEXT: Int = 0x02
    /** 设备序列号 */
    const val CMD_SERIAL_NUMBER: Int = 0x03
    /** 应用/固件版本（APK 名称 APPLICATION_VERSION） */
    const val CMD_APPLICATION_VERSION: Int = 0x05
    /** 注册通知：Payload=[feature id] */
    const val CMD_REGISTER_NOTIFICATION: Int = 0x07
    /** 取消通知：Payload=[feature id] */
    const val CMD_CANCEL_NOTIFICATION: Int = 0x08
    /** 读取传输信息：Payload=[ProtocolInfo id 1..7] */
    const val CMD_GET_TRANSPORT_INFORMATION: Int = 0x0C
    /** 设置传输参数（写） */
    const val CMD_SET_TRANSPORT_PARAMETER: Int = 0x0D
    /** 左耳序列号 */
    const val CMD_EARBUD_SN_L: Int = 0x14
    /** 右耳序列号 */
    const val CMD_EARBUD_SN_R: Int = 0x15

    // ========== Cmd ID - ANC (Feature=0x40, 抓包确认) ==========
    /** ANC 状态查询 */
    const val CMD_ANC_QUERY: Int = 0x03
    /** ANC 模式设置: Payload=[mode] */
    const val CMD_ANC_SET: Int = 0x04
    /** ANC 切换配置读取（旧名“可用模式”有误） */
    const val CMD_ANC_CONFIG_READ: Int = 0x29
    /** ANC 切换配置写入 */
    const val CMD_ANC_CONFIG_WRITE: Int = 0x2A
    /** ANC 状态异步推送 */
    const val CMD_ANC_NOTIFY: Int = 0x81
    /** ANC 错误通知 */
    const val CMD_ANC_ERROR: Int = 0x84

    // ========== Cmd ID - Gain (Feature=0x1E, 抓包确认) ==========
    const val CMD_GAIN_QUERY: Int = 0x01
    const val CMD_GAIN_SET: Int = 0x02

    // ========== Cmd ID - 编解码器 (Feature=0x20, README/实测确认) ==========
    /** LC3 状态查询 */
    const val CMD_LC3_STATUS: Int = 0x01
    /** LDAC 状态查询 */
    const val CMD_LDAC_STATUS: Int = 0x02
    /** LC3 开关设置: Payload=[0/1] */
    const val CMD_LC3_SET: Int = 0x03
    /** LDAC 开关设置: Payload=[0/1] */
    const val CMD_LDAC_SET: Int = 0x04
    /** LHDC 状态查询 */
    const val CMD_LHDC_STATUS: Int = 0x05
    /** LHDC 开关设置: Payload=[0/1] */
    const val CMD_LHDC_SET: Int = 0x06

    // ========== Cmd ID - EQ (Feature=0x0A, APK V3MusicProcessingPlugin 确认) ==========
    const val CMD_EQ_STATE: Int = 0x00
    const val CMD_EQ_AVAILABLE_PRESETS: Int = 0x01
    const val CMD_EQ_READ_SET: Int = 0x02
    const val CMD_EQ_WRITE_SET: Int = 0x03
    const val CMD_EQ_USER_BAND_COUNT: Int = 0x04
    const val CMD_EQ_USER_CONFIG_READ: Int = 0x05
    const val CMD_EQ_USER_CONFIG_WRITE: Int = 0x06
    const val CMD_EQ_SAVE_USER: Int = 0x07
    const val CMD_EQ_WRITE_NV_ID: Int = 0x08

    // ========== Cmd ID - 指示灯 (Feature=0x26, APK 确认) ==========
    const val CMD_LED_GET: Int = 0x01
    const val CMD_LED_SET: Int = 0x02

    // ========== Cmd ID - 提示音 (Feature=0x1C, APK 确认) ==========
    const val CMD_VOICE_GET: Int = 0x01
    const val CMD_VOICE_SET: Int = 0x02

    // ========== Cmd ID - 手势 (Feature=0x2C, APK 确认) ==========
    const val CMD_TOUCH_DEFAULT: Int = 0x01
    const val CMD_TOUCH_CURRENT: Int = 0x02
    const val CMD_TOUCH_SET: Int = 0x03

    // ========== Cmd ID - 一拖二 (Feature=0x28, APK 确认) ==========
    const val CMD_OBT_STATUS: Int = 0x01
    const val CMD_OBT_SET: Int = 0x02
    const val CMD_OBT_TIMEOUT: Int = 0x03
    const val CMD_OBT_TIMEOUT_SET: Int = 0x04
    const val CMD_OBT_DEVICE_LIST: Int = 0x05
    const val CMD_OBT_DEVICE_LIST_NEXT: Int = 0x06
    const val CMD_OBT_DISCONNECT: Int = 0x07

    // ========== Cmd ID - 电池电量 (Feature=0x1A, README 确认) ==========
    /** 查询支持的电池 (Cmd=0x00) */
    const val CMD_BATTERY_SUPPORTED: Int = 0x00
    /** 查询指定电池: Payload=[ID...]，回包为 [ID][level] 成对 (Cmd=0x01) */
    const val CMD_BATTERY_QUERY: Int = 0x01

    // ========== ANC 模式 (水月雨 APP btsnoop 确认) ==========
    const val ANC_OFF: Byte = 0x00
    const val ANC_ADAPTIVE: Byte = 0x01
    const val ANC_TRANSPARENCY: Byte = 0x02
    const val ANC_ANTI_WIND: Byte = 0x03
    /** 降噪组入口，SET 后进入降噪并恢复上次子模式 */
    const val ANC_NOISE_CANCEL: Byte = 0x04

    // ========== 响应位 ==========
    const val RESPONSE_BIT: Int = 0x01
    /** 错误/通知位: Cmd 的 bit 7（响应 Feature + 该位 = 错误帧；请求 Feature + 该位 = 通知帧） */
    const val ERROR_BIT: Int = 0x80
    fun isResponse(featureId: Int): Boolean = (featureId and RESPONSE_BIT) != 0
    fun baseFeatureId(featureId: Int): Int = featureId and RESPONSE_BIT.inv()
    fun isErrorCommand(commandId: Int): Boolean = (commandId and ERROR_BIT) != 0
}
