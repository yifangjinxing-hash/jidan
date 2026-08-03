package dev.jidan.shell

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CommandDispatchPolicyTest {
    @Test
    fun openingAlipayAndSettingsAreDirectNavigation() {
        val commands = listOf(
            "打开支付宝" to ShellAction.OPEN_ALIPAY,
            "启动支付宝" to ShellAction.OPEN_ALIPAY,
            "支付宝" to ShellAction.OPEN_ALIPAY,
            "打开系统设置" to ShellAction.OPEN_SYSTEM_SETTINGS,
            "打开设置" to ShellAction.OPEN_SYSTEM_SETTINGS,
            "系统设置" to ShellAction.OPEN_SYSTEM_SETTINGS,
        )

        commands.forEach { (command, expectedAction) ->
            val directive = CommandDispatchPolicy.classify(LocalCommandParser.parse(command))

            assertTrue(command, directive is DispatchDirective.DirectNavigation)
            assertEquals(
                expectedAction,
                (directive as DispatchDirective.DirectNavigation).proposal.action,
            )
        }
    }

    @Test
    fun paymentTransferScanAndCredentialCommandsNeverDispatch() {
        val dangerousCommands = listOf(
            "打开支付宝给小明转账 10 元",
            "打开支付宝付款",
            "打开支付宝扫一扫",
            "打开支付宝收款码",
            "打开支付宝红包",
            "打开支付宝充值",
            "打开支付宝提现",
            "打开支付宝订单",
            "打开支付宝输入密码",
            "打开支付宝输入验证码",
            "打开支付宝做指纹验证",
            "打开支付宝做人脸验证",
            "打开 alipays://platformapi/startapp?appId=20000056",
        )

        dangerousCommands.forEach { command ->
            val parsed = LocalCommandParser.parse(command)
            val directive = CommandDispatchPolicy.classify(parsed)

            assertTrue(command, parsed is ParseResult.Rejected)
            assertTrue(command, directive is DispatchDirective.DoNotDispatch)
        }
    }

    @Test
    fun unknownAndBlankCommandsAlsoNeverDispatch() {
        listOf("打开支付宝看看账单", "今天天气怎么样", "  ").forEach { command ->
            val directive = CommandDispatchPolicy.classify(LocalCommandParser.parse(command))

            assertTrue(command, directive is DispatchDirective.DoNotDispatch)
        }
    }
}
