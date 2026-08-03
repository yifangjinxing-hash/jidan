import SwiftUI

private enum OrbMode: Equatable {
    case idle
    case listening
    case thinking
    case success
    case failure

    var accent: Color {
        switch self {
        case .idle: return Color(red: 0.72, green: 0.62, blue: 0.95)
        case .listening: return Color(red: 0.35, green: 0.90, blue: 0.79)
        case .thinking: return Color(red: 0.98, green: 0.76, blue: 0.35)
        case .success: return Color(red: 0.45, green: 0.90, blue: 0.68)
        case .failure: return Color(red: 1.00, green: 0.46, blue: 0.57)
        }
    }
}

struct ContentView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var speech = SpeechRecognizer()
    @State private var input = ""
    @State private var statusTitle = "想做什么？"
    @State private var statusSubtitle = "说一句，或写一句。安全的打开动作会直接执行。"
    @State private var orbMode: OrbMode = .idle
    @State private var didRunDemo = false
    @State private var isSettingsPresented = false
    @AppStorage("receiptSequence") private var receiptSequence = 1

    var body: some View {
        ZStack {
            CosmicBackground()

            VStack(spacing: 0) {
                topBar
                Spacer(minLength: 18)
                JidanOrb(mode: orbMode)
                    .frame(width: 232, height: 232)
                    .accessibilityLabel("鸡蛋状态：\(statusTitle)")
                statusArea
                Spacer(minLength: 22)
                commandBar
                quickActions
                Text("只有你点麦克风时，我才会听。涉及钱和密码，我会停下。")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.55))
                    .multilineTextAlignment(.center)
                    .padding(.top, 10)
                footer
                    .padding(.top, 12)
            }
            .padding(.horizontal, 22)
            .padding(.top, 8)
            .padding(.bottom, 10)
        }
        .task {
            guard !didRunDemo else { return }
            let arguments = ProcessInfo.processInfo.arguments
            let demoMode = ProcessInfo.processInfo.environment["JIDAN_DEMO"]
            let demoCommand: String?
            if demoMode == "settings" || arguments.contains("--jidan-demo-settings") {
                demoCommand = "打开鸡蛋设置"
            } else if demoMode == "alipay" || arguments.contains("--jidan-demo-alipay") {
                demoCommand = "打开支付宝"
            } else {
                demoCommand = nil
            }
            guard let demoCommand else { return }
            didRunDemo = true
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            input = demoCommand
            submit(input)
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase != .active, speech.isListening else { return }
            speech.stop()
            orbMode = .idle
            statusTitle = "已经停止听写"
            statusSubtitle = "鸡蛋进入后台后不会继续听。"
        }
        .fullScreenCover(isPresented: $isSettingsPresented) {
            JidanSettingsView()
                .preferredColorScheme(.dark)
        }
    }

    private var topBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("Jidan")
                    .font(.system(size: 27, weight: .bold, design: .rounded))
                Text("iOS 可观察原型 · 0.1")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.62))
            }
            Spacer()
            Button {
                submit("打开鸡蛋设置")
            } label: {
                Image(systemName: "gearshape.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .frame(width: 46, height: 46)
                    .background(.white.opacity(0.09), in: Circle())
                    .overlay(Circle().stroke(.white.opacity(0.22), lineWidth: 1))
            }
            .accessibilityLabel("打开鸡蛋设置")
            .accessibilityIdentifier("jidan.quick.settings.top")
        }
        .foregroundStyle(.white)
    }

    private var statusArea: some View {
        VStack(spacing: 5) {
            Text(statusTitle)
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .lineLimit(1)
                .accessibilityIdentifier("jidan.status.title")
            Text(statusSubtitle)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.72))
                .multilineTextAlignment(.center)
                .lineLimit(3)
                .frame(minHeight: 42)
                .accessibilityIdentifier("jidan.status.subtitle")
        }
        .padding(.top, 7)
        .animation(.easeOut(duration: 0.2), value: statusTitle)
    }

    private var commandBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "sparkle.magnifyingglass")
                .foregroundStyle(.white.opacity(0.58))
                .padding(.leading, 4)
            TextField("告诉鸡蛋你想做什么", text: $input, axis: .vertical)
                .textInputAutocapitalization(.never)
                .submitLabel(.go)
                .lineLimit(1...2)
                .onSubmit { submit(input) }
            Button(action: toggleSpeech) {
                Image(systemName: speech.isListening ? "stop.fill" : "mic.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .frame(width: 46, height: 46)
                    .background(
                        speech.isListening ? OrbMode.listening.accent.opacity(0.24) : Color.white.opacity(0.07),
                        in: Circle()
                    )
            }
            .accessibilityLabel(speech.isListening ? "停止听写" : "开始语音转文字")

            Button { submit(input) } label: {
                Image(systemName: "arrow.up")
                    .font(.system(size: 18, weight: .bold))
                    .frame(width: 46, height: 46)
                    .background(Color(red: 0.71, green: 0.64, blue: 0.93).opacity(0.25), in: Circle())
            }
            .accessibilityLabel("执行")
        }
        .foregroundStyle(.white)
        .padding(7)
        .background(Color(red: 0.06, green: 0.05, blue: 0.14).opacity(0.76), in: Capsule())
        .overlay(Capsule().stroke(.white.opacity(0.56), lineWidth: 1.2))
    }

    private var quickActions: some View {
        HStack(spacing: 9) {
            quickButton("打开支付宝", icon: "arrow.up.forward.app", identifier: "jidan.quick.alipay")
            quickButton("打开鸡蛋设置", icon: "gearshape", identifier: "jidan.quick.settings")
        }
        .padding(.top, 10)
    }

    private func quickButton(_ command: String, icon: String, identifier: String) -> some View {
        Button {
            input = command
            submit(command)
        } label: {
            Label(command, systemImage: icon)
                .font(.caption.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 38)
                .background(.white.opacity(0.075), in: Capsule())
                .overlay(Capsule().stroke(.white.opacity(0.18), lineWidth: 1))
        }
        .foregroundStyle(.white.opacity(0.88))
        .accessibilityIdentifier(identifier)
    }

    private var footer: some View {
        HStack {
            Label("本机", systemImage: "circle.dotted")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color(red: 0.55, green: 0.92, blue: 0.82))
                .padding(.horizontal, 13)
                .frame(height: 36)
                .background(Color(red: 0.03, green: 0.18, blue: 0.17).opacity(0.42), in: Capsule())
                .overlay(Capsule().stroke(Color(red: 0.31, green: 0.74, blue: 0.65).opacity(0.65), lineWidth: 1))
            Spacer()
            Text(String(format: "回执 %04d", receiptSequence))
                .font(.caption.monospacedDigit())
                .foregroundStyle(.white.opacity(0.48))
            Spacer()
            Image(systemName: "questionmark")
                .font(.caption.bold())
                .frame(width: 36, height: 36)
                .background(.white.opacity(0.07), in: Circle())
                .overlay(Circle().stroke(.white.opacity(0.18), lineWidth: 1))
                .foregroundStyle(.white.opacity(0.8))
                .accessibilityLabel("帮助")
        }
    }

    @MainActor
    private func submit(_ raw: String) {
        if speech.isListening { speech.stop() }
        input = raw
        switch CommandPolicy.parse(raw) {
        case let .direct(proposal):
            orbMode = .thinking
            statusTitle = "正在交给 iOS"
            statusSubtitle = proposal.compactContract
            Task { @MainActor in
                let outcome = await IOSActionDispatcher().dispatch(proposal)
                apply(outcome)
            }

        case let .rejected(title, message):
            orbMode = .failure
            statusTitle = title
            statusSubtitle = message
            appendReceipt()

        case let .unsupported(message):
            orbMode = .failure
            statusTitle = "这件事还不会"
            statusSubtitle = message
        }
    }

    @MainActor
    private func apply(_ outcome: DispatchOutcome) {
        switch outcome {
        case .presentJidanSettings:
            orbMode = .success
            statusTitle = "鸡蛋设置已经打开"
            statusSubtitle = "这是动作结果，不是第二遍确认。"
            isSettingsPresented = true
            ObservableEvidence.record("settings_dispatched")
        case let .targetUnavailable(title, message):
            orbMode = .failure
            statusTitle = title
            statusSubtitle = message
            ObservableEvidence.record("alipay_target_unavailable")
        case let .blocked(title, message):
            orbMode = .failure
            statusTitle = title
            statusSubtitle = message
            ObservableEvidence.record("blocked")
        }
        appendReceipt()
    }

    @MainActor
    private func toggleSpeech() {
        if speech.isListening {
            speech.stop()
            orbMode = .idle
            statusTitle = "已经停止听写"
            statusSubtitle = "你可以修改文字，再点箭头执行。"
            return
        }

        speech.start(
            onPreparing: {
                orbMode = .thinking
                statusTitle = "准备麦克风"
                statusSubtitle = "第一次使用时，iOS 会询问麦克风和语音识别权限。"
            },
            onStarted: {
                orbMode = .listening
                statusTitle = "我在听"
                statusSubtitle = "说完后，文字会出现在输入框里并直接判断。"
            },
            onPartial: { text in
                input = text
            },
            onFinal: { text in
                input = text
                submit(text)
            },
            onFailure: { message in
                orbMode = .failure
                statusTitle = "语音暂不可用"
                statusSubtitle = message
            }
        )
    }

    private func appendReceipt() {
        receiptSequence = receiptSequence >= 9_999 ? 1 : receiptSequence + 1
    }
}

