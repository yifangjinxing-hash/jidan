import UIKit

enum DispatchOutcome: Equatable {
    case dispatched(title: String, message: String)
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
            guard let url = URL(string: UIApplication.openSettingsURLString) else {
                return .blocked(title: "没有打开", message: "iOS 没有提供可用的鸡蛋设置入口。")
            }
            let opened = await UIApplication.shared.open(url)
            return opened
                ? .dispatched(
                    title: "已经交给 iOS",
                    message: "iOS 已接收打开鸡蛋设置的请求；鸡蛋没有修改任何开关。"
                )
                : .blocked(title: "没有打开", message: "iOS 拒绝了设置入口，鸡蛋没有自动重试。")

        case .alipayFrontDoor:
            return .targetUnavailable(
                title: "iOS 转接头还没接上",
                message: "当前没有经过审计的苹果端支付宝公开入口契约。鸡蛋不会猜私有链接，也没有尝试付款。"
            )
        }
    }
}

