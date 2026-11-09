package com.moondrop.protocol

import com.moondrop.protocol.model.AncMode
import com.moondrop.protocol.model.GainLevel
import com.moondrop.protocol.model.GaiaPacket

/**
 * GAIA V3 响应解析器。
 * 基于实测 MOONDROP Pudding (杰理芯片) btsnoop 抓包数据与官方 APK 复核。
 *
 * 基础域响应 Feature=0x01, 通过 Cmd 区分功能。
 */
object ResponseParser {

    private fun parseAscii(packet: GaiaPacket, commandId: Int): String? {
        if (packet.featureId != (GaiaConstants.FEATURE_BASE or GaiaConstants.RESPONSE_BIT)) return null
        if (packet.commandId != commandId) return null
        if (packet.payload.isEmpty()) return null
        return try { String(packet.payload, Charsets.US_ASCII).trim() } catch (_: Exception) { null }
    }

    /** 解析应用/固件版本 (Feature=0x01, Cmd=0x05) */
    fun parseFirmwareVersion(packet: GaiaPacket): String? =
        parseAscii(packet, GaiaConstants.CMD_APPLICATION_VERSION)

    /** 解析应用/固件版本（APK 名称） */
    fun parseApplicationVersion(packet: GaiaPacket): String? = parseFirmwareVersion(packet)

    /** 解析设备序列号 (Feature=0x01, Cmd=0x03) */
    fun parseSerialNumber(packet: GaiaPacket): String? =
        parseAscii(packet, GaiaConstants.CMD_SERIAL_NUMBER)

    /** 解析左耳序列号 (Feature=0x01, Cmd=0x14) */
    fun parseLeftEarbudSerialNumber(packet: GaiaPacket): String? =
        parseAscii(packet, GaiaConstants.CMD_EARBUD_SN_L)

    /** 解析右耳序列号 (Feature=0x01, Cmd=0x15) */
    fun parseRightEarbudSerialNumber(packet: GaiaPacket): String? =
        parseAscii(packet, GaiaConstants.CMD_EARBUD_SN_R)

