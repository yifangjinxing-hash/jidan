import AVFoundation
import Speech

@MainActor
final class SpeechRecognizer: ObservableObject {
    @Published private(set) var isListening = false

    private let audioEngine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var hasAudioTap = false
    private var onPartial: ((String) -> Void)?
    private var onFinal: ((String) -> Void)?
    private var onFailure: ((String) -> Void)?

    func start(
        onPreparing: @escaping () -> Void,
        onStarted: @escaping () -> Void,
        onPartial: @escaping (String) -> Void,
        onFinal: @escaping (String) -> Void,
        onFailure: @escaping (String) -> Void
    ) {
        guard !isListening else { return }
        self.onPartial = onPartial
        self.onFinal = onFinal
        self.onFailure = onFailure
        onPreparing()

        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            Task { @MainActor in
                guard let self else { return }
                guard status == .authorized else {
                    self.fail("没有语音识别权限。你仍然可以打字。")
                    return
                }
                self.requestMicrophonePermission(onStarted: onStarted)
            }
        }
    }

    func stop() {
        cleanup(cancelTask: true)
    }

    private func requestMicrophonePermission(onStarted: @escaping () -> Void) {
        AVAudioApplication.requestRecordPermission { [weak self] granted in
            Task { @MainActor in
                guard let self else { return }
                guard granted else {
                    self.fail("没有麦克风权限。你仍然可以打字。")
                    return
                }
                do {
                    try self.beginRecognition()
                    onStarted()
                } catch {
                    self.fail("这台设备暂时不能听写。你仍然可以打字。")
                }
            }
        }
    }

    private func beginRecognition() throws {
        guard let recognizer, recognizer.isAvailable else {
            throw SpeechFailure.unavailable
        }

        cleanup(cancelTask: true, clearCallbacks: false)

        let audioSession = AVAudioSession.sharedInstance()
        try audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
        try audioSession.setActive(true, options: .notifyOthersOnDeactivation)

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        recognitionRequest = request

        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { throw SpeechFailure.noAudioInput }
        inputNode.installTap(onBus: 0, bufferSize: 1_024, format: format) { [weak request] buffer, _ in
            request?.append(buffer)
        }
        hasAudioTap = true

        audioEngine.prepare()
        try audioEngine.start()
        isListening = true

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let text = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal == true
            Task { @MainActor in
                guard let self else { return }
                if let text, !text.isEmpty {
                    self.onPartial?(text)
                }
                if isFinal, let text, !text.isEmpty {
                    let completion = self.onFinal
                    self.cleanup(cancelTask: false)
                    completion?(text)
                } else if error != nil {
                    self.fail("没有听清。请再说一次，或直接打字。")
                }
            }
        }
    }

    private func fail(_ message: String) {
        let failure = onFailure
        cleanup(cancelTask: true)
        failure?(message)
    }

    private func cleanup(cancelTask: Bool, clearCallbacks: Bool = true) {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        if hasAudioTap {
            audioEngine.inputNode.removeTap(onBus: 0)
            hasAudioTap = false
        }
        recognitionRequest?.endAudio()
        if cancelTask {
            recognitionTask?.cancel()
        }
        recognitionTask = nil
        recognitionRequest = nil
        isListening = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        if clearCallbacks {
            onPartial = nil
            onFinal = nil
            onFailure = nil
        }
    }
}

private enum SpeechFailure: Error {
    case unavailable
    case noAudioInput
}