private struct JidanSettingsView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            CosmicBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(alignment: .center) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("鸡蛋设置")
                                .font(.system(size: 29, weight: .bold, design: .rounded))
                                .accessibilityIdentifier("jidan.settings.title")
                            Text("看得见的动作驾驶舱")
                                .font(.subheadline)
                                .foregroundStyle(.white.opacity(0.62))
                        }
                        Spacer()
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 16, weight: .bold))
                                .frame(width: 46, height: 46)
                                .background(.white.opacity(0.09), in: Circle())
                                .overlay(Circle().stroke(.white.opacity(0.22), lineWidth: 1))
                        }
                        .accessibilityLabel("关闭鸡蛋设置")
                        .accessibilityIdentifier("jidan.settings.close")
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Label("一点就到这里", systemImage: "checkmark.circle.fill")
                            .font(.headline)
                            .foregroundStyle(Color(red: 0.49, green: 0.92, blue: 0.75))
                        Text("没有“请再确认一次”。你刚才点的是设置，这里就是设置。")
                            .font(.subheadline)
                            .foregroundStyle(.white.opacity(0.76))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(18)
                    .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 22))
                    .overlay(
                        RoundedRectangle(cornerRadius: 22)
                            .stroke(Color(red: 0.49, green: 0.92, blue: 0.75).opacity(0.38), lineWidth: 1)
                    )

                    Text("JCL 动作契约")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white.opacity(0.52))
                        .textCase(.uppercase)

                    VStack(spacing: 0) {
                        settingsRow(
                            title: "协议",
                            value: "JCL 0.1",
                            icon: "curlybraces",
                            identifier: "jidan.settings.protocol"
                        )
                        Divider().overlay(.white.opacity(0.12))
                        settingsRow(
                            title: "打开动作",
                            value: "NAVIGATION / DIRECT",
                            icon: "arrow.up.forward.app",
                            identifier: "jidan.settings.policy"
                        )
                        Divider().overlay(.white.opacity(0.12))
                        settingsRow(
                            title: "涉及钱和密码",
                            value: "停下，不自动执行",
                            icon: "hand.raised.fill",
                            identifier: "jidan.settings.money"
                        )
                        Divider().overlay(.white.opacity(0.12))
                        settingsRow(
                            title: "语音",
                            value: "只在你点麦克风后听",
                            icon: "mic.fill",
                            identifier: "jidan.settings.speech"
                        )
                    }
                    .background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 22))
                    .overlay(RoundedRectangle(cornerRadius: 22).stroke(.white.opacity(0.14), lineWidth: 1))

                    Text("鸡蛋现在还是运行在 iOS 里的驾驶舱 App，不是替换苹果内核的独立操作系统。")
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.56))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 2)
                }
                .padding(.horizontal, 22)
                .padding(.top, 18)
                .padding(.bottom, 28)
            }
        }
    }

    private func settingsRow(
        title: String,
        value: String,
        icon: String,
        identifier: String
    ) -> some View {
        HStack(spacing: 13) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color(red: 0.77, green: 0.69, blue: 0.98))
                .frame(width: 32, height: 32)
                .background(Color.purple.opacity(0.16), in: RoundedRectangle(cornerRadius: 9))
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                Text(value)
                    .font(.caption.monospaced())
                    .foregroundStyle(.white.opacity(0.62))
                    .accessibilityIdentifier(identifier)
            }
            Spacer(minLength: 4)
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 68)
    }
}

