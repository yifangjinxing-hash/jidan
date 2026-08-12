package dev.jidan.shell.accessibility

object DailyNoteBrain {
    private const val daily = ExecutionLaneResolver.DAILY_PACKAGE
    private const val inputId = "$daily:id/daily_note_input"
    private const val saveId = "$daily:id/daily_note_save"
    private const val statusId = "$daily:id/daily_note_status"
    private const val resultId = "$daily:id/daily_note_result"

    fun plan(
        session: LabSession,
        observation: UiObservation,
    ): UiActionPlan {
        require(session.taskKind == AccessibilityTaskKind.DAILY_NOTE)
        require(session.targetIdentity.packageName == daily)
        require(observation.packageName == daily)
        val noteReference = requireNotNull(session.valueReferences.note)
        require(EPHEMERAL_REFERENCE.matches(noteReference))
        val payloadDigest = requireNotNull(session.payloadSha256)
        require(SHA256.matches(payloadDigest))

        val input = observation.uniqueNode(inputId)
        val save = observation.uniqueNode(saveId)
        observation.uniqueNode(statusId)
        observation.uniqueNode(resultId)
        require(input.editable && !input.password && input.valueState == "EMPTY") {
            "daily note input must be an empty non-password editor"
        }
        require(save.clickable && !save.editable) { "daily save role mismatch" }

        val steps = listOf(
            PlannedUiAction(
                id = "set_daily_note",
                kind = UiActionKind.SET_TEXT,
                selector = input.selector(),
                ephemeralValueRef = noteReference,
                postconditionViewId = statusId,
                postconditionMarker = "note_ready:$payloadDigest",
            ),
            PlannedUiAction(
                id = "save_daily_note",
                kind = UiActionKind.CLICK,
                selector = save.selector(),
                postconditionViewId = resultId,
                postconditionMarker = "saved:$payloadDigest",
            ),
        )
        return UiActionPlan.create(
            id = "daily.${requireNotNull(session.requestId)}",
            handProviderId = HandProviderIds.DAILY_ACCESSIBILITY,
            handProviderRegistrationSha256 =
                HandProviderIds.DAILY_ACCESSIBILITY_REGISTRATION_SHA256,
            lane = ExecutionLane.OWNED_APP,
            observationSha256 = observation.evidenceSha256,
            targetIdentitySha256 = session.targetIdentity.digestSha256,
            steps = steps,
        )
    }

    private fun UiObservation.uniqueNode(viewId: String): UiNodeSnapshot {
        val matches = nodes.filter { node -> node.packageName == daily && node.viewId == viewId }
        require(matches.size == 1) { "daily semantic node must be unique: $viewId" }
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
    private val SHA256 = Regex("^[0-9a-f]{64}$")
}
