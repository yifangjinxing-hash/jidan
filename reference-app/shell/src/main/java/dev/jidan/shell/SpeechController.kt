package dev.jidan.shell

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import java.util.Locale

internal class SpeechCallbackGate {
    private var generation = 0L
    private var stoppedGeneration: Long? = null

    fun next(): Long {
        stoppedGeneration = null
        return ++generation
    }

    fun requestStop() {
        stoppedGeneration = generation
    }

    fun invalidate() {
        generation += 1
    }

    fun isCurrent(candidate: Long): Boolean = candidate == generation

    fun acceptsProgress(candidate: Long): Boolean =
        isCurrent(candidate) && stoppedGeneration != candidate
}

internal class SpeechTimeoutGate {
    private var armedGeneration: Long? = null

    fun arm(generation: Long) {
        armedGeneration = generation
    }

    fun disarm() {
        armedGeneration = null
    }

    fun shouldFire(candidate: Long, current: Boolean, listening: Boolean): Boolean =
        armedGeneration == candidate && current && listening
}

class SpeechController(
    private val context: Context,
    private val listener: Listener,
) : RecognitionListener {
    interface Listener {
        fun onSpeechPreparing(onDevice: Boolean)
        fun onListeningStarted(onDevice: Boolean)
        fun onRecognizing()
        fun onPartialText(text: String)
        fun onFinalText(text: String)
        fun onSpeechFailure()
    }

    private var recognizer: SpeechRecognizer? = null
    private var onDeviceRecognizer = false
    private var recognizingNotified = false
    private var fallbackAttempted = false
    private var stopRequested = false
    private val callbackGate = SpeechCallbackGate()
    private val timeoutGate = SpeechTimeoutGate()
    private val mainHandler = Handler(Looper.getMainLooper())
    private var timeoutRunnable: Runnable? = null
    private var activeGeneration = 0L
    var isListening: Boolean = false
        private set

    fun isAvailable(): Boolean = SpeechRecognizer.isRecognitionAvailable(context)

    fun start() {
        if (isListening) return
        try {
            val onDevice = Build.VERSION.SDK_INT >= 31 &&
                SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
            recognizingNotified = false
            fallbackAttempted = false
            stopRequested = false
            isListening = true
            startRecognizer(onDevice)
        } catch (_: RuntimeException) {
            isListening = false
            disarmTimeout()
            recognizer?.destroy()
            recognizer = null
            listener.onSpeechFailure()
        }
    }

    fun stop() {
        if (!isListening) return
        stopRequested = true
        callbackGate.requestStop()
        notifyRecognizing()
        recognizer?.stopListening()
        armTimeout(activeGeneration, STOP_FINAL_TIMEOUT_MS)
    }

    fun cancel() {
        isListening = false
        stopRequested = true
        disarmTimeout()
        callbackGate.invalidate()
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
    }

    fun destroy() {
        cancel()
    }

    override fun onReadyForSpeech(params: Bundle?) {
        if (stopRequested) return
        listener.onListeningStarted(onDeviceRecognizer)
    }
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() {
        notifyRecognizing()
    }
    override fun onEvent(eventType: Int, params: Bundle?) = Unit

    override fun onPartialResults(partialResults: Bundle?) {
        if (stopRequested) return
        bestText(partialResults)?.let(listener::onPartialText)
    }

    override fun onResults(results: Bundle?) {
        isListening = false
        disarmTimeout()
        val text = bestText(results)
        if (text.isNullOrBlank()) listener.onSpeechFailure() else listener.onFinalText(text)
    }

    override fun onError(error: Int) {
        Log.w(TAG, "recognition error=$error onDevice=$onDeviceRecognizer fallback=$fallbackAttempted")
        if (!isListening) return
        if (onDeviceRecognizer && !fallbackAttempted && !stopRequested && isListening) {
            fallbackAttempted = true
            runCatching { startRecognizer(onDevice = false) }
                .onFailure {
                    isListening = false
                    disarmTimeout()
                    listener.onSpeechFailure()
                }
            return
        }
        isListening = false
        disarmTimeout()
        listener.onSpeechFailure()
    }

    @android.annotation.SuppressLint("NewApi")
    private fun startRecognizer(onDevice: Boolean) {
        val generation = callbackGate.next()
        activeGeneration = generation
        onDeviceRecognizer = onDevice
        recognizer?.destroy()
        recognizer = if (onDevice) {
            SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        } else {
            createAvailableSpeechRecognizer()
        }.also { value -> value.setRecognitionListener(generationListener(generation)) }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, onDevice)
        }
        listener.onSpeechPreparing(onDevice)
        recognizer?.startListening(intent)
        armTimeout(generation, RECOGNITION_TIMEOUT_MS)
    }

    private fun generationListener(generation: Long): RecognitionListener =
        object : RecognitionListener {
            private fun current(): Boolean =
                callbackGate.isCurrent(generation) && isListening

            private fun progressCurrent(): Boolean =
                callbackGate.acceptsProgress(generation) && isListening

            override fun onReadyForSpeech(params: Bundle?) {
                if (progressCurrent()) this@SpeechController.onReadyForSpeech(params)
            }

            override fun onBeginningOfSpeech() {
                if (current()) this@SpeechController.onBeginningOfSpeech()
            }

            override fun onRmsChanged(rmsdB: Float) {
                if (current()) this@SpeechController.onRmsChanged(rmsdB)
            }

            override fun onBufferReceived(buffer: ByteArray?) {
                if (current()) this@SpeechController.onBufferReceived(buffer)
            }

            override fun onEndOfSpeech() {
                if (current()) this@SpeechController.onEndOfSpeech()
            }

            override fun onError(error: Int) {
                if (current()) this@SpeechController.onError(error)
            }

            override fun onResults(results: Bundle?) {
                if (current()) this@SpeechController.onResults(results)
            }

            override fun onPartialResults(partialResults: Bundle?) {
                if (progressCurrent()) this@SpeechController.onPartialResults(partialResults)
            }

            override fun onEvent(eventType: Int, params: Bundle?) {
                if (current()) this@SpeechController.onEvent(eventType, params)
            }
        }

    private fun createAvailableSpeechRecognizer(): SpeechRecognizer {
        // Let Android use the recognition service selected by the user/system. Query order is
        // not a trust boundary and must never decide which process receives microphone audio.
        return SpeechRecognizer.createSpeechRecognizer(context)
    }

    private fun armTimeout(generation: Long, delayMs: Long) {
        timeoutRunnable?.let(mainHandler::removeCallbacks)
        timeoutGate.arm(generation)
        timeoutRunnable = Runnable {
            if (!timeoutGate.shouldFire(generation, callbackGate.isCurrent(generation), isListening)) {
                return@Runnable
            }
            isListening = false
            stopRequested = true
            timeoutRunnable = null
            timeoutGate.disarm()
            callbackGate.invalidate()
            recognizer?.cancel()
            recognizer?.destroy()
            recognizer = null
            listener.onSpeechFailure()
        }.also { mainHandler.postDelayed(it, delayMs) }
    }

    private fun disarmTimeout() {
        timeoutRunnable?.let(mainHandler::removeCallbacks)
        timeoutRunnable = null
        timeoutGate.disarm()
    }

    private fun notifyRecognizing() {
        if (recognizingNotified) return
        recognizingNotified = true
        listener.onRecognizing()
    }

    private fun bestText(bundle: Bundle?): String? =
        bundle
            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull()
            ?.trim()

    companion object {
        private const val TAG = "JidanSpeech"
        private const val RECOGNITION_TIMEOUT_MS = 15_000L
        private const val STOP_FINAL_TIMEOUT_MS = 3_000L
    }
}
