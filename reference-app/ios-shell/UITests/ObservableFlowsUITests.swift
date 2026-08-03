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
        XCTAssertTrue(app.staticTexts["jidan.status.title"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["jidan.status.title"].label, "想做什么？")
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

        let title = app.staticTexts["jidan.status.title"]
        XCTAssertTrue(waitForLabel("iOS 转接头还没接上", on: title, timeout: 5))
        XCTAssertEqual(
            app.staticTexts["jidan.status.subtitle"].label,
            "当前没有经过审计的苹果端支付宝公开入口契约。鸡蛋不会猜私有链接，也没有尝试付款。"
        )
        XCTAssertEqual(app.state, .runningForeground)
        attachScreenshot(named: "JidanIOS-alipay-unavailable")
    }

    func testSettingsButtonOpensJidanSettingsPage() {
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        let button = app.buttons["jidan.quick.settings"]
        XCTAssertTrue(button.waitForExistence(timeout: 5))
        XCTAssertTrue(button.isHittable)
        button.tap()

        XCTAssertTrue(
            settings.wait(for: .runningForeground, timeout: 8),
            "点击后，苹果设置没有进入前台"
        )

        let protocolValue = settings.staticTexts["JCL 0.1"]
        let policyValue = settings.staticTexts["NAVIGATION / DIRECT"]
        if !protocolValue.waitForExistence(timeout: 3) || !policyValue.exists {
            settings.swipeUp()
        }
        XCTAssertTrue(protocolValue.waitForExistence(timeout: 5))
        XCTAssertTrue(policyValue.waitForExistence(timeout: 5))
        attachScreenshot(named: "JidanIOS-direct-settings")
    }

    private func waitForLabel(_ expected: String, on element: XCUIElement, timeout: TimeInterval) -> Bool {
        let predicate = NSPredicate(format: "label == %@", expected)
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
