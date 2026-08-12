package dev.jidan.shell

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class AssistantUiStateTest {
    @Test
    fun staleSpeechCallbacksCannotCrossRecognizerFallback() {
        val gate = SpeechCallbackGate()
        val firstRecognizer = gate.next()
        val fallbackRecognizer = gate.next()

        assertEquals(false, gate.isCurrent(firstRecognizer))
        assertEquals(true, gate.isCurrent(fallbackRecognizer))

        gate.invalidate()
        assertEquals(false, gate.isCurrent(fallbackRecognizer))
    }

    @Test
    fun stopBeforeReadyRejectsProgressButKeepsTheFinalCallbackEligible() {
        val gate = SpeechCallbackGate()
        val recognizer = gate.next()

        gate.requestStop()

        assertEquals(false, gate.acceptsProgress(recognizer))
        assertEquals(true, gate.isCurrent(recognizer))
    }

    @Test
    fun speechTimeoutCannotCrossIntoANewerRecognizerGeneration() {
        val callbacks = SpeechCallbackGate()
        val timeout = SpeechTimeoutGate()
        val oldRecognizer = callbacks.next()
        timeout.arm(oldRecognizer)
        callbacks.next()

        assertEquals(
            false,
            timeout.shouldFire(oldRecognizer, callbacks.isCurrent(oldRecognizer), listening = true),
        )
    }

    @Test
    fun stopTimeoutReleasesARecognizerThatNeverReturnsAFinalCallback() {
        val callbacks = SpeechCallbackGate()
        val timeout = SpeechTimeoutGate()
        val recognizer = callbacks.next()
        timeout.arm(recognizer)

        assertEquals(
            true,
            timeout.shouldFire(recognizer, callbacks.isCurrent(recognizer), listening = true),
        )
        timeout.disarm()
        assertEquals(
            false,
            timeout.shouldFire(recognizer, callbacks.isCurrent(recognizer), listening = true),
        )
    }

    @Test
    fun microphoneIsNotListeningUntilRecognizerIsReady() {
        val preparing = AssistantUiState.preparingMicrophone()
        val listening = AssistantUiState.listening()

        assertEquals(AssistantUiState.Phase.PREPARING_MICROPHONE, preparing.phase)
        assertNotEquals(AssistantUiState.Tone.LISTENING, preparing.tone)
        assertEquals(AssistantUiState.Phase.LISTENING, listening.phase)
    }

    @Test
    fun dispatchAcceptedIsVerifyingNotSuccess() {
        val state = AssistantUiState.verifying("打开系统设置")

        assertEquals(AssistantUiState.Phase.VERIFYING, state.phase)
        assertNotEquals(AssistantUiState.Tone.SUCCESS, state.tone)
    }

    @Test
    fun returningFromAnUnverifiedHandoffHasANeutralTerminalState() {
        val state = AssistantUiState.handedOff("打开系统设置")

        assertEquals(AssistantUiState.Phase.HANDED_OFF, state.phase)
        assertEquals(AssistantUiState.Tone.IDLE, state.tone)
        assertNotEquals(AssistantUiState.Tone.SUCCESS, state.tone)
    }

    @Test
    fun aHandoffThatNeverLeftTheForegroundDoesNotClaimItReturned() {
        val state = AssistantUiState.handoffNotObserved("打开系统设置")

        assertEquals(AssistantUiState.Phase.HANDED_OFF, state.phase)
        assertEquals(AssistantUiState.Tone.IDLE, state.tone)
        assertEquals(false, state.title.contains("返回"))
    }

    @Test
    fun savedDeadlinesAreDurationsBoundedToTheCurrentSession() {
        assertEquals(30_000L, AssistantLifecyclePolicy.remaining(90_000L, 10_000L, 30_000L))
        assertEquals(0L, AssistantLifecyclePolicy.remaining(9_000L, 10_000L, 30_000L))
        assertEquals(40_000L, AssistantLifecyclePolicy.restoredDeadline(80_000L, 10_000L, 30_000L))
    }

    @Test
    fun accessibilityReturnPollsUntilConnectedOrTheBoundedDeadline() {
        assertEquals(true, AssistantLifecyclePolicy.shouldPollAccessibility(false, 0, 11))
        assertEquals(false, AssistantLifecyclePolicy.shouldPollAccessibility(true, 0, 11))
        assertEquals(false, AssistantLifecyclePolicy.shouldPollAccessibility(false, 11, 11))
    }

    @Test
    fun onlyVerifiedCompletionUsesSuccess() {
        val state = AssistantUiState.completed("已记下“明天买鸡蛋”")

        assertEquals(AssistantUiState.Phase.COMPLETED, state.phase)
        assertEquals(AssistantUiState.Tone.SUCCESS, state.tone)
    }

    @Test
    fun failureNeverClaimsCompletion() {
        val state = AssistantUiState.failed("没有找到按键精灵")

        assertEquals(AssistantUiState.Phase.FAILED, state.phase)
        assertEquals(AssistantUiState.Tone.FAILURE, state.tone)
        assertNotEquals(AssistantUiState.Phase.COMPLETED, state.phase)
    }
}
