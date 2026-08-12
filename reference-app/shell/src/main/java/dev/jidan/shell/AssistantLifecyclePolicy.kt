package dev.jidan.shell

internal object AssistantLifecyclePolicy {
    fun remaining(deadlineElapsed: Long, nowElapsed: Long, timeoutMs: Long): Long =
        (deadlineElapsed - nowElapsed).coerceIn(0L, timeoutMs)

    fun restoredDeadline(remainingMs: Long, nowElapsed: Long, timeoutMs: Long): Long {
        val bounded = remainingMs.coerceIn(0L, timeoutMs)
        return if (bounded == 0L) 0L else nowElapsed + bounded
    }

    fun shouldPollAccessibility(connected: Boolean, attempt: Int, maxAttempts: Int): Boolean =
        !connected && attempt < maxAttempts
}
