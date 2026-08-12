package dev.jidan.shell.accessibility

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

class LabSessionRegistryTest {
    private val identity = TargetIdentity(
        packageName = ExecutionLaneResolver.SANDBOX_PACKAGE,
        versionCode = 1,
        uid = 12345,
        signingCertificateSha256 = "e".repeat(64),
        contractId = AccessibilityExecutionPolicy.SANDBOX_CONTRACT_ID,
    )
    private val dailyIdentity = TargetIdentity(
        packageName = ExecutionLaneResolver.DAILY_PACKAGE,
        versionCode = 1,
        uid = 12346,
        signingCertificateSha256 = "f".repeat(64),
        contractId = OwnedTargetRegistry.DAILY_CONTRACT_ID,
    )

    @Before
    fun clearBefore() = LabSessionRegistry.clearActive()

    @After
    fun clearAfter() = LabSessionRegistry.clearActive()

    @Test
    fun handleIsBoundConsumedOnceAndSessionExpiresMonotonically() {
        val session = LabSessionRegistry.arm(identity, nowElapsedMs = 100, ttlMs = 50)

        assertNull(
            LabSessionRegistry.resolveAndConsume(
                sessionId = session.id,
                reference = session.valueReferences.password,
                actionId = "set_recipient",
                selectorViewId = "${ExecutionLaneResolver.SANDBOX_PACKAGE}:id/lab_recipient",
                sensitivity = Sensitivity.NONE,
                nowElapsedMs = 120,
            ),
        )
        assertEquals(4, LabSessionRegistry.remainingValueCount(120))

        val resolved = LabSessionRegistry.resolveAndConsume(
            sessionId = session.id,
            reference = session.valueReferences.password,
            actionId = "set_password",
            selectorViewId = "${ExecutionLaneResolver.SANDBOX_PACKAGE}:id/lab_password",
            sensitivity = Sensitivity.PASSWORD,
            nowElapsedMs = 120,
        )
        assertNotNull(resolved)
        assertNull(
            LabSessionRegistry.resolveAndConsume(
                sessionId = session.id,
                reference = session.valueReferences.password,
                actionId = "set_password",
                selectorViewId = "${ExecutionLaneResolver.SANDBOX_PACKAGE}:id/lab_password",
                sensitivity = Sensitivity.PASSWORD,
                nowElapsedMs = 121,
            ),
        )
        assertEquals(3, LabSessionRegistry.remainingValueCount(121))

        assertNull(LabSessionRegistry.activeSession(150))
        assertEquals(0, LabSessionRegistry.remainingValueCount(150))
    }

    @Test(expected = IllegalStateException::class)
    fun activeSessionCannotBeSilentlyReplaced() {
        LabSessionRegistry.arm(identity, nowElapsedMs = 100, ttlMs = 50)
        LabSessionRegistry.arm(identity, nowElapsedMs = 120, ttlMs = 50)
    }

    @Test
    fun dailyPayloadIsBoundToOneSelectorAndConsumedOnce() {
        val requestId = "11111111-1111-4111-8111-111111111111"
        val session = LabSessionRegistry.armDaily(
            targetIdentity = dailyIdentity,
            requestId = requestId,
            noteText = "明天买鸡蛋",
            nowElapsedMs = 100,
            ttlMs = 50,
        )
        val noteReference = requireNotNull(session.valueReferences.note)

        assertEquals(AccessibilityTaskKind.DAILY_NOTE, session.taskKind)
        assertEquals(OwnedTargetRegistry.daily, session.targetSpec)
        assertEquals(requestId, session.requestId)
        assertEquals(sha256("明天买鸡蛋"), session.payloadSha256)
        assertEquals(1, LabSessionRegistry.remainingValueCount(100))
        assertNull(
            LabSessionRegistry.resolveAndConsume(
                sessionId = session.id,
                reference = noteReference,
                actionId = "set_daily_note",
                selectorViewId = "${ExecutionLaneResolver.DAILY_PACKAGE}:id/wrong_input",
                sensitivity = Sensitivity.NONE,
                nowElapsedMs = 110,
            ),
        )
        assertEquals(
            "明天买鸡蛋",
            LabSessionRegistry.resolveAndConsume(
                sessionId = session.id,
                reference = noteReference,
                actionId = "set_daily_note",
                selectorViewId = "${ExecutionLaneResolver.DAILY_PACKAGE}:id/daily_note_input",
                sensitivity = Sensitivity.NONE,
                nowElapsedMs = 110,
            ),
        )
        assertNull(
            LabSessionRegistry.resolveAndConsume(
                sessionId = session.id,
                reference = noteReference,
                actionId = "set_daily_note",
                selectorViewId = "${ExecutionLaneResolver.DAILY_PACKAGE}:id/daily_note_input",
                sensitivity = Sensitivity.NONE,
                nowElapsedMs = 111,
            ),
        )
        assertEquals(0, LabSessionRegistry.remainingValueCount(111))
    }
}
