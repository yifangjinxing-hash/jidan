package dev.jidan.shell

import android.content.Context
import android.os.SystemClock
import android.util.Log
import java.io.File

/** A small, device-local flight recorder. It never uploads data or stores command text. */
object AssistantDiagnostics {
    private const val TAG = "JidanAssistant"

    @Synchronized
    fun record(context: Context, event: String, outcome: String, detail: String = "") {
        val safeEvent = event.jsonSafe(64)
        val safeOutcome = outcome.jsonSafe(96)
        val safeDetail = detail.jsonSafe(240)
        Log.i(TAG, "$safeEvent outcome=$safeOutcome detail=$safeDetail")
        runCatching {
            val directory = context.applicationContext.filesDir
            DiagnosticsFileStore.append(
                directory,
                "{\"wallTimeMs\":${System.currentTimeMillis()}," +
                    "\"elapsedMs\":${SystemClock.elapsedRealtime()}," +
                    "\"event\":\"$safeEvent\",\"outcome\":\"$safeOutcome\"," +
                    "\"detail\":\"$safeDetail\"}\n",
            )
        }.onFailure { error ->
            Log.w(TAG, "diagnostic_write_failed", error)
        }
    }

    private fun String.jsonSafe(limit: Int): String =
        take(limit)
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\r", " ")
            .replace("\n", " ")
}

internal object DiagnosticsFileStore {
    const val FILE_NAME = "assistant-diagnostics.jsonl"
    const val PREVIOUS_FILE_NAME = "assistant-diagnostics.previous.jsonl"
    const val SEGMENT_MAX_BYTES = 256 * 1024L

    fun append(directory: File, line: String) {
        directory.mkdirs()
        val current = File(directory, FILE_NAME)
        val bytes = line.toByteArray(Charsets.UTF_8)
        if (current.length() + bytes.size > SEGMENT_MAX_BYTES) {
            rotate(current, File(directory, PREVIOUS_FILE_NAME))
        }
        current.appendBytes(bytes)
    }

    private fun rotate(current: File, previous: File) {
        try {
            if (current.exists()) current.copyTo(previous, overwrite = true)
        } finally {
            // Losing old diagnostics is preferable to letting a failed rename grow without bound.
            current.writeBytes(byteArrayOf())
        }
    }
}
