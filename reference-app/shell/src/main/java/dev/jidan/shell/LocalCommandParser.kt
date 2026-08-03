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
        val compact = Normalizer.normalize(raw, Normalizer.Form.NFKC)
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
            "现在我只会安全地打开支付宝或系统设置。其他事情没有执行。",
        )
    }
}
