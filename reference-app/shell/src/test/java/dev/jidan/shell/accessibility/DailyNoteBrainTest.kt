package dev.jidan.shell.accessibility

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class DailyNoteBrainTest {
    private val packageName = ExecutionLaneResolver.DAILY_PACKAGE
    private val identity = TargetIdentity(
        packageName = packageName,
        versionCode = 1,
        uid = 12345,
        signingCertificateSha256 = "a".repeat(64),
        contractId = OwnedTargetRegistry.DAILY_CONTRACT_ID,
    )

    @Before
    fun clearBefore() = LabSessionRegistry.clearActive()

    @After
    fun clearAfter() = LabSessionRegistry.clearActive()

    @Test
    fun planIsExactlySetTextThenSaveAndPinsTheDailyProvider() {
        val session = LabSessionRegistry.armDaily(
            targetIdentity = identity,
            requestId = "11111111-1111-4111-8111-111111111111",
            noteText = "明天买鸡蛋",
        )

        val plan = DailyNoteBrain.plan(session, readyObservation())

        assertEquals(ExecutionLane.OWNED_APP, plan.lane)
        assertEquals(2, plan.steps.size)
        assertEquals(2, plan.maxSteps)
        assertEquals(listOf(UiActionKind.SET_TEXT, UiActionKind.CLICK), plan.steps.map { it.kind })
        assertEquals(listOf("set_daily_note", "save_daily_note"), plan.steps.map { it.id })
        assertEquals(HandProviderIds.DAILY_ACCESSIBILITY, plan.handProviderId)
        assertEquals(
            "652eca8492257de7617519f2adc120bf57e366265f63c8b31147a8d2c9bb325b",
            plan.handProviderRegistrationSha256,
        )
        assertEquals("note_ready:${session.payloadSha256}", plan.steps[0].postconditionMarker)
        assertEquals("saved:${session.payloadSha256}", plan.steps[1].postconditionMarker)
        assertTrue(plan.steps[0].ephemeralValueRef?.startsWith("ephemeral:") == true)
        assertFalse(plan.toString().contains("明天买鸡蛋"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun aPrefilledEditorStopsBeforePlanning() {
        DailyNoteBrain.plan(
            LabSessionRegistry.armDaily(
                targetIdentity = identity,
                requestId = "11111111-1111-4111-8111-111111111111",
                noteText = "明天买鸡蛋",
            ),
            readyObservation(inputState = "NON_EMPTY"),
        )
    }

    private fun readyObservation(inputState: String = "EMPTY"): UiObservation {
        val ids = listOf(
            "daily_note_input",
            "daily_note_save",
            "daily_note_status",
            "daily_note_result",
        )
        return UiObservation(
            packageName = packageName,
            windowId = 7,
            sequence = 1,
            nodes = ids.mapIndexed { index, id ->
                UiNodeSnapshot(
                    path = "0.$index",
                    packageName = packageName,
                    className = when (id) {
                        "daily_note_input" -> "android.widget.EditText"
                        "daily_note_save" -> "android.widget.Button"
                        else -> "android.widget.TextView"
                    },
                    viewId = "$packageName:id/$id",
                    labelDigest = null,
                    valueState = if (id == "daily_note_input") inputState else "NOT_APPLICABLE",
                    clickable = id == "daily_note_save",
                    editable = id == "daily_note_input",
                    password = false,
                )
            },
            evidenceSha256 = "b".repeat(64),
        )
    }
}
