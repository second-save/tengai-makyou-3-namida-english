// Japanese speech -> timed text for movie audio (subtitle work). macOS Speech framework, on-device when available.
// usage: swiftc -O tools/asrjp.swift -o work/asrjp && work/asrjp AUDIO.wav [...]
// Prints per file: "#file", then "start<TAB>end<TAB>text" segments (seconds). A transcript draft, to be checked.
import Foundation
import Speech

let sem = DispatchSemaphore(value: 0)
SFSpeechRecognizer.requestAuthorization { _ in sem.signal() }
sem.wait()
guard let rec = SFSpeechRecognizer(locale: Locale(identifier: "ja-JP")), rec.isAvailable else {
    print("ERROR recognizer unavailable (status \(SFSpeechRecognizer.authorizationStatus().rawValue))"); exit(1)
}
for path in CommandLine.arguments.dropFirst() {
    let req = SFSpeechURLRecognitionRequest(url: URL(fileURLWithPath: path))
    req.shouldReportPartialResults = false
    if rec.supportsOnDeviceRecognition { req.requiresOnDeviceRecognition = true }
    req.addsPunctuation = true
    let done = DispatchSemaphore(value: 0)
    print("#\(path)")
    var finished = false
    rec.recognitionTask(with: req) { result, error in
        if let r = result, r.isFinal {
            // group word segments into phrases split at pauses > 0.6 s
            var line = ""; var st = -1.0; var en = 0.0
            for s in r.bestTranscription.segments {
                if st >= 0 && s.timestamp - en > 0.6 { print(String(format: "%.2f\t%.2f\t%@", st, en, line)); line = ""; st = -1 }
                if st < 0 { st = s.timestamp }
                line += s.substring; en = s.timestamp + s.duration
            }
            if !line.isEmpty { print(String(format: "%.2f\t%.2f\t%@", st, en, line)) }
            finished = true; done.signal()
        } else if let e = error, !finished { print("ERROR \(e.localizedDescription)"); finished = true; done.signal() }
    }
    while done.wait(timeout: .now() + 0.1) == .timedOut { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
    fflush(stdout)
}
