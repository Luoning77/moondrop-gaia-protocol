package com.moondrop.protocol

import com.moondrop.protocol.model.AncMode
import com.moondrop.protocol.model.GainLevel
import com.moondrop.protocol.model.GaiaPacket

/**
 * GAIA V3 命令包构造器。
 * 基于实测 MOONDROP Pudding (杰理芯片) btsnoop 抓包数据。
 *
 * 协议结构: Feature=0x00 用于基础查询, Cmd 为功能号。
 * ANC/Gain/Codec 使用独立 Feature ID。
 */
object GaiaPacketBuilder {

    // ========== ANC 控制 (Feature 0x40) ==========

    fun ancQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_QUERY)

    fun ancSet(mode: Byte): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_SET, byteArrayOf(mode))

    fun ancSet(mode: AncMode): GaiaPacket = ancSet(mode.value)

    fun ancAvailable(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_AVAILABLE)

    // ========== 基础查询 (Feature 0x00, Cmd=功能号) ==========

    fun firmwareVersionQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_FIRMWARE_VERSION)

    fun serialNumberQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_SERIAL)

    fun deviceIdQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_DEVICE_ID)

    fun deviceStateQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_DEVICE_STATE)

    fun configQuery(configId: Byte): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_CONFIG_QUERY, byteArrayOf(configId))

    fun supportedCommandsQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_SUPPORTED_COMMANDS)

    // ========== Gain (Feature 0x1E) ==========

    fun gainQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_GAIN, GaiaConstants.CMD_GAIN_QUERY)
    fun gainSet(level: Byte): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_GAIN, GaiaConstants.CMD_GAIN_SET, byteArrayOf(level))
    fun gainSet(level: GainLevel): GaiaPacket = gainSet(level.value)

    // ========== 编解码器 (Feature 0x20) ==========

    fun lc3StatusQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_CODEC, GaiaConstants.CMD_LC3_STATUS)
    fun ldacStatusQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_CODEC, GaiaConstants.CMD_LDAC_STATUS)
    fun lhdcStatusQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_CODEC, GaiaConstants.CMD_LHDC_STATUS)

    fun lc3Set(enabled: Boolean): GaiaPacket = codecSet(GaiaConstants.CMD_LC3_SET, enabled)
    fun ldacSet(enabled: Boolean): GaiaPacket = codecSet(GaiaConstants.CMD_LDAC_SET, enabled)
    fun lhdcSet(enabled: Boolean): GaiaPacket = codecSet(GaiaConstants.CMD_LHDC_SET, enabled)

    private fun codecSet(commandId: Int, enabled: Boolean): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_CODEC, commandId, byteArrayOf(if (enabled) 0x01 else 0x00))

    // ========== 探测 ==========

    fun probe(featureId: Int, cmdId: Int): GaiaPacket = GaiaPacket(featureId, cmdId)

    // ========== 批量查询 ==========

    fun statusQueryPackets(): List<GaiaPacket> = listOf(
        supportedCommandsQuery(),
        firmwareVersionQuery(),
        ancQuery(),
        gainQuery(),
        serialNumberQuery(),
        deviceIdQuery()
    )
}
