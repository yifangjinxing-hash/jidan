package dev.jidan.daily.demo

import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DailyTaskStoreCoordinatorTest {
    @Test
    fun `separate store instances merge additions against latest persisted tasks`() {
        val persistence = FakePersistence(tasks = listOf(task("old", "old")))
        val lock = Any()
        val first = DailyTaskStoreCoordinator(persistence, lock)
        val second = DailyTaskStoreCoordinator(persistence, lock)

        assertEquals(DailyTaskAddStatus.ADDED, first.add(task("one", "one"), null).status)
        assertEquals(DailyTaskAddStatus.ADDED, second.add(task("two", "two"), null).status)

        assertEquals(listOf("two", "one", "old"), first.load().map(DailyTask::id))
    }

    @Test
    fun `stale caller completion update preserves a newer addition`() {
        val persistence = FakePersistence(tasks = listOf(task("old", "old")))
        val lock = Any()
        val staleCaller = DailyTaskStoreCoordinator(persistence, lock)
        val otherCaller = DailyTaskStoreCoordinator(persistence, lock)
        staleCaller.load()

        otherCaller.add(task("new", "new"), null)
        val saved = staleCaller.setCompleted("old", completed = true)

        assertTrue(saved.saved)
        assertEquals(listOf("new", "old"), saved.tasks.map(DailyTask::id))
        assertTrue(saved.tasks.single { it.id == "old" }.completed)
    }

    @Test
    fun `concurrent retry with same request id adds exactly once`() {
        val persistence = FakePersistence()
        val lock = Any()
        val first = DailyTaskStoreCoordinator(persistence, lock)
        val second = DailyTaskStoreCoordinator(persistence, lock)

        val results = runTogether(
            { first.add(task("one", "same note"), "request-1") },
            { second.add(task("two", "same note"), "request-1") },
        )

        assertEquals(
            setOf(DailyTaskAddStatus.ADDED, DailyTaskAddStatus.DUPLICATE),
            results.map(DailyTaskAddResult::status).toSet(),
        )
        assertEquals(1, first.load().size)
        assertEquals(
            DailyAutomationContract.noteDigest("same note"),
            persistence.requestDigest("request-1"),
        )
    }

    @Test
    fun `concurrent changed payload for same request id is rejected`() {
        val persistence = FakePersistence()
        val lock = Any()
        val first = DailyTaskStoreCoordinator(persistence, lock)
        val second = DailyTaskStoreCoordinator(persistence, lock)

        val results = runTogether(
            { first.add(task("one", "first note"), "request-1") },
            { second.add(task("two", "second note"), "request-1") },
        )

        assertEquals(
            setOf(DailyTaskAddStatus.ADDED, DailyTaskAddStatus.CONFLICT),
            results.map(DailyTaskAddResult::status).toSet(),
        )
        assertEquals(1, first.load().size)
    }

    @Test
    fun `failed atomic commit does not consume request id`() {
        val persistence = FakePersistence().apply { failNextCommit = true }
        val store = DailyTaskStoreCoordinator(persistence, Any())
        val note = task("one", "retry me")

        assertEquals(DailyTaskAddStatus.SAVE_FAILED, store.add(note, "request-1").status)
        assertFalse(persistence.requestDigest("request-1") != null)
        assertEquals(DailyTaskAddStatus.ADDED, store.add(note, "request-1").status)
        assertEquals(1, store.load().size)
    }

    private fun runTogether(
        first: () -> DailyTaskAddResult,
        second: () -> DailyTaskAddResult,
    ): List<DailyTaskAddResult> {
        val ready = CountDownLatch(2)
        val start = CountDownLatch(1)
        val executor = Executors.newFixedThreadPool(2)
        return try {
            val futures = listOf(first, second).map { operation ->
                executor.submit<DailyTaskAddResult> {
                    ready.countDown()
                    check(start.await(5, TimeUnit.SECONDS))
                    operation()
                }
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS))
            start.countDown()
            futures.map { it.get(5, TimeUnit.SECONDS) }
        } finally {
            executor.shutdownNow()
        }
    }

    private fun task(id: String, title: String) = DailyTask(
        id = id,
        title = title,
        completed = false,
        createdAtEpochMs = 1L,
    )

    private class FakePersistence(
        tasks: List<DailyTask> = emptyList(),
    ) : DailyTaskPersistence {
        private var storedTasks = tasks
        private val requests = mutableMapOf<String, String>()
        var failNextCommit: Boolean = false

        override fun loadTasks(): List<DailyTask> = storedTasks

        override fun requestDigest(requestId: String): String? = requests[requestId]

        override fun commit(
            tasks: List<DailyTask>,
            requestId: String?,
            noteDigest: String?,
        ): Boolean {
            if (failNextCommit) {
                failNextCommit = false
                return false
            }
            storedTasks = tasks
            if (requestId != null && noteDigest != null) requests[requestId] = noteDigest
            return true
        }
    }
}
