package dev.jidan.shell

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import java.util.Locale

class SpeechController(
    private val context: Context,
    private val listener: Listener,
) : RecognitionListener {
    interface Listener {
        fun onListeningStarted(onDevice: Boolean)
        fun onPartialText(text: String)
        fun onFinalText(text: String)
        fun onSpeechFailure()
    }

    private var recognizer: SpeechRecognizer? = null
    var isListening: Boolean = false
        private set

    fun isAvailable(): Boolean = SpeechRecognizer.isRecognitionAvailable(context)

    fun start() {
        if (isListening) return
        try {
            val onDevice = Build.VERSION.SDK_INT >= 31 &&
                SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
            recognizer?.destroy()
            recognizer = if (onDevice) {
                SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
            } else {
                SpeechRecognizer.createSpeechRecognizer(context)
            }.also { value -> value.setRecognitionListener(this) }

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
                )
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag())
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                if (onDevice) putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            }
            isListening = true
            listener.onListeningStarted(onDevice)
            recognizer?.startListening(intent)
        } catch (_: RuntimeException) {
            isListening = false
            recognizer?.destroy()
            recognizer = null
            listener.onSpeechFailure()
        }
    }

    fun stop() {
        if (!isListening) return
        recognizer?.stopListening()
    }

    fun destroy() {
        isListening = false
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
    }

    override fun onReadyForSpeech(params: Bundle?) = Unit
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit

    override fun onPartialResults(partialResults: Bundle?) {
        bestText(partialResults)?.let(listener::onPartialText)
    }

    override fun onResults(results: Bundle?) {
        isListening = false
        val text = bestText(results)
        if (text.isNullOrBlank()) listener.onSpeechFailure() else listener.onFinalText(text)
    }

    override fun onError(error: Int) {
        isListening = false
        listener.onSpeechFailure()
    }

    private fun bestText(bundle: Bundle?): String? =
        bundle
            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull()
            ?.trim()
}
