package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessibilityBrainTest {
    @Test
    fun sandboxPlanKeepsSensitiveActionsWithoutPersistingTheirValues() {
        val packageName = ExecutionLaneResolver.SANDBOX_PACKAGE
        val identity = TargetIdentity(
            packageName = packageName,
            versionCode = 1,
            uid = 12345,
            signingCertificateSha256 = "c".repeat(64),
            contractId = AccessibilityExecutionPolicy.SANDBOX_CONTRACT_ID,
        )
        val references = LabValueReferences(
            recipient = "ephemeral:11111111-1111-4111-8111-111111111111",
            amount = "ephemeral:22222222-2222-4222-8222-222222222222",
            password = "ephemeral:33333333-3333-4333-8333-333333333333",
            otp = "ephemeral:44444444-4444-4444-8444-444444444444",
        )
        val ids = listOf(
            "lab_recipient",
            "lab_amount",
            "lab_password",
            "lab_otp",
            "lab_submit",
            "lab_status",
            "lab_result",
        )
        val observation = UiObservation(
            packageName = packageName,
            windowId = 7,
            sequence = 1,
            nodes = ids.mapIndexed { index, id ->
                UiNodeSnapshot(
                    path = "0.$index",
                    packageName = packageName,
                    className = if (id == "lab_submit") {
                        "android.widget.Button"
                    } else {
                        "android.widget.EditText"
                    },
                    viewId = "$packageName:id/$id",
                    labelDigest = null,
                    valueState = if (id.startsWith("lab_") && id !in setOf("lab_submit", "lab_status", "lab_result")) {
                        "EMPTY"
                    } else {
                        "NOT_APPLICABLE"
                    },
                    clickable = id == "lab_submit",
                    editable = id in setOf("lab_recipient", "lab_amount", "lab_password", "lab_otp"),
                    password = id in setOf("lab_password", "lab_otp"),
                )
            },
            evidenceSha256 = "a".repeat(64),
        )

        val plan = AccessibilityBrain.planSandbox("session-1", observation, identity, references)

        assertEquals(ExecutionLane.SANDBOX, plan.lane)
        assertEquals(5, plan.steps.size)
        assertTrue(plan.steps.any { it.sensitivity == Sensitivity.PAYMENT })
        assertTrue(plan.steps.any { it.sensitivity == Sensitivity.PASSWORD })
        assertTrue(plan.steps.any { it.sensitivity == Sensitivity.OTP })
        assertEquals(64, plan.planSha256.length)
        assertEquals(identity.digestSha256, plan.targetIdentitySha256)
        assertEquals(HandProviderIds.BUILTIN_ACCESSIBILITY, plan.handProviderId)
        assertEquals(
            HandProviderIds.BUILTIN_ACCESSIBILITY_REGISTRATION_SHA256,
            plan.handProviderRegistrationSha256,
        )
        assertEquals(
            "3a435217c54c7c7e97f24d2de3d97fc43fc2ccf321d3aa85d049f47a28622920",
            plan.handProviderRegistrationSha256,
        )
        assertTrue(plan.steps.mapNotNull { it.ephemeralValueRef }.all { it.startsWith("ephemeral:") })
        assertFalse(plan.toString().contains("246810"))
        assertFalse(plan.toString().contains("123456"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun incompleteSemanticsStopsBeforeExecution() {
        AccessibilityBrain.planSandbox(
            "session-2",
            UiObservation(
                packageName = ExecutionLaneResolver.SANDBOX_PACKAGE,
                windowId = 1,
                sequence = 1,
                nodes = emptyList(),
                evidenceSha256 = "b".repeat(64),
            ),
            TargetIdentity(
                packageName = ExecutionLaneResolver.SANDBOX_PACKAGE,
                versionCode = 1,
                uid = 1,
                signingCertificateSha256 = "d".repeat(64),
                contractId = AccessibilityExecutionPolicy.SANDBOX_CONTRACT_ID,
            ),
            LabValueReferences(
                recipient = "ephemeral:11111111-1111-4111-8111-111111111111",
                amount = "ephemeral:22222222-2222-4222-8222-222222222222",
                password = "ephemeral:33333333-3333-4333-8333-333333333333",
                otp = "ephemeral:44444444-4444-4444-8444-444444444444",
            ),
        )
    }
}
