import XCTest

final class ObservableFlowsUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = [
            "-AppleLanguages", "(zh-Hans)",
            "-AppleLocale", "zh_CN"
        ]
        app.launch()

        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 8))
        XCTAssertTrue(app.textFields["jidan.command.input"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["jidan.quick.alipay"].exists)
        XCTAssertTrue(app.buttons["jidan.quick.settings"].exists)
    }

    override func tearDownWithError() throws {
        app?.terminate()
        app = nil
    }

    func testAlipayButtonShowsAuditedUnavailableState() {
        let button = app.buttons["jidan.quick.alipay"]
        XCTAssertTrue(button.waitForExistence(timeout: 5))
        XCTAssertTrue(button.isHittable)
        button.tap()

        let alert = app.alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 5))
        XCTAssertTrue(alert.staticTexts["iOS 转接头还没接上"].exists)
        XCTAssertTrue(
            alert.staticTexts[
                "当前没有经过审计的苹果端支付宝公开入口契约。鸡蛋不会猜私有链接，也没有尝试付款。"
            ].exists
        )
        XCTAssertEqual(app.state, .runningForeground)
        attachScreenshot(named: "JidanIOS-alipay-unavailable")
    }

    func testSettingsButtonOpensJidanSettingsPage() {
        let button = app.buttons["jidan.quick.settings"]
        XCTAssertTrue(button.waitForExistence(timeout: 5))
        XCTAssertTrue(button.isHittable)
        button.tap()

        XCTAssertEqual(app.state, .runningForeground)
        XCTAssertTrue(app.staticTexts["jidan.settings.title"].waitForExistence(timeout: 5))
        attachScreenshot(named: "JidanIOS-direct-settings")
        XCTAssertEqual(app.staticTexts["jidan.settings.title"].label, "鸡蛋设置")
        XCTAssertEqual(app.staticTexts["jidan.settings.protocol"].label, "JCL 0.1")
        XCTAssertEqual(app.staticTexts["jidan.settings.policy"].label, "NAVIGATION / DIRECT")
        XCTAssertTrue(app.buttons["jidan.settings.close"].isHittable)
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
