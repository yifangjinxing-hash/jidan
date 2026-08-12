package dev.jidan.daily.demo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DailyTaskTest {
    @Test
    fun `add trims title and places newest task first`() {
        val old = task("old", "旧事项")
        val added = DailyTaskLogic.add(listOf(old), task("new", "  买牛奶  "))

        assertEquals(listOf("new", "old"), added.map(DailyTask::id))
        assertEquals("买牛奶", added.first().title)
    }

    @Test
    fun `complete undo and clear only affect selected tasks`() {
        val first = task("first", "第一件")
        val second = task("second", "第二件")

        val completed = DailyTaskLogic.setCompleted(listOf(first, second), "first", true)
        assertTrue(completed.first().completed)
        assertFalse(completed.last().completed)
        assertEquals(1, DailyTaskLogic.remainingCount(completed))

        val undone = DailyTaskLogic.setCompleted(completed, "first", false)
        assertFalse(undone.first().completed)

        val cleared = DailyTaskLogic.clearCompleted(completed)
        assertEquals(listOf("second"), cleared.map(DailyTask::id))
    }

    @Test
    fun `codec round trips unicode and completion state`() {
        val original = listOf(
            task("one", "给妈妈打电话☎", completed = true),
            task("two", "整理\t书桌"),
        )

        assertEquals(original, DailyTaskCodec.decode(DailyTaskCodec.encode(original)))
    }

    @Test
    fun `codec ignores malformed rows without losing valid tasks`() {
        val valid = DailyTaskCodec.encode(listOf(task("one", "喝水")))
        val decoded = DailyTaskCodec.decode("$valid\n不是一条任务")

        assertEquals(listOf("喝水"), decoded.map(DailyTask::title))
    }

    @Test
    fun `automation markers bind nonce state and normalized note`() {
        val noteHash = DailyAutomationContract.sha256("买牛奶")
        val nonceHash = DailyAutomationContract.sha256("nonce-1")

        assertEquals(
            "jidan_daily_session:$nonceHash|note_ready:$noteHash",
            DailyAutomationContract.noteReadyMarker("nonce-1", "  买牛奶  "),
        )
        assertEquals(
            "jidan_daily_session:$nonceHash|saved:$noteHash",
            DailyAutomationContract.savedMarker("nonce-1", "买牛奶"),
        )
    }

    @Test
    fun `request ids make retries idempotent and reject changed payloads`() {
        val firstDigest = DailyAutomationContract.noteDigest("买牛奶")

        assertEquals(
            DailyRequestState.NEW,
            DailyAutomationContract.requestState(null, firstDigest),
        )
        assertEquals(
            DailyRequestState.DUPLICATE,
            DailyAutomationContract.requestState(firstDigest, firstDigest),
        )
        assertEquals(
            DailyRequestState.CONFLICT,
            DailyAutomationContract.requestState(
                firstDigest,
                DailyAutomationContract.noteDigest("买面包"),
            ),
        )
    }

    private fun task(
        id: String,
        title: String,
        completed: Boolean = false,
    ) = DailyTask(
        id = id,
        title = title,
        completed = completed,
        createdAtEpochMs = if (id == "old") 1L else 2L,
    )
}
