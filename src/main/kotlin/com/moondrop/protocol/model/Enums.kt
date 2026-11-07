package com.moondrop.protocol.model

/**
 * ANC 模式枚举 (基于水月雨 APP btsnoop 抓包确认)。
 *
 * 0x04 = 降噪组入口，SET 后进入降噪并恢复上次子模式（自适应或抗风噪），
 * 首次配对/上电时 ANC_QUERY 返回 0x04（此时无上次状态）。
 */
enum class AncMode(val value: Byte, val label: String, val available: Boolean = true) {
    OFF(0x00, "关闭"),
    ADAPTIVE(0x01, "自适应"),
    TRANSPARENCY(0x02, "通透"),
    ANTI_WIND(0x03, "抗风噪"),
    NOISE_CANCEL(0x04, "降噪");

    companion object {
        private val map = entries.associateBy { it.value }

        /** 未定义的值返回 null，避免把错误/未知状态静默当成 OFF。 */
        fun fromValue(value: Byte): AncMode? = map[value]
    }
}

/**
 * Gain 级别枚举。
 */
enum class GainLevel(val value: Byte, val label: String) {
    HIGH(0x00, "高"),
    MEDIUM(0x01, "中"),
    LOW(0x02, "低");

    companion object {
        private val map = entries.associateBy { it.value }

        /** 未定义的值返回 null，避免把错误/未知状态静默当成 MEDIUM。 */
        fun fromValue(value: Byte): GainLevel? = map[value]
    }
}
