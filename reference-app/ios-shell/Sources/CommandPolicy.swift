import Foundation

enum JCLRiskLevel: String, Equatable {
    case navigation = "NAVIGATION"
}

enum JCLExecutionMode: String, Equatable {
    case direct = "DIRECT"
}

enum NavigationTarget: String, Equatable {
    case jidanSettings
    case alipayFrontDoor
}

struct ActionProposal: Equatable {
    let capabilityID: String
    let target: NavigationTarget
    let title: String
    let riskLevel: JCLRiskLevel
    let executionMode: JCLExecutionMode
    let requiresConfirmation: Bool

    var compactContract: String {
        "\(capabilityID) · \(riskLevel.rawValue) / \(executionMode.rawValue)"
    }
}

enum CommandDecision: Equatable {
    case direct(ActionProposal)
    case rejected(title: String, message: String)
    case unsupported(message: String)
}

enum CommandPolicy {
    private static let riskyTokens = [
        "给", "转账", "转帐", "付款", "付钱", "代付", "收款", "扫一扫", "扫码",
        "二维码", "红包", "充值", "提现", "余额", "订单", "密码", "验证码",
        "人脸", "指纹", "链接"
    ]

    static func parse(_ raw: String) -> CommandDecision {
        let compact = normalize(raw)
        guard !compact.isEmpty else {
            return .unsupported(message: "先说一句，或写一句。")
        }

        if ["打开支付宝", "启动支付宝", "支付宝"].contains(compact) {
            return .direct(
                ActionProposal(
                    capabilityID: "app.open.alipay_frontdoor",
                    target: .alipayFrontDoor,
                    title: "打开支付宝",
                    riskLevel: .navigation,
                    executionMode: .direct,
                    requiresConfirmation: false
                )
            )
        }

        if ["打开系统设置", "打开设置", "系统设置", "打开鸡蛋设置", "鸡蛋设置"].contains(compact) {
            return .direct(
                ActionProposal(
                    capabilityID: "app.open.jidan_settings",
                    target: .jidanSettings,
                    title: "打开鸡蛋设置",
                    riskLevel: .navigation,
                    executionMode: .direct,
                    requiresConfirmation: false
                )
            )
        }

        let providerless = compact.replacingOccurrences(of: "支付宝", with: "")
        if containsMatch(#"(?:[0-9一二两三四五六七八九十百千万]+)(?:\.[0-9]+)?(?:元|块|¥|￥)"#, in: providerless)
            || containsMatch(#"(?i)(?:https?://|[a-z][a-z0-9+.-]*://|intent:)"#, in: compact)
            || riskyTokens.contains(where: providerless.contains) {
            return .rejected(
                title: "这一步先停下",
                message: "这句话可能涉及付款、收款人、扫码或敏感信息。鸡蛋没有执行，什么也没改变。"
            )
        }

        return .unsupported(message: "现在我只会安全地打开鸡蛋设置，或请求经过审计的应用入口。其他事情没有执行。")
    }

    private static func normalize(_ raw: String) -> String {
        let compatible = raw.precomposedStringWithCompatibilityMapping
        let noWhitespace = compatible.components(separatedBy: .whitespacesAndNewlines).joined()
        return noWhitespace.trimmingCharacters(in: CharacterSet(charactersIn: "。！!？？?，,"))
    }

    private static func containsMatch(_ pattern: String, in value: String) -> Bool {
        value.range(of: pattern, options: .regularExpression) != nil
    }
}

