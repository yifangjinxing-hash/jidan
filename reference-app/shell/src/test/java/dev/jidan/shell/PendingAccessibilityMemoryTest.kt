package dev.jidan.shell

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PendingAccessibilityMemoryTest {
    @After
    fun tearDown() {
        PendingAccessibilityMemory.clear()
        PendingAccessibilityMemory.resetClockForTest()
    }

    @Test
    fun dailyTextCanBeRecoveredOnlyFromTheCurrentProcessMemory() {
        val requestId = "8a28a36f-52d4-43cd-a19a-b37f5822147e"
        val proposal = LocalCommandParser.dailyNoteProposal("配置切换后继续", requestId)
        PendingAccessibilityMemory.remember(proposal)

        assertEquals(
            "配置切换后继续",
            (PendingAccessibilityMemory.findDaily(requestId)?.arguments as ActionArguments.DailyNote).text,
        )

        PendingAccessibilityMemory.clearIf(proposal)
        assertNull(PendingAccessibilityMemory.findDaily(requestId))
    }

    @Test
    fun aDifferentRequestCannotReadThePendingText() {
        PendingAccessibilityMemory.remember(
            LocalCommandParser.dailyNoteProposal(
                "不会串线",
                "de3ada5d-62b6-4808-a528-13900dc931da",
            ),
        )

        assertNull(PendingAccessibilityMemory.findDaily("b38da1fb-d13d-4457-a31d-a37a877ff497"))
    }

    @Test
    fun authorizationReturnCannotDispatchAnExpiredPendingSentence() {
        var now = 10_000L
        PendingAccessibilityMemory.elapsedMs = { now }
        val proposal = LocalCommandParser.dailyNoteProposal(
            "超时后不能偷偷执行",
            "d9c01da2-3517-49ae-8ee4-c36c213ee40f",
        )
        PendingAccessibilityMemory.remember(proposal)

        now += 60_001L

        assertNull(PendingAccessibilityMemory.takeIfCurrent(proposal))
        assertNull(PendingAccessibilityMemory.findDaily("d9c01da2-3517-49ae-8ee4-c36c213ee40f"))
    }
}
