package com.moondrop.protocol.codec

import com.moondrop.protocol.GaiaConstants
import com.moondrop.protocol.model.GaiaPacket

/**
 * GAIA V3 帧编解码器。
 *
 * 包格式 (TX 和 RX 相同):
 * ```
 * FF 04 [Len:2 BE] [Seq:1] [Vendor:1] [FeatureID:1] [CmdID:1] [Payload...]
 * ```
 * Len = payload.size
 * 总包长 = 8 + payload.size
 */
object GaiaCodec {

    /** 单帧 payload 上限。超过视为长度字段损坏，按错帧丢弃并重新同步。 */
    const val MAX_PAYLOAD: Int = 512

    // ========== 编码 ==========

    fun encode(featureId: Int, commandId: Int, payload: ByteArray = byteArrayOf(), sequence: Byte = 0x00): ByteArray {
        val pkt = ByteArray(8 + payload.size)
        pkt[0] = GaiaConstants.HEADER_0
        pkt[1] = GaiaConstants.HEADER_1
        // Len: big-endian, payload size only
        pkt[2] = ((payload.size shr 8) and 0xFF).toByte()
        pkt[3] = (payload.size and 0xFF).toByte()
        pkt[4] = sequence
        pkt[5] = (GaiaConstants.VENDOR_ID and 0xFF).toByte()
        pkt[6] = (featureId and 0xFF).toByte()
        pkt[7] = (commandId and 0xFF).toByte()
        if (payload.isNotEmpty()) {
            System.arraycopy(payload, 0, pkt, 8, payload.size)
        }
        return pkt
    }

    fun encode(packet: GaiaPacket): ByteArray {
        return encode(packet.featureId, packet.commandId, packet.payload, packet.sequence)
    }

    // ========== 解码 ==========

    /**
     * 解码单帧。
     *
     * 要求 `data.size >= 8 + Len`，且 Len 不超过 [MAX_PAYLOAD]；
     * 末尾多余字节会被忽略，只截取 Len 声明的 payload（与 `webtest.decode_packet` 一致）。
     */
    fun decode(data: ByteArray): GaiaPacket? {
        if (data.size < 8) return null
        if (data[0].toInt() and 0xFF != 0xFF || data[1].toInt() and 0xFF != 0x04) return null

        val vendorId = data[5].toInt() and 0xFF
        if (vendorId != (GaiaConstants.VENDOR_ID and 0xFF)) return null

        val len = ((data[2].toInt() and 0xFF) shl 8) or (data[3].toInt() and 0xFF)
        if (len > MAX_PAYLOAD) return null
        if (data.size < 8 + len) return null

        val featureId = data[6].toInt() and 0xFF
        val commandId = data[7].toInt() and 0xFF
        val payload = if (len > 0) data.copyOfRange(8, 8 + len) else byteArrayOf()

        return GaiaPacket(featureId = featureId, commandId = commandId, payload = payload, sequence = data[4])
    }

    fun isValidPacket(data: ByteArray): Boolean {
        if (data.size < 8) return false
        if (data[0].toInt() and 0xFF != 0xFF || data[1].toInt() and 0xFF != 0x04) return false
        return (data[5].toInt() and 0xFF) == GaiaConstants.VENDOR_ID
    }

    // ========== 流式解码 ==========

    class StreamDecoder {
        private var buffer = ByteArray(1024)
        private var head = 0
        private var tail = 0

        fun feed(data: ByteArray): List<GaiaPacket> {
            if (tail + data.size > buffer.size) {
                val newBuffer = ByteArray(maxOf(buffer.size * 2, tail + data.size))
                System.arraycopy(buffer, head, newBuffer, 0, tail - head)
                tail -= head
                head = 0
                buffer = newBuffer
            }
            System.arraycopy(data, 0, buffer, tail, data.size)
            tail += data.size
            return drain()
        }

        private fun drain(): List<GaiaPacket> {
            val packets = mutableListOf<GaiaPacket>()
            while (tail - head >= 8) {
                if (buffer[head].toInt() and 0xFF != 0xFF || buffer[head + 1].toInt() and 0xFF != 0x04) {
                    head++
                    continue
                }
                val vendor = buffer[head + 5].toInt() and 0xFF
                if (vendor != GaiaConstants.VENDOR_ID) {
                    head++
                    continue
                }
                val len = (buffer[head + 2].toInt() and 0xFF shl 8) or (buffer[head + 3].toInt() and 0xFF)
                if (len > MAX_PAYLOAD) {
                    // 长度字段不可信：丢弃 1 字节重新同步，避免后续正常帧被一起卡住。
                    head++
                    continue
                }
                val totalLen = 8 + len
                if (tail - head < totalLen) break
                val decoded = decode(buffer.copyOfRange(head, head + totalLen))
                head += totalLen
                if (decoded != null) packets.add(decoded)
            }
            if (head > 0 && tail > head) {
                val remaining = tail - head
                System.arraycopy(buffer, head, buffer, 0, remaining)
                head = 0
                tail = remaining
            } else if (head == tail) {
                head = 0; tail = 0
            }
            return packets
        }

        fun reset() { head = 0; tail = 0 }
    }
}
