import XCTest
@testable import JidanIOS

final class CommandPolicyTests: XCTestCase {
    func testSettingsNavigationIsDirectWithoutSecondConfirmation() {
        guard case let .direct(proposal) = CommandPolicy.parse("  打开 系统设置。 ") else {
            return XCTFail("expected direct navigation")
        }

        XCTAssertEqual(proposal.target, .jidanSettings)
        XCTAssertEqual(proposal.riskLevel, .navigation)
        XCTAssertEqual(proposal.executionMode, .direct)
        XCTAssertFalse(proposal.requiresConfirmation)
        XCTAssertEqual(proposal.compactContract, "app.open.jidan_settings · NAVIGATION / DIRECT")
    }

    func testAlipayFrontDoorRequestIsNarrowAndDirect() {
        guard case let .direct(proposal) = CommandPolicy.parse("打开支付宝") else {
            return XCTFail("expected direct navigation proposal")
        }

        XCTAssertEqual(proposal.target, .alipayFrontDoor)
        XCTAssertFalse(proposal.requiresConfirmation)
    }

    func testMoneyAndCredentialLanguageNeverFallsThroughToNavigation() {
        [
            "打开支付宝给小明转账 10 元",
            "支付宝付款",
            "打开支付宝扫一扫",
            "打开支付宝输入验证码",
            "打开 https://example.com/pay"
        ].forEach { command in
            guard case .rejected = CommandPolicy.parse(command) else {
                return XCTFail("expected rejection for: \(command)")
            }
        }
    }

    func testUnknownTextDoesNothing() {
        guard case .unsupported = CommandPolicy.parse("帮我看看天气") else {
            return XCTFail("unknown text must not dispatch")
        }
    }
}