    /** 解析 ANC 状态 (Feature=0x41, payload[0]=当前模式, 仅接受 query/set 响应) */
    fun parseAncMode(packet: GaiaPacket): AncMode? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_ANC) return null
        if (packet.commandId != GaiaConstants.CMD_ANC_QUERY && packet.commandId != GaiaConstants.CMD_ANC_SET) return null
        if (packet.payload.isEmpty()) return null
        return AncMode.fromValue(packet.payload[0])
    }

    /** 解析 ANC 切换配置 (Feature=0x41, Cmd=0x29) */
    fun parseAncSwitchConfig(packet: GaiaPacket): List<Int> {
        if (!GaiaConstants.isResponse(packet.featureId)) return emptyList()
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_ANC) return emptyList()
        if (packet.commandId != GaiaConstants.CMD_ANC_CONFIG_READ) return emptyList()
        if (packet.payload.isEmpty()) return emptyList()
        return packet.payload.map { it.toInt() and 0xFF }
    }

    /** 解析 Gain 级别 (Feature=0x1F, payload[0]=当前级别, 仅接受 query/set 响应) */
    fun parseGainLevel(packet: GaiaPacket): GainLevel? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_GAIN) return null
        if (packet.commandId != GaiaConstants.CMD_GAIN_QUERY && packet.commandId != GaiaConstants.CMD_GAIN_SET) return null
        if (packet.payload.isEmpty()) return null
        return GainLevel.fromValue(packet.payload[0])
    }

    /** 解析 LDAC 状态 (Feature=0x21, Cmd=0x02) */
    fun parseLdacStatus(packet: GaiaPacket): Boolean? =
        parseCodecSwitch(packet, GaiaConstants.CMD_LDAC_STATUS)

    /** 解析 LC3 状态 (Feature=0x21, Cmd=0x01) */
    fun parseLc3Status(packet: GaiaPacket): Boolean? =
        parseCodecSwitch(packet, GaiaConstants.CMD_LC3_STATUS)

    /** 解析 LHDC 状态 (Feature=0x21, Cmd=0x05) */
    fun parseLhdcStatus(packet: GaiaPacket): Boolean? =
        parseCodecSwitch(packet, GaiaConstants.CMD_LHDC_STATUS)

    /**
     * 解析编解码开关状态（LDAC / LC3 / LHDC 三个入口共用）。
     *
     * 取值约定：payload[0] 中 `0x00` = false（关闭），`0x01` = true（开启），
     * **其余任何值（如 0x02、0xFF）= null（无法识别）**。
     *
     * 与官方 APK `V3CodecPlugin.publishLc3State/publishLdacState/publishLhdcState`
     * 中的 `bArr[0] == 1` 有意不同：APK 的写法会把设备返回的未定义值静默判为"关闭"，
     * 本实现返回 null，用于区分"确实关闭"与"无法识别"，避免向 UI 上报错误的关闭状态。
     */
    private fun parseCodecSwitch(packet: GaiaPacket, commandId: Int): Boolean? {
        if (packet.featureId != (GaiaConstants.FEATURE_CODEC or GaiaConstants.RESPONSE_BIT)) return null
        if (packet.commandId != commandId) return null
        if (packet.payload.isEmpty()) return null
        return when (packet.payload[0].toInt() and 0xFF) {
            0x00 -> false
            0x01 -> true
            else -> null // 0x02/0xFF 等：设备未定义，不猜
        }
    }

    /** 解析指示灯状态 (Feature=0x27, Cmd=0x01/0x02) */
    fun parseLed(packet: GaiaPacket): Boolean? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_LED) return null
        if (packet.commandId != GaiaConstants.CMD_LED_GET && packet.commandId != GaiaConstants.CMD_LED_SET) return null
        if (packet.payload.isEmpty()) return null
        return (packet.payload[0].toInt() and 0x01) == 1
    }

    /** 解析提示音配置 (Feature=0x1D, Cmd=0x01/0x02)：[enabled, volume, index] */
    fun parseVoiceConfig(packet: GaiaPacket): List<Int>? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_VOICE) return null
        if (packet.commandId != GaiaConstants.CMD_VOICE_GET && packet.commandId != GaiaConstants.CMD_VOICE_SET) return null
        if (packet.payload.size < 3) return null
        return listOf(packet.payload[0].toInt() and 0x01, packet.payload[1].toInt() and 0xFF, packet.payload[2].toInt() and 0xFF)
    }

    /** 解析手势配置 (Feature=0x2D, Cmd=0x01/0x02/0x03)：5 字节 */
    fun parseTouchConfig(packet: GaiaPacket): List<Int>? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_TOUCH) return null
        if (packet.commandId != GaiaConstants.CMD_TOUCH_DEFAULT &&
            packet.commandId != GaiaConstants.CMD_TOUCH_CURRENT &&
            packet.commandId != GaiaConstants.CMD_TOUCH_SET) return null
        if (packet.payload.size < 5) return null
        return packet.payload.take(5).map { it.toInt() and 0xFF }
    }

    /** 解析一拖二状态 (Feature=0x29, Cmd=0x01/0x02) */
    fun parseOnebringtwoState(packet: GaiaPacket): Boolean? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_ONEBRINGTWO) return null
        if (packet.commandId != GaiaConstants.CMD_OBT_STATUS && packet.commandId != GaiaConstants.CMD_OBT_SET) return null
        if (packet.payload.isEmpty()) return null
        return (packet.payload[0].toInt() and 0x01) == 1
    }

    /** 解析一拖二超时 (Feature=0x29, Cmd=0x03/0x04)，返回秒 */
    fun parseOnebringtwoTimeout(packet: GaiaPacket): Int? {
        if (!GaiaConstants.isResponse(packet.featureId)) return null
        if (GaiaConstants.baseFeatureId(packet.featureId) != GaiaConstants.FEATURE_ONEBRINGTWO) return null
        if (packet.commandId != GaiaConstants.CMD_OBT_TIMEOUT && packet.commandId != GaiaConstants.CMD_OBT_TIMEOUT_SET) return null
        if (packet.payload.isEmpty()) return null
        return packet.payload[0].toInt() and 0xFF
    }

    /** 错误帧：响应 Feature (bit0=1) 且 Cmd 带错误位 (0x80) */
    fun isError(packet: GaiaPacket): Boolean {
        return GaiaConstants.isResponse(packet.featureId) && GaiaConstants.isErrorCommand(packet.commandId)
    }

    /** 成功响应：响应 Feature (bit0=1) 且不是错误帧 */
    fun isSuccess(packet: GaiaPacket): Boolean {
        return GaiaConstants.isResponse(packet.featureId) && !GaiaConstants.isErrorCommand(packet.commandId)
    }
}
