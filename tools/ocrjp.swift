// Japanese text finder for texture dumps (leftover-Japanese scan, tools/jpleft.py notes).
// usage: swiftc -O tools/ocrjp.swift -o work/ocrjp && work/ocrjp FILE.png [...]  (or a directory)
// Prints "path<TAB>text" for every image where macOS Vision reads kana/kanji. Images are upscaled 4x first
// (textures are small). Vision misses stylised brush lettering and invents text in noise: a triage, not proof.
import Foundation
import Vision
import AppKit

func hasJapanese(_ s: String) -> Bool {
    s.unicodeScalars.contains { (0x3040...0x30FF).contains($0.value) || (0x4E00...0x9FFF).contains($0.value) }
}

func scan(_ path: String) {
    guard let img = NSImage(contentsOfFile: path),
          let cg0 = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
    let w = cg0.width * 4, h = cg0.height * 4
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { return }
    ctx.setFillColor(CGColor(red: 0.2, green: 0.2, blue: 0.35, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.interpolationQuality = .high
    ctx.draw(cg0, in: CGRect(x: 0, y: 0, width: w, height: h))
    guard let cg = ctx.makeImage() else { return }
    let req = VNRecognizeTextRequest()
    req.recognitionLanguages = ["ja-JP"]; req.recognitionLevel = .accurate; req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    let texts = (req.results ?? []).compactMap { $0.topCandidates(1).first }.filter { $0.confidence > 0.3 }.map { $0.string }
    let jp = texts.filter(hasJapanese)
    if !jp.isEmpty { print("\(path)\t\(jp.joined(separator: " | "))"); fflush(stdout) }
}

var paths: [String] = []
for a in CommandLine.arguments.dropFirst() {
    var isDir: ObjCBool = false
    if FileManager.default.fileExists(atPath: a, isDirectory: &isDir), isDir.boolValue {
        let items = (try? FileManager.default.contentsOfDirectory(atPath: a)) ?? []
        paths += items.filter { $0.hasSuffix(".png") }.sorted().map { "\(a)/\($0)" }
    } else { paths.append(a) }
}
for p in paths { autoreleasepool { scan(p) } }
