package dev.jidan.shell

/** Process-local only. Android saved-state never receives the pending command text. */
object PendingAccessibilityMemory {
    @Volatile
    internal var elapsedMs: () -> Long = { System.nanoTime() / 1_000_000L }

    @Volatile
    private var proposal: ActionProposal? = null

    @Volatile
    private var expiresAtElapsed = 0L

    fun remember(value: ActionProposal) {
        proposal = value
        expiresAtElapsed = elapsedMs() + TTL_MS
    }

    fun findDaily(requestId: String): ActionProposal? {
        val current = current() ?: return null
        val arguments = current.arguments as? ActionArguments.DailyNote ?: return null
        return current.takeIf {
            current.action == ShellAction.CREATE_DAILY_NOTE && arguments.requestId == requestId
        }
    }

    fun takeIfCurrent(value: ActionProposal): ActionProposal? =
        current()?.takeIf { it === value }

    fun clearIf(value: ActionProposal?) {
        if (value != null && proposal === value) clear()
    }

    fun clear() {
        proposal = null
        expiresAtElapsed = 0L
    }

    internal fun resetClockForTest() {
        elapsedMs = { System.nanoTime() / 1_000_000L }
    }

    private fun current(): ActionProposal? {
        if (elapsedMs() > expiresAtElapsed) {
            clear()
            return null
        }
        return proposal
    }

    private const val TTL_MS = 60_000L
}
