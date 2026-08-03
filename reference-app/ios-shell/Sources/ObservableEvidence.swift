import Foundation

enum ObservableEvidence {
    static let markerFileName = "jidan-observable-state.txt"

    static func record(_ state: String) {
        let environment = ProcessInfo.processInfo.environment
        guard let token = environment["JIDAN_OBSERVATION_TOKEN"], !token.isEmpty,
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first else {
            return
        }

        let marker = caches.appendingPathComponent(markerFileName, isDirectory: false)
        try? "\(token):\(state)\n".write(to: marker, atomically: true, encoding: .utf8)
    }
}
