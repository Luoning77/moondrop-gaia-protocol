package com.moondrop.protocol

import com.moondrop.protocol.codec.GaiaCodec
import com.moondrop.protocol.model.AncMode
import com.moondrop.protocol.model.GainLevel
import com.moondrop.protocol.model.GaiaPacket
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class GaiaCodecTest {

    private fun hex(vararg bytes: Int): ByteArray = ByteArray(bytes.size) { bytes[it].toByte() }

    // ========== 编码 ==========

    @Test
    fun `encode firmware version query`() {
        val encoded = GaiaCodec.encode(GaiaPacketBuilder.firmwareVersionQuery())
        assertEquals(0xFF, encoded[0].toInt() and 0xFF)
        assertEquals(0x04, encoded[1].toInt() and 0xFF)
        assertEquals(0x00, encoded[6].toInt() and 0xFF) // FEATURE_BASE
        assertEquals(0x05, encoded[7].toInt() and 0xFF) // CMD_FIRMWARE_VERSION
    }

    @Test
    fun `encode ANC query`() {
        val encoded = GaiaCodec.encode(GaiaPacketBuilder.ancQuery())
        assertEquals(0x40, encoded[6].toInt() and 0xFF) // FEATURE_ANC
        assertEquals(0x03, encoded[7].toInt() and 0xFF) // CMD_ANC_QUERY
    }

    @Test
    fun `encode ANC set`() {
        val encoded = GaiaCodec.encode(GaiaPacketBuilder.ancSet(AncMode.ADAPTIVE))
        assertEquals(0x40, encoded[6].toInt() and 0xFF)
        assertEquals(0x04, encoded[7].toInt() and 0xFF)
        assertEquals(0x01, encoded[8].toInt() and 0xFF) // ANC mode = 0x01
    }

    @Test
    fun `encode gain set`() {
        val encoded = GaiaCodec.encode(GaiaPacketBuilder.gainSet(GainLevel.LOW))
        assertEquals(0x1E, encoded[6].toInt() and 0xFF)
        assertEquals(0x02, encoded[7].toInt() and 0xFF)
        assertEquals(0x02, encoded[8].toInt() and 0xFF)
    }

    @Test
    fun `encode len is payload size`() {
        val encoded = GaiaCodec.encode(GaiaPacket(0x40, 0x04, byteArrayOf(0x01, 0x02, 0x03)))
        assertEquals(0, encoded[2].toInt() and 0xFF, "len high byte")
        assertEquals(3, encoded[3].toInt() and 0xFF, "len low byte")
        assertEquals(11, encoded.size, "total size = 8 + 3")
    }

    @Test
    fun `codec commands use documented ids`() {
        assertEquals(0x02, GaiaCodec.encode(GaiaPacketBuilder.ldacStatusQuery())[7].toInt() and 0xFF)
        assertEquals(0x01, GaiaCodec.encode(GaiaPacketBuilder.lc3StatusQuery())[7].toInt() and 0xFF)
        assertEquals(0x05, GaiaCodec.encode(GaiaPacketBuilder.lhdcStatusQuery())[7].toInt() and 0xFF)
        assertEquals(0x03, GaiaCodec.encode(GaiaPacketBuilder.lc3Set(true))[7].toInt() and 0xFF)
        assertEquals(0x04, GaiaCodec.encode(GaiaPacketBuilder.ldacSet(true))[7].toInt() and 0xFF)
        assertEquals(0x06, GaiaCodec.encode(GaiaPacketBuilder.lhdcSet(true))[7].toInt() and 0xFF)
    }

    @Test
    fun `basic domain commands use documented ids`() {
        fun cmdOf(bytes: ByteArray) = bytes[7].toInt() and 0xFF
        assertEquals(0x01, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.supportedFeaturesQuery())))
        assertEquals(0x02, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.supportedFeaturesNextQuery())))
        assertEquals(0x03, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.deviceSerialNumberQuery())))
        assertEquals(0x05, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.applicationVersionQuery())))
        assertEquals(0x0C, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.transportInformationQuery(0x02.toByte()))))
        assertEquals(0x02, GaiaCodec.encode(GaiaPacketBuilder.transportInformationQuery(0x02.toByte()))[8].toInt() and 0xFF)
        assertEquals(0x14, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.leftEarbudSerialNumberQuery())))
        assertEquals(0x15, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.rightEarbudSerialNumberQuery())))
        assertEquals(0x29, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.ancConfigQuery())))
    }

    @Test
    fun `feature constants use documented ids`() {
        assertEquals(0x1A, GaiaConstants.FEATURE_BATTERY) // 电池
        assertEquals(0x2C, GaiaConstants.FEATURE_TOUCH)   // 手势 TOUCHV2
        assertEquals(0x28, GaiaConstants.FEATURE_ONEBRINGTWO)
        assertEquals(0x26, GaiaConstants.FEATURE_LED)
        assertEquals(0x1C, GaiaConstants.FEATURE_VOICE)
        assertEquals(0x00, GaiaConstants.CMD_BATTERY_SUPPORTED)
        assertEquals(0x01, GaiaConstants.CMD_BATTERY_QUERY)
        assertEquals(0x03, GaiaConstants.CMD_SERIAL_NUMBER)
        assertEquals(0x14, GaiaConstants.CMD_EARBUD_SN_L)
        assertEquals(0x15, GaiaConstants.CMD_EARBUD_SN_R)
    }

    // ========== 解码 ==========

    @Test
    fun `decode firmware version`() {
        val rx = hex(0xFF, 0x04, 0x00, 0x05, 0x00, 0x1D, 0x01, 0x05) +
                "3.5.2".toByteArray(Charsets.US_ASCII)
        val p = GaiaCodec.decode(rx)
        assertNotNull(p)
        assertEquals(0x01, p.featureId) // response bit set
        assertEquals(0x05, p.commandId)
        assertEquals("3.5.2", ResponseParser.parseFirmwareVersion(p))
    }

    @Test
    fun `decode ANC status`() {
        val rx = hex(0xFF, 0x04, 0x00, 0x01, 0x00, 0x1D, 0x41, 0x03, 0x02)
        val p = GaiaCodec.decode(rx)
        assertNotNull(p)
        assertEquals(0x41, p.featureId) // 0x40 | 0x01 response bit
        assertEquals(AncMode.TRANSPARENCY, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `decode ANC off`() {
        val rx = hex(0xFF, 0x04, 0x00, 0x01, 0x00, 0x1D, 0x41, 0x03, 0x00)
        val p = GaiaCodec.decode(rx)
        assertNotNull(p)
        assertEquals(AncMode.OFF, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `decode ANC anti-wind`() {
        val rx = hex(0xFF, 0x04, 0x00, 0x01, 0x00, 0x1D, 0x41, 0x03, 0x03)
        val p = GaiaCodec.decode(rx)
        assertNotNull(p)
        assertEquals(AncMode.ANTI_WIND, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `decode ANC adaptive`() {
        val rx = hex(0xFF, 0x04, 0x00, 0x01, 0x00, 0x1D, 0x41, 0x03, 0x01)
        val p = GaiaCodec.decode(rx)
        assertNotNull(p)
        assertEquals(AncMode.ADAPTIVE, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `decode invalid header`() {
        assertNull(GaiaCodec.decode(hex(0x00, 0x04, 0x00, 0x00, 0x00, 0x1D, 0x05, 0x00)))
    }

    @Test
    fun `decode wrong vendor`() {
        assertNull(GaiaCodec.decode(hex(0xFF, 0x04, 0x00, 0x00, 0x00, 0x01, 0x05, 0x00)))
    }

    @Test
    fun `decode too short`() {
        assertNull(GaiaCodec.decode(hex(0xFF, 0x04, 0x00)))
    }

    @Test
    fun `decode rejects len larger than data`() {
        // 声明 Len=5，实际只有 1 字节 payload
        assertNull(GaiaCodec.decode(hex(0xFF, 0x04, 0x00, 0x05, 0x00, 0x1D, 0x41, 0x03, 0x33)))
    }

    @Test
    fun `decode ignores bytes beyond declared len`() {
        // 声明 Len=0，末尾多出 2 字节：与 webtest.decode_packet 一致，只取 Len 长度
        val p = GaiaCodec.decode(hex(0xFF, 0x04, 0x00, 0x00, 0x00, 0x1D, 0x41, 0x03, 0xAA, 0xBB))
        assertNotNull(p)
        assertTrue(p.payload.isEmpty())
    }

    @Test
    fun `decode rejects oversized len`() {
        val len = GaiaCodec.MAX_PAYLOAD + 1
        val rx = hex(
            0xFF, 0x04, (len shr 8) and 0xFF, len and 0xFF,
            0x00, 0x1D, 0x41, 0x03
        )
        assertNull(GaiaCodec.decode(rx))
    }

    // ========== 工具方法 ==========

    @Test
    fun `isResponse and baseFeatureId`() {
        assertTrue(GaiaConstants.isResponse(0x41))
        assertEquals(0x40, GaiaConstants.baseFeatureId(0x41))
    }

    @Test
    fun `packet cmdId`() {
        assertEquals(0x0005, GaiaPacket(0x00, 0x05).cmdId)
    }

    // ========== ResponseParser ==========

    @Test
    fun `parse firmware fails on wrong feature`() {
        assertNull(ResponseParser.parseFirmwareVersion(GaiaPacket(0x07, 0x05, "1.0".toByteArray())))
    }

    @Test
    fun `parse basic domain strings`() {
        assertEquals("DEV-SN", ResponseParser.parseSerialNumber(GaiaPacket(0x01, 0x03, "DEV-SN".toByteArray())))
        assertEquals("L-SN", ResponseParser.parseLeftEarbudSerialNumber(GaiaPacket(0x01, 0x14, "L-SN".toByteArray())))
        assertEquals("R-SN", ResponseParser.parseRightEarbudSerialNumber(GaiaPacket(0x01, 0x15, "R-SN".toByteArray())))
        assertEquals("3.5.2", ResponseParser.parseApplicationVersion(GaiaPacket(0x01, 0x05, "3.5.2".toByteArray())))
        assertNull(ResponseParser.parseSerialNumber(GaiaPacket(0x01, 0x14, "L-SN".toByteArray())))
    }

    @Test
    fun `parse led voice touch and onebringtwo`() {
        assertEquals(true, ResponseParser.parseLed(GaiaPacket(0x27, 0x01, byteArrayOf(0x01))))
        assertEquals(listOf(1, 60, 3), ResponseParser.parseVoiceConfig(GaiaPacket(0x1D, 0x01, byteArrayOf(0x01, 60, 3))))
        assertEquals(listOf(0x11, 0x23, 0x66, 0x77, 0x00),
            ResponseParser.parseTouchConfig(GaiaPacket(0x2D, 0x02, byteArrayOf(0x11, 0x23, 0x66, 0x77, 0x00))))
        assertEquals(true, ResponseParser.parseOnebringtwoState(GaiaPacket(0x29, 0x01, byteArrayOf(0x01))))
        assertEquals(5, ResponseParser.parseOnebringtwoTimeout(GaiaPacket(0x29, 0x03, byteArrayOf(0x05))))
    }

    @Test
    fun `encode led voice touch and onebringtwo`() {
        fun cmdOf(bytes: ByteArray) = bytes[7].toInt() and 0xFF
        assertEquals(0x26, GaiaCodec.encode(GaiaPacketBuilder.ledSet(true))[6].toInt() and 0xFF)
        assertEquals(0x02, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.ledSet(true))))
        assertEquals(0x1C, GaiaCodec.encode(GaiaPacketBuilder.voiceSet(true, 60, 3))[6].toInt() and 0xFF)
        assertEquals(listOf(0x01, 60, 3),
            GaiaCodec.encode(GaiaPacketBuilder.voiceSet(true, 60, 3)).drop(8).map { it.toInt() and 0xFF })
        assertEquals(0x03, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.touchSet(byteArrayOf(1, 2, 3, 4, 5)))))
        assertEquals(0x02, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.onebringtwoSet(true))))
        assertEquals(0x04, cmdOf(GaiaCodec.encode(GaiaPacketBuilder.onebringtwoTimeoutSet(5))))
    }

    @Test
    fun `parse anc mode`() {
        val p = GaiaPacket(0x41, 0x03, byteArrayOf(0x02))
        assertEquals(AncMode.TRANSPARENCY, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `parse anc mode from SET response`() {
        val p = GaiaPacket(0x41, 0x04, byteArrayOf(0x03, 0x02, 0x00))
        assertEquals(AncMode.ANTI_WIND, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `parse anc adaptive from SET response`() {
        val p = GaiaPacket(0x41, 0x04, byteArrayOf(0x01, 0x02, 0x00))
        assertEquals(AncMode.ADAPTIVE, ResponseParser.parseAncMode(p))
    }

    @Test
    fun `parse gain level from SET response`() {
        val p = GaiaPacket(0x1F, 0x02, byteArrayOf(0x02, 0x00, 0x00))
        assertEquals(GainLevel.LOW, ResponseParser.parseGainLevel(p))
    }

    @Test
    fun `parse anc error frame returns null`() {
        // FF 04 00 01 00 1D 41 84 06：响应 Feature + Cmd 错误位，payload 为错误码
        val error = GaiaPacket(0x41, 0x84, byteArrayOf(0x06))
        assertNull(ResponseParser.parseAncMode(error))
    }

    @Test
    fun `parse gain error frame returns null`() {
        val error = GaiaPacket(0x1F, 0x82, byteArrayOf(0x01))
        assertNull(ResponseParser.parseGainLevel(error))
    }

    @Test
    fun `parse anc notification returns null`() {
        val notification = GaiaPacket(0x40, 0x81, byteArrayOf(0x04))
        assertNull(ResponseParser.parseAncMode(notification))
    }

    @Test
    fun `parse unknown anc mode returns null`() {
        assertNull(ResponseParser.parseAncMode(GaiaPacket(0x41, 0x03, byteArrayOf(0x06))))
    }

    @Test
    fun `parse unknown gain level returns null`() {
        assertNull(ResponseParser.parseGainLevel(GaiaPacket(0x1F, 0x01, byteArrayOf(0x03))))
    }

    @Test
    fun `parse codec status by command id`() {
        val lhdc = GaiaPacket(0x21, 0x05, byteArrayOf(0x01))
        assertEquals(true, ResponseParser.parseLhdcStatus(lhdc))
        assertNull(ResponseParser.parseLdacStatus(lhdc))
        assertNull(ResponseParser.parseLc3Status(lhdc))

        val ldac = GaiaPacket(0x21, 0x02, byteArrayOf(0x01))
        assertEquals(true, ResponseParser.parseLdacStatus(ldac))
        assertNull(ResponseParser.parseLhdcStatus(ldac))

        val lc3 = GaiaPacket(0x21, 0x01, byteArrayOf(0x00))
        assertEquals(false, ResponseParser.parseLc3Status(lc3))
    }

    @Test
    fun `parse codec switch 0x00 is false and 0x01 is true`() {
        // 评审第 4 条：0x00 / 0x01 两个合法值必须分别映射为 false / true。
        // assertEquals(false, ...) 与 assertEquals(true, ...) 同时排除了 null 的情况。
        assertEquals(false, ResponseParser.parseLc3Status(GaiaPacket(0x21, 0x01, hex(0x00))))
        assertEquals(true, ResponseParser.parseLc3Status(GaiaPacket(0x21, 0x01, hex(0x01))))

        // LDAC / LHDC 的 0x00 / 0x01 同样要正确映射
        assertEquals(false, ResponseParser.parseLdacStatus(GaiaPacket(0x21, 0x02, hex(0x00))))
        assertEquals(true, ResponseParser.parseLdacStatus(GaiaPacket(0x21, 0x02, hex(0x01))))
        assertEquals(false, ResponseParser.parseLhdcStatus(GaiaPacket(0x21, 0x05, hex(0x00))))
        assertEquals(true, ResponseParser.parseLhdcStatus(GaiaPacket(0x21, 0x05, hex(0x01))))
    }

    @Test
    fun `parse codec switch unknown value 0x02 returns null`() {
        // 独立断言 0x02：不能和 0xFF 合并，否则只处理一个分支的 bug 会漏测
        assertNull(ResponseParser.parseLc3Status(GaiaPacket(0x21, 0x01, hex(0x02))))
    }

    @Test
    fun `parse codec switch unknown value 0xff on lc3 returns null`() {
        assertNull(ResponseParser.parseLc3Status(GaiaPacket(0x21, 0x01, hex(0xFF))))
    }

    @Test
    fun `parse codec switch unknown value 0xff on ldac returns null`() {
        assertNull(ResponseParser.parseLdacStatus(GaiaPacket(0x21, 0x02, hex(0xFF))))
    }

    @Test
    fun `parse codec switch unknown value 0xff on lhdc returns null`() {
        assertNull(ResponseParser.parseLhdcStatus(GaiaPacket(0x21, 0x05, hex(0xFF))))
    }

    @Test
    fun `parse codec switch on error frame returns null`() {
        // 响应 Feature + Cmd 错误位（0x01|0x80 / 0x02|0x80 / 0x05|0x80）
        assertNull(ResponseParser.parseLc3Status(GaiaPacket(0x21, 0x81, hex(0x01))))
        assertNull(ResponseParser.parseLdacStatus(GaiaPacket(0x21, 0x82, hex(0x01))))
        assertNull(ResponseParser.parseLhdcStatus(GaiaPacket(0x21, 0x85, hex(0x01))))
    }

    @Test
    fun `parse codec switch on notification returns null`() {
        // Feature 无响应位（0x20）+ Cmd 带错误位
        assertNull(ResponseParser.parseLc3Status(GaiaPacket(0x20, 0x81, hex(0x01))))
        // Feature 无响应位（0x20）+ 正常 Cmd，通知帧也不是查询响应
        assertNull(ResponseParser.parseLc3Status(GaiaPacket(0x20, 0x01, hex(0x01))))
    }

    @Test
    fun `parse codec switch empty payload returns null`() {
        assertNull(ResponseParser.parseLc3Status(GaiaPacket(0x21, 0x01)))
        assertNull(ResponseParser.parseLdacStatus(GaiaPacket(0x21, 0x02, byteArrayOf())))
        assertNull(ResponseParser.parseLhdcStatus(GaiaPacket(0x21, 0x05, ByteArray(0))))
    }

    @Test
    fun `error and success use protocol bits`() {
        val error = GaiaPacket(0x41, 0x84, byteArrayOf(0x06))
        assertTrue(ResponseParser.isError(error))
        assertFalse(ResponseParser.isSuccess(error))

        val response = GaiaPacket(0x41, 0x03, byteArrayOf(0x02))
        assertFalse(ResponseParser.isError(response))
        assertTrue(ResponseParser.isSuccess(response))

        val notification = GaiaPacket(0x40, 0x81, byteArrayOf(0x04))
        assertFalse(ResponseParser.isError(notification))
        assertFalse(ResponseParser.isSuccess(notification))

        val command = GaiaPacket(0x40, 0x03)
        assertFalse(ResponseParser.isError(command))
        assertFalse(ResponseParser.isSuccess(command))
    }

    // ========== StreamDecoder ==========

    private fun testPkt(fid: Int, cid: Int, vararg payload: Int): ByteArray {
        return GaiaCodec.encode(GaiaPacket(fid, cid, ByteArray(payload.size) { payload[it].toByte() }))
    }

    @Test
    fun `stream single`() {
        assertEquals(1, GaiaCodec.StreamDecoder().feed(testPkt(0x00, 0x05, 0x33, 0x2E)).size)
    }

    @Test
    fun `stream two packets`() {
        val d = GaiaCodec.StreamDecoder()
        assertEquals(2, d.feed(testPkt(0x00, 0x05) + testPkt(0x00, 0x14, 0x41)).size)
    }

    @Test
    fun `stream split`() {
        val d = GaiaCodec.StreamDecoder()
        val full = testPkt(0x00, 0x05, 0x33)
        assertEquals(0, d.feed(full.copyOfRange(0, 5)).size)
        assertEquals(1, d.feed(full.copyOfRange(5, full.size)).size)
    }

    @Test
    fun `stream byte by byte`() {
        val d = GaiaCodec.StreamDecoder()
        val full = testPkt(0x00, 0x07)
        var count = 0
        for (b in full) count += d.feed(byteArrayOf(b)).size
        assertEquals(1, count)
    }

    @Test
    fun `stream empty`() {
        assertEquals(0, GaiaCodec.StreamDecoder().feed(byteArrayOf()).size)
    }

    @Test
    fun `stream resyncs after oversized len`() {
        val d = GaiaCodec.StreamDecoder()
        // Len=0xFFFF 的坏帧头，后面跟一个正常帧
        val bad = hex(0xFF, 0x04, 0xFF, 0xFF, 0x00, 0x1D, 0x41, 0x03, 0x01)
        val good = testPkt(0x00, 0x05, 0x33)
        val packets = d.feed(bad + good)
        assertEquals(1, packets.size)
        assertEquals(0x05, packets[0].commandId)
    }
}
