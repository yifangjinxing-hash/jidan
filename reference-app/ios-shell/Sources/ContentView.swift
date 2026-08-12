import SwiftUI
import UIKit

private struct HomeNotice: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}

struct ContentView: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var speech = SpeechRecognizer()
    @State private var input = ""
    @State private var isWorking = false
    @State private var didRunDemo = false
    @State private var isSettingsPresented = false
    @State private var notice: HomeNotice?

    var body: some View {
        ZStack {
            Color(uiColor: .systemBackground)
                .ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer(minLength: 24)
                commandBar
                recentCommands
                Spacer(minLength: 24)
            }
            .frame(maxWidth: 560)
            .padding(.horizontal, 24)
            .padding(.vertical, 16)
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
        }
        .fullScreenCover(isPresented: $isSettingsPresented) {
            JidanSettingsView()
        }
        .alert(item: $notice) { notice in
            Alert(
                title: Text(notice.title),
                message: Text(notice.message),
                dismissButton: .default(Text("好"))
            )
        }
    }

    private var commandBar: some View {
        HStack(spacing: 12) {
            Image(systemName: speech.isListening ? "waveform" : "magnifyingglass")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(speech.isListening ? Color.accentColor : Color.secondary)

            TextField("输入或说出指令", text: $input)
                .textInputAutocapitalization(.never)
                .submitLabel(.go)
                .lineLimit(1)
                .onSubmit { submit(input) }
                .accessibilityLabel("输入指令")
                .accessibilityIdentifier("jidan.command.input")

            Button(action: performPrimaryAction) {
                Group {
                    if isWorking {
                        ProgressView()
                            .tint(primaryActionForeground)
                    } else {
                        Image(systemName: primaryActionSymbol)
                            .font(.system(size: 16, weight: .semibold))
                    }
                }
                .frame(width: 44, height: 44)
                .foregroundStyle(primaryActionForeground)
                .background(primaryActionBackground, in: Circle())
                .contentShape(Circle())
            }
            .disabled(isWorking)
            .accessibilityLabel(primaryActionAccessibilityLabel)
            .accessibilityIdentifier(primaryActionIdentifier)
        }
        .padding(.leading, 18)
        .padding(.trailing, 8)
        .frame(minHeight: 62)
        .background(
            Color(uiColor: .secondarySystemBackground),
            in: RoundedRectangle(cornerRadius: 20, style: .continuous)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(
                    speech.isListening ? Color.accentColor.opacity(0.72) : Color.primary.opacity(0.08),
                    lineWidth: speech.isListening ? 1.5 : 1
                )
        }
        .animation(.easeInOut(duration: 0.18), value: speech.isListening)
        .animation(.easeInOut(duration: 0.18), value: normalizedInput.isEmpty)
    }

    private var recentCommands: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("最近使用")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 4)

            VStack(spacing: 0) {
                recentCommand(
                    "打开支付宝",
                    icon: "arrow.up.forward.app",
                    identifier: "jidan.quick.alipay"
                )
                Divider()
                    .padding(.leading, 54)
                recentCommand(
                    "打开鸡蛋设置",
                    icon: "gearshape",
                    identifier: "jidan.quick.settings"
                )
            }
            .background(
                Color(uiColor: .secondarySystemBackground),
                in: RoundedRectangle(cornerRadius: 18, style: .continuous)
            )
        }
    }

    private func recentCommand(_ command: String, icon: String, identifier: String) -> some View {
        Button {
            submit(command)
        } label: {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 24)
                Text(command)
                    .font(.body)
                    .foregroundStyle(.primary)
                Spacer()
                Image(systemName: "arrow.up.left")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 56)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
    }

    private var normalizedInput: String {
        input.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var primaryActionSymbol: String {
        if speech.isListening { return "stop.fill" }
        return normalizedInput.isEmpty ? "mic.fill" : "arrow.up"
    }

    private var primaryActionBackground: Color {
        if speech.isListening { return Color.red }
        return normalizedInput.isEmpty ? Color.clear : Color.accentColor
    }

    private var primaryActionForeground: Color {
        if speech.isListening || !normalizedInput.isEmpty { return Color.white }
        return Color.secondary
    }

    private var primaryActionAccessibilityLabel: String {
        if speech.isListening { return "停止听写" }
        return normalizedInput.isEmpty ? "开始听写" : "执行指令"
    }

    private var primaryActionIdentifier: String {
        if speech.isListening { return "jidan.command.stop" }
        return normalizedInput.isEmpty ? "jidan.command.mic" : "jidan.command.submit"
    }

    @MainActor
    private func performPrimaryAction() {
        if speech.isListening {
            speech.stop()
        } else if normalizedInput.isEmpty {
            toggleSpeech()
        } else {
            submit(input)
        }
    }

    @MainActor
    private func submit(_ raw: String) {
        if speech.isListening { speech.stop() }
        input = raw
        switch CommandPolicy.parse(raw) {
        case let .direct(proposal):
            isWorking = true
            Task { @MainActor in
                let outcome = await IOSActionDispatcher().dispatch(proposal)
                isWorking = false
                apply(outcome)
            }

        case let .rejected(title, message):
            notice = HomeNotice(title: title, message: message)

        case let .unsupported(message):
            notice = HomeNotice(title: "暂时不能完成", message: message)
        }
    }

    @MainActor
    private func apply(_ outcome: DispatchOutcome) {
        switch outcome {
        case .presentJidanSettings:
            isSettingsPresented = true
            ObservableEvidence.record("settings_dispatched")
        case let .targetUnavailable(title, message):
            notice = HomeNotice(title: title, message: message)
            ObservableEvidence.record("alipay_target_unavailable")
        case let .blocked(title, message):
            notice = HomeNotice(title: title, message: message)
            ObservableEvidence.record("blocked")
        }
    }

    @MainActor
    private func toggleSpeech() {
        if speech.isListening {
            speech.stop()
            return
        }

        speech.start(
            onPreparing: {
                notice = nil
            },
            onStarted: {},
            onPartial: { text in
                input = text
            },
            onFinal: { text in
                input = text
                submit(text)
            },
            onFailure: { message in
                notice = HomeNotice(title: "语音暂不可用", message: message)
            }
        )
    }
}

private struct JidanSettingsView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("动作") {
                    LabeledContent("协议") {
                        Text("JCL 0.1")
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("jidan.settings.protocol")
                    }
                    LabeledContent("打开方式") {
                        Text("NAVIGATION / DIRECT")
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("jidan.settings.policy")
                    }
                }

                Section("隐私") {
                    LabeledContent("敏感操作") {
                        Text("停止并交给你")
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("jidan.settings.money")
                    }
                    LabeledContent("语音") {
                        Text("仅在使用时")
                            .foregroundStyle(.secondary)
                            .accessibilityIdentifier("jidan.settings.speech")
                    }
                }

                Section {
                    Text("Jidan 目前作为 iOS App 运行。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("鸡蛋设置")
                        .font(.headline)
                        .accessibilityIdentifier("jidan.settings.title")
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") {
                        dismiss()
                    }
                    .accessibilityIdentifier("jidan.settings.close")
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
