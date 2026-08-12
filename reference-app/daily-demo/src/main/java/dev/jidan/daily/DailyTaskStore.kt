package dev.jidan.daily.demo

import android.content.Context

class DailyTaskStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun load(): List<DailyTask> = DailyTaskCodec.decode(preferences.getString(TASKS_KEY, null))

    fun requestDigest(requestId: String): String? =
        preferences.getString(requestKey(requestId), null)

    /** Synchronous so a saved marker is never exposed before the note reaches disk. */
    fun commit(
        tasks: List<DailyTask>,
        requestId: String? = null,
        noteDigest: String? = null,
    ): Boolean {
        val editor = preferences.edit().putString(TASKS_KEY, DailyTaskCodec.encode(tasks))
        if (requestId != null && noteDigest != null) {
            editor.putString(requestKey(requestId), noteDigest)
        }
        return editor.commit()
    }

    private fun requestKey(requestId: String): String =
        "$REQUEST_KEY_PREFIX${DailyAutomationContract.sha256(requestId)}"

    private companion object {
        const val PREFERENCES_NAME = "daily_tasks_v1"
        const val TASKS_KEY = "tasks"
        const val REQUEST_KEY_PREFIX = "request_"
    }
}
