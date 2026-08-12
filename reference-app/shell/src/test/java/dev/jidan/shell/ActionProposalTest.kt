package dev.jidan.shell

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ActionProposalTest {
    @Test
    fun dailyArgumentsAreCanonicalAndJsonEscaped() {
        val proposal = dailyProposal("明天买\"鸡蛋\"\\牛奶\n第二行")

        assertEquals(
            "{\"action\":\"daily.note.create\",\"arguments\":" +
                "{\"requestId\":\"11111111-1111-4111-8111-111111111111\"," +
                "\"text\":\"明天买\\\"鸡蛋\\\"\\\\牛奶\\n第二行\"}," +
                "\"riskLevel\":\"OWNED_APP_WRITE\"," +
                "\"executionMode\":\"OWNED_APP\"," +
                "\"requiresConfirmation\":false}",
            proposal.canonicalContract,
        )
        assertFalse(proposal.canonicalContract.contains('\n'))
        assertEquals(64, proposal.digest.length)
    }

    @Test
    fun payloadChangesTheContractDigest() {
        assertNotEquals(dailyProposal("买鸡蛋").digest, dailyProposal("买牛奶").digest)
        assertTrue(dailyProposal("买鸡蛋").canonicalContract.contains("买鸡蛋"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun dailyPayloadCannotBeAttachedToAnotherAction() {
        ActionProposal(
            action = ShellAction.OPEN_MOBILEANJIAN,
            title = "candidate",
            safetyMessage = "handoff",
            actionLabel = "open",
            arguments = ActionArguments.DailyNote(
                requestId = "11111111-1111-4111-8111-111111111111",
                text = "明天买鸡蛋",
            ),
        )
    }

    private fun dailyProposal(text: String) = ActionProposal(
        action = ShellAction.CREATE_DAILY_NOTE,
        title = "daily",
        safetyMessage = "daily",
        actionLabel = "daily",
        riskLevel = ShellRiskLevel.OWNED_APP_WRITE,
        executionMode = ShellExecutionMode.OWNED_APP,
        arguments = ActionArguments.DailyNote(
            requestId = "11111111-1111-4111-8111-111111111111",
            text = text,
        ),
    )
}
