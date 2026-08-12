package dev.jidan.daily.demo

import android.content.Context
import android.content.SharedPreferences

internal class DailyTaskStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val coordinator = DailyTaskStoreCoordinator(
        persistence = SharedPreferencesPersistence(preferences),
        mutationLock = STORE_MUTATION_LOCK,
    )

    fun load(): List<DailyTask> = coordinator.load()

    fun add(task: DailyTask, requestId: String?): DailyTaskAddResult =
        coordinator.add(task, requestId)

    fun setCompleted(taskId: String, completed: Boolean): DailyTaskSaveResult =
        coordinator.setCompleted(taskId, completed)

    fun clearCompleted(): DailyTaskSaveResult = coordinator.clearCompleted()

    private class SharedPreferencesPersistence(
        private val preferences: SharedPreferences,
    ) : DailyTaskPersistence {
        override fun loadTasks(): List<DailyTask> =
            DailyTaskCodec.decode(preferences.getString(TASKS_KEY, null))

        override fun requestDigest(requestId: String): String? =
            preferences.getString(requestKey(requestId), null)

        /** Synchronous so a saved marker is never exposed before the note reaches disk. */
        override fun commit(
            tasks: List<DailyTask>,
            requestId: String?,
            noteDigest: String?,
        ): Boolean {
            val editor = preferences.edit().putString(TASKS_KEY, DailyTaskCodec.encode(tasks))
            if (requestId != null && noteDigest != null) {
                editor.putString(requestKey(requestId), noteDigest)
            }
            return editor.commit()
        }

        private fun requestKey(requestId: String): String =
            "$REQUEST_KEY_PREFIX${DailyAutomationContract.sha256(requestId)}"
    }

    private companion object {
        const val PREFERENCES_NAME = "daily_tasks_v1"
        const val TASKS_KEY = "tasks"
        const val REQUEST_KEY_PREFIX = "request_"
        val STORE_MUTATION_LOCK = Any()
    }
}
