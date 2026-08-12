package dev.jidan.daily.demo

internal enum class DailyTaskAddStatus {
    ADDED,
    DUPLICATE,
    CONFLICT,
    SAVE_FAILED,
}

internal data class DailyTaskAddResult(
    val status: DailyTaskAddStatus,
    val tasks: List<DailyTask>,
    val noteDigest: String,
)

internal data class DailyTaskSaveResult(
    val saved: Boolean,
    val tasks: List<DailyTask>,
    val changedCount: Int,
)

/** Small persistence boundary so every store instance can share one serialized mutation path. */
internal interface DailyTaskPersistence {
    fun loadTasks(): List<DailyTask>

    fun requestDigest(requestId: String): String?

    fun commit(
        tasks: List<DailyTask>,
        requestId: String? = null,
        noteDigest: String? = null,
    ): Boolean
}

internal class DailyTaskStoreCoordinator(
    private val persistence: DailyTaskPersistence,
    private val mutationLock: Any,
) {
    fun load(): List<DailyTask> = synchronized(mutationLock) {
        persistence.loadTasks()
    }

    fun add(task: DailyTask, requestId: String?): DailyTaskAddResult =
        synchronized(mutationLock) {
            val latest = persistence.loadTasks()
            val normalizedRequestId = requestId?.trim()?.takeIf(String::isNotBlank)
            val noteDigest = DailyAutomationContract.noteDigest(task.title)
            val requestState = normalizedRequestId
                ?.let(persistence::requestDigest)
                ?.let { previous -> DailyAutomationContract.requestState(previous, noteDigest) }
                ?: DailyRequestState.NEW

            when (requestState) {
                DailyRequestState.DUPLICATE -> DailyTaskAddResult(
                    status = DailyTaskAddStatus.DUPLICATE,
                    tasks = latest,
                    noteDigest = noteDigest,
                )

                DailyRequestState.CONFLICT -> DailyTaskAddResult(
                    status = DailyTaskAddStatus.CONFLICT,
                    tasks = latest,
                    noteDigest = noteDigest,
                )

                DailyRequestState.NEW -> {
                    val merged = DailyTaskLogic.add(latest, task)
                    val saved = persistence.commit(merged, normalizedRequestId, noteDigest)
                    DailyTaskAddResult(
                        status = if (saved) {
                            DailyTaskAddStatus.ADDED
                        } else {
                            DailyTaskAddStatus.SAVE_FAILED
                        },
                        tasks = if (saved) merged else latest,
                        noteDigest = noteDigest,
                    )
                }
            }
        }

    fun setCompleted(taskId: String, completed: Boolean): DailyTaskSaveResult =
        saveLatest { latest ->
            val updated = DailyTaskLogic.setCompleted(latest, taskId, completed)
            updated to if (updated == latest) 0 else 1
        }

    fun clearCompleted(): DailyTaskSaveResult = saveLatest { latest ->
        val updated = DailyTaskLogic.clearCompleted(latest)
        updated to (latest.size - updated.size)
    }

    private fun saveLatest(
        transform: (List<DailyTask>) -> Pair<List<DailyTask>, Int>,
    ): DailyTaskSaveResult = synchronized(mutationLock) {
        val latest = persistence.loadTasks()
        val (updated, changedCount) = transform(latest)
        if (updated == latest) {
            return@synchronized DailyTaskSaveResult(
                saved = true,
                tasks = latest,
                changedCount = 0,
            )
        }
        val saved = persistence.commit(updated)
        DailyTaskSaveResult(
            saved = saved,
            tasks = if (saved) updated else latest,
            changedCount = if (saved) changedCount else 0,
        )
    }
}
