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
    /** 设备信息（配对设备名、子类型） */
    const val FEATURE_DEVICE_INFO: Int = 0x28
    /** 电池电量（Feature=0x1A，README/实测确认） */
    const val FEATURE_BATTERY: Int = 0x1A
    /** 手势 TOUCHV2（Feature=0x2C，APK + 真机确认） */
    const val FEATURE_TOUCH: Int = 0x2C

    // ========== Cmd ID - 基础查询 (Feature=0x00, 抓包确认) ==========
    /** 支持的命令列表 */
    const val CMD_SUPPORTED_COMMANDS: Int = 0x01
    /** 固件版本查询 */
    const val CMD_FIRMWARE_VERSION: Int = 0x05
    /** EQ 状态查询（兼作心跳） */
    const val CMD_EQ_STATUS: Int = 0x07
    /** 设备状态 */
    const val CMD_DEVICE_STATE: Int = 0x0D
    /** 配置查询 (子命令在 payload 中) */
    const val CMD_CONFIG_QUERY: Int = 0x0C
    /** 序列号查询 */
    const val CMD_SERIAL: Int = 0x14
    /** 设备 ID 查询 */
    const val CMD_DEVICE_ID: Int = 0x15

    // ========== Cmd ID - ANC (Feature=0x40, 抓包确认) ==========
    /** ANC 状态查询 */
    const val CMD_ANC_QUERY: Int = 0x03
    /** ANC 模式设置: Payload=[mode] */
    const val CMD_ANC_SET: Int = 0x04
    /** ANC 可用模式查询 */
    const val CMD_ANC_AVAILABLE: Int = 0x29
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

    // ========== Cmd ID - EQ 参数 (Feature=0x0A, btsnoop 确认, 格式待确认) ==========
    const val CMD_EQ_BANDWIDTH: Int = 0x03
    const val CMD_EQ_PARAM_QUERY: Int = 0x05
    const val CMD_EQ_PARAM_SET: Int = 0x06

    // ========== Cmd ID - 设备信息 (Feature=0x28, btsnoop 确认) ==========
    const val CMD_DEVICE_INFO: Int = 0x01
    const val CMD_DEVICE_SUBTYPE: Int = 0x03
    const val CMD_CONNECTED_DEVICE_NAME: Int = 0x05

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
