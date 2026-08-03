package dev.jidan.shell

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalCommandParserTest {
    @Test
    fun exactAlipayCommandProducesEmptyInputContract() {
        val result = LocalCommandParser.parse("  打开 支付宝。 ")

        assertTrue(result is ParseResult.Proposal)
        val proposal = (result as ParseResult.Proposal).value
        assertEquals(ShellAction.OPEN_ALIPAY, proposal.action)
        assertEquals(
            "{\"action\":\"app.open.alipay_frontdoor\",\"arguments\":{}," +
                "\"riskLevel\":\"NAVIGATION\",\"executionMode\":\"DIRECT\"," +
                "\"requiresConfirmation\":false}",
            proposal.canonicalContract,
        )
        assertEquals(ShellRiskLevel.NAVIGATION, proposal.riskLevel)
        assertEquals(ShellExecutionMode.DIRECT, proposal.executionMode)
        assertEquals(false, proposal.requiresConfirmation)
        assertEquals(64, proposal.digest.length)
    }

    @Test
    fun paymentScanAmountAndUriVariantsFailBeforeExactActionMatching() {
        val unsafe = listOf(
            "打开支付宝扫一扫",
            "打开支付宝给小明转账",
            "支付宝付10元",
            "打开支付宝二维码",
            "打开 alipays://platformapi/startapp",
            "打开支付宝输入验证码",
        )

        unsafe.forEach { command ->
            assertTrue(command, LocalCommandParser.parse(command) is ParseResult.Rejected)
        }
    }

    @Test
    fun unknownTextNeverFallsThroughToAlipay() {
        assertTrue(LocalCommandParser.parse("打开支付宝看看账单") is ParseResult.Unknown)
        assertTrue(LocalCommandParser.parse("今天天气怎么样") is ParseResult.Unknown)
    }

    @Test
    fun settingsIsASeparateStableAction() {
        val result = LocalCommandParser.parse("打开系统设置！")

        assertTrue(result is ParseResult.Proposal)
        val proposal = (result as ParseResult.Proposal).value
        assertEquals(ShellAction.OPEN_SYSTEM_SETTINGS, proposal.action)
        assertNotEquals(
            ActionProposal(
                ShellAction.OPEN_ALIPAY,
                "打开支付宝",
                "安全提示",
                "打开",
            ).digest,
            proposal.digest,
        )
    }

    @Test
    fun blankInputDoesNothing() {
        assertTrue(LocalCommandParser.parse("  ") is ParseResult.Unknown)
    }
}
