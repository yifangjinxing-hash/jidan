package dev.jidan.shell.accessibility

import java.security.SecureRandom
import java.util.UUID

data class LabSession(
    val id: String,
    val launchNonce: String,
    val createdAtElapsedMs: Long,
    val expiresAtElapsedMs: Long,
    val targetIdentity: TargetIdentity,
    val valueReferences: LabValueReferences,
    val taskKind: AccessibilityTaskKind = AccessibilityTaskKind.SANDBOX_LAB,
    val targetSpec: OwnedTargetSpec = OwnedTargetRegistry.sandbox,
    val requestId: String? = null,
    val payloadSha256: String? = null,
    val dailyNoteText: String? = null,
)

/**
 * Session-scoped synthetic values. Handles are bound to one action, selector,
 * and sensitivity, consumed once, and removed on every terminal path.
 */
object LabSessionRegistry {
    private data class BoundValue(
        val actionId: String,
        val selectorViewId: String,
        val sensitivity: Sensitivity,
        var value: String,
    )

    private data class Active(
        val session: LabSession,
        val values: MutableMap<String, BoundValue>,
    )

    private val random = SecureRandom()
    private var active: Active? = null

    @Synchronized
    fun arm(
        targetIdentity: TargetIdentity,
        nowElapsedMs: Long = elapsedRealtimeMs(),
        ttlMs: Long = DEFAULT_TTL_MS,
    ): LabSession {
        require(ttlMs in 1..MAX_TTL_MS) { "invalid lab session TTL" }
        check(current(nowElapsedMs) == null) { "a lab session is already active" }

        val references = LabValueReferences(
            recipient = newReference(),
            amount = newReference(),
            password = newReference(),
            otp = newReference(),
        )
        val packageName = ExecutionLaneResolver.SANDBOX_PACKAGE
        val values = mutableMapOf(
            references.recipient to BoundValue(
                actionId = "set_recipient",
                selectorViewId = "$packageName:id/lab_recipient",
                sensitivity = Sensitivity.NONE,
                value = "测试商户-${UUID.randomUUID().toString().take(4)}",
            ),
            references.amount to BoundValue(
                actionId = "set_amount",
                selectorViewId = "$packageName:id/lab_amount",
                sensitivity = Sensitivity.PAYMENT,
                value = "0.01",
            ),
            references.password to BoundValue(
                actionId = "set_password",
                selectorViewId = "$packageName:id/lab_password",
                sensitivity = Sensitivity.PASSWORD,
                value = randomDigits(),
            ),
            references.otp to BoundValue(
                actionId = "set_otp",
                selectorViewId = "$packageName:id/lab_otp",
                sensitivity = Sensitivity.OTP,
                value = randomDigits(),
            ),
        )
        val session = LabSession(
            id = UUID.randomUUID().toString(),
            launchNonce = UUID.randomUUID().toString(),
            createdAtElapsedMs = nowElapsedMs,
            expiresAtElapsedMs = nowElapsedMs + ttlMs,
            targetIdentity = targetIdentity,
            valueReferences = references,
            taskKind = AccessibilityTaskKind.SANDBOX_LAB,
            targetSpec = OwnedTargetRegistry.sandbox,
        )
        active = Active(session, values)
        return session
    }

    @Synchronized
    fun armDaily(
        targetIdentity: TargetIdentity,
        requestId: String,
        noteText: String,
        nowElapsedMs: Long = elapsedRealtimeMs(),
        ttlMs: Long = DEFAULT_TTL_MS,
    ): LabSession {
        require(REQUEST_ID.matches(requestId)) { "invalid daily request id" }
        require(noteText.isNotBlank() && noteText.length <= 200) { "invalid daily note" }
        require(ttlMs in 1..MAX_TTL_MS) { "invalid daily session TTL" }
        check(targetIdentity.packageName == ExecutionLaneResolver.DAILY_PACKAGE) {
            "daily target identity required"
        }
        check(current(nowElapsedMs) == null) { "an accessibility session is already active" }

        val noteReference = newReference()
        val references = LabValueReferences(
            recipient = "",
            amount = "",
            password = "",
            otp = "",
            note = noteReference,
        )
        val inputId = "${ExecutionLaneResolver.DAILY_PACKAGE}:id/daily_note_input"
        val values = mutableMapOf(
            noteReference to BoundValue(
                actionId = "set_daily_note",
                selectorViewId = inputId,
                sensitivity = Sensitivity.NONE,
                value = noteText,
            ),
        )
        val session = LabSession(
            id = UUID.randomUUID().toString(),
            launchNonce = UUID.randomUUID().toString(),
            createdAtElapsedMs = nowElapsedMs,
            expiresAtElapsedMs = nowElapsedMs + ttlMs,
            targetIdentity = targetIdentity,
            valueReferences = references,
            taskKind = AccessibilityTaskKind.DAILY_NOTE,
            targetSpec = OwnedTargetRegistry.daily,
            requestId = requestId,
            payloadSha256 = sha256(noteText),
            dailyNoteText = noteText,
        )
        active = Active(session, values)
        return session
    }

    @Synchronized
    fun activeSession(nowElapsedMs: Long = elapsedRealtimeMs()): LabSession? =
        current(nowElapsedMs)?.session

    @Synchronized
    fun resolveAndConsume(
        sessionId: String,
        reference: String,
        actionId: String,
        selectorViewId: String,
        sensitivity: Sensitivity,
        nowElapsedMs: Long = elapsedRealtimeMs(),
    ): CharSequence? {
        val current = current(nowElapsedMs) ?: return null
        if (current.session.id != sessionId) return null
        val bound = current.values[reference] ?: return null
        if (
            bound.actionId != actionId ||
            bound.selectorViewId != selectorViewId ||
            bound.sensitivity != sensitivity
        ) {
            return null
        }
        current.values.remove(reference)
        return bound.value.also { bound.value = "" }
    }

    @Synchronized
    fun clear(sessionId: String) {
        val current = active ?: return
        if (current.session.id != sessionId) return
        wipe(current)
        active = null
    }

    @Synchronized
    fun clearActive() {
        active?.let(::wipe)
        active = null
    }

    @Synchronized
    internal fun remainingValueCount(nowElapsedMs: Long = elapsedRealtimeMs()): Int =
        current(nowElapsedMs)?.values?.size ?: 0

    private fun current(nowElapsedMs: Long): Active? {
        val current = active ?: return null
        if (nowElapsedMs >= current.session.expiresAtElapsedMs) {
            wipe(current)
            active = null
            return null
        }
        return current
    }

    private fun wipe(current: Active) {
        current.values.values.forEach { it.value = "" }
        current.values.clear()
    }

    private fun newReference(): String = "ephemeral:${UUID.randomUUID()}"

    private fun randomDigits(): String = random.nextInt(1_000_000)
        .toString()
        .padStart(6, '0')

    private fun elapsedRealtimeMs(): Long = System.nanoTime() / 1_000_000L

    private val REQUEST_ID = Regex(
        "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        RegexOption.IGNORE_CASE,
    )

    const val DEFAULT_TTL_MS = 30_000L
    private const val MAX_TTL_MS = 60_000L
}
