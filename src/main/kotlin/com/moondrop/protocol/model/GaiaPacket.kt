package com.moondrop.protocol.model

/**
 * GAIA V3 数据包。
 *
 * 包格式 (TX 和 RX 相同):
 * ```
 * FF 04 [Len:2 BE] [Seq:1] [Vendor:1] [FeatureID:1] [CmdID:1] [Payload...]
 * ```
 * Len = payload.size
 * 总包长 = 8 + payload.size
 */
data class GaiaPacket(
    /** Feature ID */
    val featureId: Int,

    /** Command ID */
    val commandId: Int,

    /** 载荷数据 */
    val payload: ByteArray = byteArrayOf(),

    /** 第 4 字节：抓包始终为 0x00，含义待确认（可能是 16 位 Vendor 的高字节） */
    val sequence: Byte = 0x00
) {
    /** 获取 cmdId (featureId shl 8 | commandId) */
    val cmdId: Int get() = (featureId shl 8) or commandId

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is GaiaPacket) return false
        return featureId == other.featureId &&
                commandId == other.commandId &&
                payload.contentEquals(other.payload) &&
                sequence == other.sequence
    }

    override fun hashCode(): Int {
        var result = featureId
        result = 31 * result + commandId
        result = 31 * result + payload.contentHashCode()
        result = 31 * result + sequence.hashCode()
        return result
    }

    override fun toString(): String {
        val payloadHex = payload.joinToString(" ") { String.format("%02X", it) }
        return "GaiaPacket(feature=0x${String.format("%02X", featureId)}, " +
                "cmd=0x${String.format("%02X", commandId)}, " +
                "payload=[$payloadHex], " +
                "seq=$sequence)"
    }
}
