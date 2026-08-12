package dev.jidan.shell.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Test

class DailyNoteReceiptDataTest {
    private val base = DailyNoteReceiptData(
        phase = DailyNoteReceiptSemantics.RESULT,
        timestampMs = 1,
        sessionId = "session",
        requestId = "11111111-1111-4111-8111-111111111111",
        targetIdentitySha256 = "a".repeat(64),
        windowId = 7,
        planSha256 = "b".repeat(64),
        stepId = "save_daily_note",
        kind = UiActionKind.CLICK.name,
        payloadSha256 = "c".repeat(64),
        beforeSha256 = "d".repeat(64),
        afterSha256 = "e".repeat(64),
        executorAttempted = true,
        osAccepted = true,
        postconditionVerified = true,
        effectStatus = EffectStatus.TRANSITION_VERIFIED.name,
        noteSaved = true,
        navigationAccepted = null,
        rawPayloadInReceipt = false,
        outcome = "transition_verified",
        attemptHash = "f".repeat(64),
        previousHash = "f".repeat(64),
    )

    @Test
    fun verifiedSaveIsOwnedLocalAndContainsOnlyThePayloadDigest() {
        DailyNoteReceiptSemantics.validate(base)

        assertEquals(64, base.hash().length)
        assertFalse(base.canonical().contains("明天买鸡蛋"))
        assertFalse(base.rawPayloadInReceipt)
        assertNotEquals(base.hash(), base.copy(noteSaved = false).hash())
        assertNotEquals(base.hash(), base.copy(payloadSha256 = "0".repeat(64)).hash())
    }

    @Test(expected = IllegalStateException::class)
    fun rawPayloadClaimIsRejected() {
        DailyNoteReceiptSemantics.validate(base.copy(rawPayloadInReceipt = true))
    }

    @Test(expected = IllegalStateException::class)
    fun setTextCannotClaimTheNoteWasSaved() {
        DailyNoteReceiptSemantics.validate(
            base.copy(stepId = "set_daily_note", kind = UiActionKind.SET_TEXT.name),
        )
    }
}
