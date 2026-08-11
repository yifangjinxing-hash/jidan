package dev.jidan.shell.accessibility

import java.security.MessageDigest

enum class ExecutionLane {
    SANDBOX,
    SHADOW,
}

enum class UiActionKind {
    SET_TEXT,
    CLICK,
}

enum class Sensitivity {
    NONE,
    PAYMENT,
    PASSWORD,
    OTP,
}

enum class EffectStatus {
    NOT_ATTEMPTED,
    FAILED_BEFORE_EFFECT,
    TRANSITION_VERIFIED,
    OUTCOME_UNKNOWN,
}

enum class RealWorldStatus {
    SYNTHETIC_ONLY,
}

data class TargetIdentity(
    val packageName: String,
    val versionCode: Long,
    val uid: Int,
    val signingCertificateSha256: String,
    val contractId: String,
) {
    val digestSha256: String = sha256(
        listOf(
            packageName,
            versionCode.toString(),
            uid.toString(),
            signingCertificateSha256,
            contractId,
        ).joinToString("\n"),
    )
}

data class LabValueReferences(
    val recipient: String,
    val amount: String,
    val password: String,
    val otp: String,
)

data class UiNodeSnapshot(
    val path: String,
    val packageName: String,
    val className: String,
    val viewId: String?,
    val labelDigest: String?,
    val valueState: String,
    val clickable: Boolean,
    val editable: Boolean,
    val password: Boolean,
)

data class UiObservation(
    val packageName: String,
    val windowId: Int,
    val sequence: Long,
    val nodes: List<UiNodeSnapshot>,
    val evidenceSha256: String,
)

data class UiNodeSelector(
    val packageName: String,
    val viewId: String,
    val expectedPath: String,
    val expectedClassName: String,
    val expectedClickable: Boolean,
    val expectedEditable: Boolean,
    val expectedPassword: Boolean,
)

data class PlannedUiAction(
    val id: String,
    val kind: UiActionKind,
    val selector: UiNodeSelector,
    val ephemeralValueRef: String? = null,
    val sensitivity: Sensitivity = Sensitivity.NONE,
    val postconditionViewId: String,
    val postconditionMarker: String,
)

data class UiActionPlan(
    val id: String,
    val handProviderId: String,
    val handProviderRegistrationSha256: String,
    val lane: ExecutionLane,
    val observationSha256: String,
    val targetIdentitySha256: String,
    val steps: List<PlannedUiAction>,
    val maxSteps: Int,
    val reobserveBudget: Int,
    val planSha256: String,
) {
    companion object {
        fun create(
            id: String,
            handProviderId: String,
            handProviderRegistrationSha256: String,
            lane: ExecutionLane,
            observationSha256: String,
            targetIdentitySha256: String,
            steps: List<PlannedUiAction>,
            maxSteps: Int = steps.size,
            reobserveBudget: Int = 1,
        ): UiActionPlan {
            val canonical = buildString {
                append(id).append('\n')
                append(handProviderId).append('\n')
                append(handProviderRegistrationSha256).append('\n')
                append(lane.name).append('\n')
                append(observationSha256).append('\n')
                append(targetIdentitySha256).append('\n')
                append(maxSteps).append('\n')
                append(reobserveBudget).append('\n')
                steps.forEach { step ->
                    append(step.id).append('|')
                    append(step.kind.name).append('|')
                    append(step.selector.packageName).append('|')
                    append(step.selector.viewId).append('|')
                    append(step.selector.expectedPath).append('|')
                    append(step.selector.expectedClassName).append('|')
                    append(step.selector.expectedClickable).append('|')
                    append(step.selector.expectedEditable).append('|')
                    append(step.selector.expectedPassword).append('|')
                    append(step.ephemeralValueRef.orEmpty()).append('|')
                    append(step.sensitivity.name).append('|')
                    append(step.postconditionViewId).append('|')
                    append(step.postconditionMarker).append('\n')
                }
            }
            return UiActionPlan(
                id = id,
                handProviderId = handProviderId,
                handProviderRegistrationSha256 = handProviderRegistrationSha256,
                lane = lane,
                observationSha256 = observationSha256,
                targetIdentitySha256 = targetIdentitySha256,
                steps = steps,
                maxSteps = maxSteps,
                reobserveBudget = reobserveBudget,
                planSha256 = sha256(canonical),
            )
        }
    }
}

object HandProviderIds {
    const val BUILTIN_ACCESSIBILITY = "android.hand.jidan.accessibility.v0.1"
    const val BUILTIN_ACCESSIBILITY_REGISTRATION_SHA256 =
        "3a435217c54c7c7e97f24d2de3d97fc43fc2ccf321d3aa85d049f47a28622920"
    const val MOBILEANJIAN_CANDIDATE = "android.hand.candidate.cyjh.mobileanjian.v0.1"
}

data class AccessibilityReceiptData(
    val phase: String,
    val timestampMs: Long,
    val sessionId: String,
    val lane: String,
    val targetPackage: String,
    val targetIdentitySha256: String,
    val windowId: Int,
    val planSha256: String,
    val stepId: String,
    val kind: String,
    val sensitivity: String,
    val beforeSha256: String,
    val afterSha256: String,
    val executorAttempted: Boolean?,
    val osAccepted: Boolean?,
    val postconditionVerified: Boolean,
    val effectStatus: String,
    val realWorldStatus: String,
    val syntheticCommit: Boolean,
    val realPayment: Boolean,
    val sensitiveValuePersisted: Boolean,
    val outcome: String,
    val attemptHash: String?,
    val previousHash: String,
) {
    fun canonical(): String = listOf(
        SCHEMA_VERSION,
        phase,
        timestampMs.toString(),
        sessionId,
        lane,
        targetPackage,
        targetIdentitySha256,
        windowId.toString(),
        planSha256,
        stepId,
        kind,
        sensitivity,
        beforeSha256,
        afterSha256,
        executorAttempted?.toString() ?: "null",
        osAccepted?.toString() ?: "null",
        postconditionVerified.toString(),
        effectStatus,
        realWorldStatus,
        syntheticCommit.toString(),
        realPayment.toString(),
        sensitiveValuePersisted.toString(),
        outcome,
        attemptHash.orEmpty(),
        previousHash,
    ).joinToString("\n")

    fun hash(): String = sha256(canonical())

    companion object {
        const val SCHEMA_VERSION = "jidan.accessibility.receipt.v0.2"
    }
}

object ExecutionLaneResolver {
    const val SANDBOX_PACKAGE = "dev.jidan.accessibility.sandbox"

    fun resolve(targetPackage: String, trustedSandbox: Boolean): ExecutionLane =
        if (targetPackage == SANDBOX_PACKAGE && trustedSandbox) {
            ExecutionLane.SANDBOX
        } else {
            ExecutionLane.SHADOW
        }
}

internal fun sha256(value: String): String = MessageDigest
    .getInstance("SHA-256")
    .digest(value.toByteArray(Charsets.UTF_8))
    .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
