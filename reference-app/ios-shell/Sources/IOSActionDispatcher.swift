enum DispatchOutcome: Equatable {
    case presentJidanSettings
    case targetUnavailable(title: String, message: String)
    case blocked(title: String, message: String)
}

@MainActor
struct IOSActionDispatcher {
    func dispatch(_ proposal: ActionProposal) async -> DispatchOutcome {
        guard proposal.riskLevel == .navigation,
              proposal.executionMode == .direct,
              !proposal.requiresConfirmation else {
            return .blocked(
                title: "契约不安全",
                message: "这不是可直接执行的低风险导航，鸡蛋已经停下。"
            )
        }

        switch proposal.target {
        case .jidanSettings:
            return .presentJidanSettings

        case .alipayFrontDoor:
            return .targetUnavailable(
                title: "iOS 转接头还没接上",
                message: "当前没有经过审计的苹果端支付宝公开入口契约。鸡蛋不会猜私有链接，也没有尝试付款。"
            )
        }
    }
}
