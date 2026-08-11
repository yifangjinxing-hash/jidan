package dev.jidan.shell

import java.security.MessageDigest

enum class ShellAction(val id: String) {
    OPEN_ALIPAY("app.open.alipay_frontdoor"),
    OPEN_MOBILEANJIAN("app.open.mobileanjian_candidate"),
    OPEN_SYSTEM_SETTINGS("android.settings.open"),
    OPEN_AUTOMATION_LAB("android.ui.sandbox_start"),
}

enum class ShellRiskLevel {
    NAVIGATION,
    SENSITIVE_EXPERIMENT,
}

enum class ShellExecutionMode {
    DIRECT,
    SANDBOX,
}

data class ActionProposal(
    val action: ShellAction,
    val title: String,
    val safetyMessage: String,
    val actionLabel: String,
    val riskLevel: ShellRiskLevel = ShellRiskLevel.NAVIGATION,
    val executionMode: ShellExecutionMode = ShellExecutionMode.DIRECT,
    val requiresConfirmation: Boolean = false,
) {
    val canonicalContract: String =
        "{\"action\":\"${action.id}\",\"arguments\":{}," +
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
