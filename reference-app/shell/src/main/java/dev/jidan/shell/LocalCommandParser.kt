package dev.jidan.shell

import java.text.Normalizer

object LocalCommandParser {
    private val amountPattern = Regex("(?:[0-9０-９]+|[一二两三四五六七八九十百千万]+)(?:\\.\\d+)?(?:元|块|圆)")
    private val uriPattern = Regex("(?i)(?:https?://|[a-z][a-z0-9+.-]*://|intent:)")
    private val riskyTokens = listOf(
        "给",
        "转账",
        "转帐",
        "付款",
        "付钱",
        "代付",
        "收款",
        "扫一扫",
        "扫码",
        "二维码",
        "红包",
        "充值",
        "提现",
        "余额",
        "订单",
        "密码",
        "验证码",
        "人脸",
        "指纹",
        "链接",
    )

    fun parse(raw: String): ParseResult {
        val normalized = Normalizer.normalize(raw, Normalizer.Form.NFKC).trim()
        if (normalized.startsWith("记下")) {
            val note = normalized.removePrefix("记下").trim()
            if (note.isBlank()) return ParseResult.Rejected("要记下的内容还是空的，鸡蛋没有保存。")
            if (note.length > 200) return ParseResult.Rejected("这条内容超过 200 个字，鸡蛋没有截断或保存。")
            return ParseResult.Proposal(
                ActionProposal(
                    action = ShellAction.CREATE_DAILY_NOTE,
                    title = "记一条待办",
                    safetyMessage = "将打开鸡蛋自带的日常小事 App，填入这句话并保存。",
                    actionLabel = "记下",
                    riskLevel = ShellRiskLevel.OWNED_APP_WRITE,
                    executionMode = ShellExecutionMode.OWNED_APP,
                    arguments = ActionArguments.dailyNote(note),
                ),
            )
        }

        val compact = normalized
            .trim()
            .trimEnd('。', '！', '!', '？', '?')
            .replace(Regex("\\s+"), "")

        if (compact.isBlank()) {
            return ParseResult.Unknown("先说一句，或写一句。")
        }

        if (compact in setOf("打开支付宝", "启动支付宝", "支付宝")) {
            return ParseResult.Proposal(
                ActionProposal(
                    action = ShellAction.OPEN_ALIPAY,
                    title = "打开支付宝",
                    safetyMessage = (
                        "将请安卓打开这台手机里的支付宝，并离开鸡蛋。\n" +
                            "鸡蛋不会填写收款人、金额或密码，也不知道你是否付款。"
                        ),
                    actionLabel = "打开支付宝",
                ),
            )
        }

        if (compact in setOf("打开按键精灵", "启动按键精灵", "按键精灵")) {
            return ParseResult.Proposal(
                ActionProposal(
                    action = ShellAction.OPEN_MOBILEANJIAN,
                    title = "打开候选手",
                    safetyMessage = (
                        "只打开已审计版本的按键精灵首页。鸡蛋不会调用它的私有服务、端口或脚本。"
                        ),
                    actionLabel = "打开按键精灵",
                ),
            )
        }

        if (compact in setOf("打开系统设置", "打开设置", "系统设置")) {
            return ParseResult.Proposal(
                ActionProposal(
                    action = ShellAction.OPEN_SYSTEM_SETTINGS,
                    title = "打开系统设置",
                    safetyMessage = "将打开安卓系统设置。鸡蛋不会替你修改任何开关。",
                    actionLabel = "打开设置",
                ),
            )
        }

        if (compact in setOf(
                "开始手脑实验",
                "打开手脑实验",
                "实验支付",
                "测试支付密码验证码",
            )
        ) {
            return ParseResult.Proposal(
                ActionProposal(
                    action = ShellAction.OPEN_AUTOMATION_LAB,
                    title = "手 + 脑实验",
                    safetyMessage = "将在鸡蛋自带的无网络假页面中填写虚构金额、假密码和假验证码。",
                    actionLabel = "开始实验",
                    riskLevel = ShellRiskLevel.SENSITIVE_EXPERIMENT,
                    executionMode = ShellExecutionMode.SANDBOX,
                ),
            )
        }

        val withoutProviderName = compact.replace("支付宝", "")
        val risky = amountPattern.containsMatchIn(withoutProviderName) ||
            uriPattern.containsMatchIn(compact) ||
            riskyTokens.any { token -> withoutProviderName.contains(token) }
        if (risky) {
            return ParseResult.Rejected(
                "这句话可能涉及付款、收款人、扫码或敏感信息。鸡蛋没有执行，什么也没改变。",
            )
        }

        return ParseResult.Unknown(
            "现在我会记一条日常待办、打开支付宝、按键精灵、系统设置，或运行隔离实验。其他事情没有执行。",
        )
    }
}
