package com.moondrop.protocol

import com.moondrop.protocol.model.AncMode
import com.moondrop.protocol.model.GainLevel
import com.moondrop.protocol.model.GaiaPacket

/**
 * GAIA V3 命令包构造器。
 * 基于实测 MOONDROP Pudding (杰理芯片) btsnoop 抓包数据与官方 APK 复核。
 *
 * 协议结构: Feature=0x00 用于基础查询, Cmd 为功能号。
 * ANC/Gain/Codec/LED/Voice/Touch/OneBringTwo 使用独立 Feature ID。
 */
object GaiaPacketBuilder {

    // ========== ANC 控制 (Feature 0x40) ==========

    fun ancQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_QUERY)

    fun ancSet(mode: Byte): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_SET, byteArrayOf(mode))

    fun ancSet(mode: AncMode): GaiaPacket = ancSet(mode.value)

    fun ancConfigQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_CONFIG_READ)

    fun ancConfigSet(values: ByteArray): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ANC, GaiaConstants.CMD_ANC_CONFIG_WRITE, values)

    // ========== 基础域 (Feature 0x00) ==========

    fun supportedFeaturesQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_SUPPORTED_FEATURES)

    fun supportedFeaturesNextQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_SUPPORTED_FEATURES_NEXT)

    fun deviceSerialNumberQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_SERIAL_NUMBER)

    fun leftEarbudSerialNumberQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_EARBUD_SN_L)

    fun rightEarbudSerialNumberQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_EARBUD_SN_R)

    fun applicationVersionQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_APPLICATION_VERSION)

    /** 旧名；APK 中 0x05 是 APPLICATION_VERSION。 */
    fun firmwareVersionQuery(): GaiaPacket = applicationVersionQuery()

    fun transportInformationQuery(parameter: Byte): GaiaPacket {
        require(parameter.toInt() in 1..7) { "ProtocolInfo id must be 1..7" }
        return GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_GET_TRANSPORT_INFORMATION, byteArrayOf(parameter))
    }

    fun transportParameterSet(payload: ByteArray): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_SET_TRANSPORT_PARAMETER, payload)

    fun registerNotification(featureId: Byte): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_REGISTER_NOTIFICATION, byteArrayOf(featureId))

    fun cancelNotification(featureId: Byte): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_BASE, GaiaConstants.CMD_CANCEL_NOTIFICATION, byteArrayOf(featureId))

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
        GaiaPacket(GaiaConstants.FEATURE_CODEC, commandId, byteArrayOf((if (enabled) 1 else 0).toByte()))

    // ========== 指示灯 (Feature 0x26) ==========

    fun ledQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_LED, GaiaConstants.CMD_LED_GET)

    fun ledSet(on: Boolean): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_LED, GaiaConstants.CMD_LED_SET, byteArrayOf((if (on) 1 else 0).toByte()))

    // ========== 提示音 (Feature 0x1C) ==========

    fun voiceQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_VOICE, GaiaConstants.CMD_VOICE_GET)

    fun voiceSet(enabled: Boolean, volume: Int, index: Int): GaiaPacket {
        require(volume in 0..100) { "volume must be 0..100" }
        require(index in 0..255) { "index must be 0..255" }
        return GaiaPacket(
            GaiaConstants.FEATURE_VOICE,
            GaiaConstants.CMD_VOICE_SET,
            byteArrayOf((if (enabled) 1 else 0).toByte(), volume.toByte(), index.toByte())
        )
    }

    // ========== 手势 (Feature 0x2C) ==========

    fun touchDefaultQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_TOUCH, GaiaConstants.CMD_TOUCH_DEFAULT)

    fun touchCurrentQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_TOUCH, GaiaConstants.CMD_TOUCH_CURRENT)

    fun touchSet(values: ByteArray): GaiaPacket {
        require(values.size == 5) { "touch config must be 5 bytes" }
        return GaiaPacket(GaiaConstants.FEATURE_TOUCH, GaiaConstants.CMD_TOUCH_SET, values)
    }

    // ========== 一拖二 (Feature 0x28) ==========

    fun onebringtwoQuery(): GaiaPacket = GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_STATUS)

    fun onebringtwoSet(on: Boolean): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_SET, byteArrayOf((if (on) 1 else 0).toByte()))

    fun onebringtwoTimeoutQuery(): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_TIMEOUT)

    fun onebringtwoTimeoutSet(seconds: Int): GaiaPacket {
        require(seconds in 0..255) { "timeout must be 0..255" }
        return GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_TIMEOUT_SET, byteArrayOf(seconds.toByte()))
    }

    fun onebringtwoDeviceListQuery(): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_DEVICE_LIST)

    fun onebringtwoDeviceListNextQuery(): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_DEVICE_LIST_NEXT)

    fun onebringtwoDisconnect(payload: ByteArray): GaiaPacket =
        GaiaPacket(GaiaConstants.FEATURE_ONEBRINGTWO, GaiaConstants.CMD_OBT_DISCONNECT, payload)

    // ========== 探测 ==========

    fun probe(featureId: Int, cmdId: Int): GaiaPacket = GaiaPacket(featureId, cmdId)

    // ========== 批量查询 ==========

    fun statusQueryPackets(): List<GaiaPacket> = listOf(
        supportedFeaturesQuery(),
        applicationVersionQuery(),
        ancQuery(),
        gainQuery(),
        deviceSerialNumberQuery(),
        leftEarbudSerialNumberQuery(),
        rightEarbudSerialNumberQuery()
    )
}
