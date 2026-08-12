package dev.jidan.shell

import java.security.MessageDigest
import java.util.UUID

enum class ShellAction(val id: String) {
    OPEN_ALIPAY("app.open.alipay_frontdoor"),
    OPEN_MOBILEANJIAN("app.open.mobileanjian_candidate"),
    OPEN_SYSTEM_SETTINGS("android.settings.open"),
    OPEN_AUTOMATION_LAB("android.ui.sandbox_start"),
    CREATE_DAILY_NOTE("daily.note.create"),
}

enum class ShellRiskLevel {
    NAVIGATION,
    SENSITIVE_EXPERIMENT,
    OWNED_APP_WRITE,
}

enum class ShellExecutionMode {
    DIRECT,
    SANDBOX,
    OWNED_APP,
}

sealed interface ActionArguments {
    fun canonicalJson(): String

    data object Empty : ActionArguments {
        override fun canonicalJson(): String = "{}"
    }

    data class DailyNote(
        val requestId: String,
        val text: String,
    ) : ActionArguments {
        init {
            require(UUID_PATTERN.matches(requestId)) { "daily note requestId must be a UUID" }
            require(text.isNotBlank() && text.length <= 200) { "daily note text is out of bounds" }
            require(text == text.trim()) { "daily note text must already be trimmed" }
        }

        override fun canonicalJson(): String =
            "{\"requestId\":${jsonString(requestId)},\"text\":${jsonString(text)}}"
    }

    companion object {
        fun dailyNote(text: String): DailyNote = DailyNote(UUID.randomUUID().toString(), text)

        fun dailyNote(requestId: String, text: String): DailyNote = DailyNote(requestId, text)

        private val UUID_PATTERN = Regex(
            "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            RegexOption.IGNORE_CASE,
        )

        internal fun jsonString(value: String): String = buildString {
            append('"')
            value.forEach { character ->
                when (character) {
                    '"' -> append("\\\"")
                    '\\' -> append("\\\\")
                    '\b' -> append("\\b")
                    '\u000c' -> append("\\f")
                    '\n' -> append("\\n")
                    '\r' -> append("\\r")
                    '\t' -> append("\\t")
                    else -> if (character.code < 0x20) {
                        append("\\u%04x".format(character.code))
                    } else {
                        append(character)
                    }
                }
            }
            append('"')
        }
    }
}

data class ActionProposal(
    val action: ShellAction,
    val title: String,
    val safetyMessage: String,
    val actionLabel: String,
    val riskLevel: ShellRiskLevel = ShellRiskLevel.NAVIGATION,
    val executionMode: ShellExecutionMode = ShellExecutionMode.DIRECT,
    val requiresConfirmation: Boolean = false,
    val arguments: ActionArguments = ActionArguments.Empty,
) {
    init {
        val isDailyAction = action == ShellAction.CREATE_DAILY_NOTE
        require(isDailyAction == (arguments is ActionArguments.DailyNote)) {
            "daily note arguments cannot cross an action boundary"
        }
        if (isDailyAction) {
            require(riskLevel == ShellRiskLevel.OWNED_APP_WRITE)
            require(executionMode == ShellExecutionMode.OWNED_APP)
            require(!requiresConfirmation)
        }
    }

    val canonicalContract: String =
        "{\"action\":\"${action.id}\",\"arguments\":${arguments.canonicalJson()}," +
            "\"riskLevel\":\"${riskLevel.name}\"," +
            "\"executionMode\":\"${executionMode.name}\"," +
            "\"requiresConfirmation\":$requiresConfirmation}"

    val digest: String = sha256(canonicalContract)

    companion object {
        fun sha256(value: String): String = MessageDigest
            .getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
    }
}

sealed interface ParseResult {
    data class Proposal(val value: ActionProposal) : ParseResult
    data class Rejected(val reason: String) : ParseResult
    data class Unknown(val suggestion: String) : ParseResult
}