private struct JidanOrb: View {
    let mode: OrbMode

    var body: some View {
        ZStack {
            Circle()
                .fill(mode.accent.opacity(0.17))
                .blur(radius: 25)
                .scaleEffect(1.14)
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            Color.white.opacity(0.30),
                            mode.accent.opacity(0.32),
                            Color(red: 0.17, green: 0.12, blue: 0.31).opacity(0.74)
                        ],
                        center: .center,
                        startRadius: 4,
                        endRadius: 116
                    )
                )
                .overlay(Circle().stroke(mode.accent.opacity(0.55), lineWidth: 1.1))
            Circle()
                .stroke(.white.opacity(0.10), lineWidth: 1)
                .padding(22)
            Text("🌱 ʕ(˶ᵔ ᵕ ᵔ˶)ʔ ☀️")
                .font(.system(size: 18))
                .shadow(color: mode.accent, radius: 12)
        }
        .animation(.easeInOut(duration: 0.28), value: mode)
    }
}

private struct CosmicBackground: View {
    private let stars: [(CGFloat, CGFloat, CGFloat)] = [
        (0.11, 0.12, 2.0), (0.82, 0.09, 1.4), (0.23, 0.29, 1.2), (0.74, 0.33, 2.3),
        (0.93, 0.49, 1.1), (0.08, 0.57, 1.5), (0.62, 0.66, 1.2), (0.86, 0.73, 2.1),
        (0.17, 0.82, 1.0), (0.48, 0.91, 1.8), (0.95, 0.92, 1.2), (0.39, 0.18, 0.9)
    ]

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                LinearGradient(
                    colors: [
                        Color(red: 0.04, green: 0.04, blue: 0.13),
                        Color(red: 0.09, green: 0.06, blue: 0.22),
                        Color(red: 0.10, green: 0.03, blue: 0.12),
                        Color(red: 0.02, green: 0.02, blue: 0.08)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Circle()
                    .fill(Color.purple.opacity(0.18))
                    .frame(width: proxy.size.width * 0.95)
                    .blur(radius: 60)
                    .offset(x: -proxy.size.width * 0.22, y: -proxy.size.height * 0.20)
                Circle()
                    .fill(Color.pink.opacity(0.13))
                    .frame(width: proxy.size.width * 0.75)
                    .blur(radius: 70)
                    .offset(x: proxy.size.width * 0.32, y: proxy.size.height * 0.34)
                ForEach(stars.indices, id: \.self) { index in
                    let star = stars[index]
                    Circle()
                        .fill(.white.opacity(index.isMultiple(of: 3) ? 0.72 : 0.36))
                        .frame(width: star.2, height: star.2)
                        .position(x: proxy.size.width * star.0, y: proxy.size.height * star.1)
                        .shadow(color: .white.opacity(0.45), radius: 4)
                }
            }
        }
        .ignoresSafeArea()
    }
}

#Preview {
    ContentView()
}
