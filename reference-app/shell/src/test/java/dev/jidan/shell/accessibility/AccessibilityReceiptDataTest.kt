package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class AccessibilityReceiptDataTest {
    private val base = AccessibilityReceiptData(
        phase = "RESULT",
        timestampMs = 1,
        sessionId = "session",
        lane = "SANDBOX",
        targetPackage = ExecutionLaneResolver.SANDBOX_PACKAGE,
        targetIdentitySha256 = "a".repeat(64),
        windowId = 7,
        planSha256 = "b".repeat(64),
        stepId = "set_password",
        kind = "SET_TEXT",
        sensitivity = "PASSWORD",
        beforeSha256 = "c".repeat(64),
        afterSha256 = "d".repeat(64),
        executorAttempted = true,
        osAccepted = true,
        postconditionVerified = true,
        effectStatus = EffectStatus.TRANSITION_VERIFIED.name,
        realWorldStatus = RealWorldStatus.SYNTHETIC_ONLY.name,
        syntheticCommit = false,
        realPayment = false,
        sensitiveValuePersisted = false,
        outcome = "transition_verified",
        attemptHash = "e".repeat(64),
        previousHash = "e".repeat(64),
    )

    @Test
    fun everySecurityConclusionChangesTheHash() {
        val original = base.hash()
        val mutations = listOf(
            base.copy(lane = "SHADOW"),
            base.copy(targetPackage = "other.package"),
            base.copy(executorAttempted = false),
            base.copy(effectStatus = EffectStatus.OUTCOME_UNKNOWN.name),
            base.copy(realWorldStatus = "UNKNOWN"),
            base.copy(syntheticCommit = true),
            base.copy(realPayment = true),
            base.copy(sensitiveValuePersisted = true),
            base.copy(attemptHash = null),
        )
        mutations.forEach { mutation -> assertNotEquals(original, mutation.hash()) }
        assertEquals(64, original.length)
    }
}
