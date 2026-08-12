package dev.jidan.daily.demo

import java.security.MessageDigest

object DailyAutomationContract {
    const val SESSION_NONCE_EXTRA = "dev.jidan.extra.ACCESSIBILITY_LAB_SESSION_NONCE"
    const val REQUEST_ID_EXTRA = "dev.jidan.extra.DAILY_REQUEST_ID"
    private const val SESSION_PREFIX = "jidan_daily_session:"

    fun noteDigest(note: String): String = sha256(note.trim())

    fun marker(nonce: String, state: String): String =
        "$SESSION_PREFIX${sha256(nonce)}|$state"

    fun emptyMarker(nonce: String): String = marker(nonce, "empty")

    fun noteReadyMarker(nonce: String, note: String): String =
        marker(nonce, "note_ready:${noteDigest(note)}")

    fun savedMarker(nonce: String, note: String): String =
        marker(nonce, "saved:${noteDigest(note)}")

    fun requestState(previousDigest: String?, noteDigest: String): DailyRequestState = when {
        previousDigest == null -> DailyRequestState.NEW
        previousDigest == noteDigest -> DailyRequestState.DUPLICATE
        else -> DailyRequestState.CONFLICT
    }

    fun sha256(value: String): String = MessageDigest
        .getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
}

enum class DailyRequestState {
    NEW,
    DUPLICATE,
    CONFLICT,
}
