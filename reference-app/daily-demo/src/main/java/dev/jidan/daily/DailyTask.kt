package dev.jidan.daily.demo

data class DailyTask(
    val id: String,
    val title: String,
    val completed: Boolean,
    val createdAtEpochMs: Long,
)

object DailyTaskLogic {
    fun add(tasks: List<DailyTask>, task: DailyTask): List<DailyTask> {
        val normalized = task.copy(title = task.title.trim())
        require(normalized.id.isNotBlank()) { "Task id must not be blank" }
        require(normalized.title.isNotBlank()) { "Task title must not be blank" }
        require(tasks.none { it.id == normalized.id }) { "Task id must be unique" }
        return listOf(normalized) + tasks
    }

    fun setCompleted(
        tasks: List<DailyTask>,
        taskId: String,
        completed: Boolean,
    ): List<DailyTask> = tasks.map { task ->
        if (task.id == taskId) task.copy(completed = completed) else task
    }

    fun clearCompleted(tasks: List<DailyTask>): List<DailyTask> =
        tasks.filterNot(DailyTask::completed)

    fun remainingCount(tasks: List<DailyTask>): Int = tasks.count { !it.completed }
}
