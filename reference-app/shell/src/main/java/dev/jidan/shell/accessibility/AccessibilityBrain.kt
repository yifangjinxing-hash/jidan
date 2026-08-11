package dev.jidan.shell.accessibility

/**
 * Deterministic first brain. A model can replace this planner later, while the
 * target trust check, one-step executor and receipts stay outside the model.
 */
object AccessibilityBrain {
    private const val sandbox = ExecutionLaneResolver.SANDBOX_PACKAGE
    private const val statusId = "$sandbox:id/lab_status"
    private const val resultId = "$sandbox:id/lab_result"

    fun planSandbox(
        sessionId: String,
        observation: UiObservation,
        targetIdentity: TargetIdentity,
        references: LabValueReferences,
    ): UiActionPlan {
        require(observation.packageName == sandbox) { "sandbox observation required" }
        require(targetIdentity.packageName == sandbox) { "sandbox identity required" }
        listOf(
            references.recipient,
            references.amount,
            references.password,
            references.otp,
        ).forEach { reference ->
            require(EPHEMERAL_REFERENCE.matches(reference)) { "opaque value reference required" }
        }

        val recipient = observation.uniqueNode("$sandbox:id/lab_recipient")
        val amount = observation.uniqueNode("$sandbox:id/lab_amount")
        val password = observation.uniqueNode("$sandbox:id/lab_password")
        val otp = observation.uniqueNode("$sandbox:id/lab_otp")
        val submit = observation.uniqueNode("$sandbox:id/lab_submit")
        observation.uniqueNode(statusId)
        observation.uniqueNode(resultId)

        require(recipient.editable && !recipient.password) { "recipient role mismatch" }
        require(amount.editable && !amount.password) { "amount role mismatch" }
        require(password.editable && password.password) { "password role mismatch" }
        require(otp.editable && otp.password) { "OTP role mismatch" }
        require(submit.clickable && !submit.editable) { "submit role mismatch" }

        val steps = listOf(
            PlannedUiAction(
                id = "set_recipient",
                kind = UiActionKind.SET_TEXT,
                selector = recipient.selector(),
                ephemeralValueRef = references.recipient,
                postconditionViewId = statusId,
                postconditionMarker = "recipient_ready",
            ),
            PlannedUiAction(
                id = "set_amount",
                kind = UiActionKind.SET_TEXT,
                selector = amount.selector(),
                ephemeralValueRef = references.amount,
                sensitivity = Sensitivity.PAYMENT,
                postconditionViewId = statusId,
                postconditionMarker = "amount_ready",
            ),
            PlannedUiAction(
                id = "set_password",
                kind = UiActionKind.SET_TEXT,
                selector = password.selector(),
                ephemeralValueRef = references.password,
                sensitivity = Sensitivity.PASSWORD,
                postconditionViewId = statusId,
                postconditionMarker = "password_ready",
            ),
            PlannedUiAction(
                id = "set_otp",
                kind = UiActionKind.SET_TEXT,
                selector = otp.selector(),
                ephemeralValueRef = references.otp,
                sensitivity = Sensitivity.OTP,
                postconditionViewId = statusId,
                postconditionMarker = "otp_ready",
            ),
            PlannedUiAction(
                id = "submit_synthetic",
                kind = UiActionKind.CLICK,
                selector = submit.selector(),
                sensitivity = Sensitivity.PAYMENT,
                postconditionViewId = resultId,
                postconditionMarker = "synthetic_committed",
            ),
        )
        return UiActionPlan.create(
            id = "lab.$sessionId",
            handProviderId = HandProviderIds.BUILTIN_ACCESSIBILITY,
            handProviderRegistrationSha256 =
                HandProviderIds.BUILTIN_ACCESSIBILITY_REGISTRATION_SHA256,
            lane = ExecutionLane.SANDBOX,
            observationSha256 = observation.evidenceSha256,
            targetIdentitySha256 = targetIdentity.digestSha256,
            steps = steps,
        )
    }

    private fun UiObservation.uniqueNode(viewId: String): UiNodeSnapshot {
        val matches = nodes.filter { node ->
            node.packageName == sandbox && node.viewId == viewId
        }
        require(matches.size == 1) { "sandbox semantic node must be unique: $viewId" }
        return matches.single()
    }

    private fun UiNodeSnapshot.selector(): UiNodeSelector = UiNodeSelector(
        packageName = packageName,
        viewId = requireNotNull(viewId),
        expectedPath = path,
        expectedClassName = className,
        expectedClickable = clickable,
        expectedEditable = editable,
        expectedPassword = password,
    )

    private val EPHEMERAL_REFERENCE = Regex(
        "^ephemeral:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        RegexOption.IGNORE_CASE,
    )
}
