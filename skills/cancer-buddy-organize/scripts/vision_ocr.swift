// vision_ocr.swift — Apple Vision text recognition for the organize second read (macOS only).
//
// Built and cached by scripts/run_ocr_engine.py (swiftc -O; the binary is keyed by this file's hash).
//   vision_ocr recognize <image>  → {engine, revision, os_version, languages, width, height,
//                                    observations: [{text, confidence, bbox:[x,y,w,h] top-left origin,
//                                                    normalised, candidates:[{text, confidence}] (top 3)]}
//   vision_ocr orient <image>     → {rotation: clockwise degrees that make the text upright, votes}
//                                    (no recognised text is printed: orientation runs before anyone reads)
// VNRecognizeTextRequest, recognitionLevel accurate, zh-Hans + en-US, usesLanguageCorrection = false.
// Output keys are sorted and numbers rounded, so the same image gives the same bytes.
import Foundation
import ImageIO
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(2)
}

func loadImage(_ path: String) -> CGImage {
    let url = URL(fileURLWithPath: path)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        fail("cannot read image \(path)")
    }
    return img
}

func round4(_ v: Double) -> Double { (v * 10000).rounded() / 10000 }

func recognize(_ img: CGImage, _ orientation: CGImagePropertyOrientation) -> ([VNRecognizedTextObservation], Int) {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    let handler = VNImageRequestHandler(cgImage: img, orientation: orientation, options: [:])
    do { try handler.perform([req]) } catch { fail("Vision failed: \(error)") }
    return (req.results ?? [], req.revision)
}

func emit(_ obj: Any) {
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys]) else {
        fail("cannot serialise output")
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

let args = CommandLine.arguments
if args.count != 3 || !["recognize", "orient"].contains(args[1]) {
    fail("usage: vision_ocr recognize|orient <image>")
}
let img = loadImage(args[2])

if args[1] == "orient" {
    // Vision reads rotated text anyway; the rotated quadrilateral of each observation gives the text
    // baseline's direction. Vote (weighted by characters) for the quarter turn: angle 0 = upright,
    // -90 = content turned 90° clockwise (fix: rotate 270° clockwise), 90 → 90, 180 → 180.
    let (obs, _) = recognize(img, .up)
    let w = Double(img.width), h = Double(img.height)
    var votes: [String: Double] = ["0": 0, "90": 0, "180": 0, "270": 0]
    for ob in obs {
        guard let c = ob.topCandidates(1).first else { continue }
        let dx = (Double(ob.topRight.x) - Double(ob.topLeft.x)) * w
        let dy = (Double(ob.topRight.y) - Double(ob.topLeft.y)) * h
        var deg = Int((atan2(dy, dx) * 180 / Double.pi / 90).rounded()) * 90
        deg = ((deg % 360) + 360) % 360
        votes[String(deg), default: 0] += Double(c.string.count)
    }
    var best = "0"
    for k in ["0", "90", "180", "270"] where votes[k]! > votes[best]! { best = k }
    emit(["rotation": Int(best)!, "votes": votes])
    exit(0)
}

let (obs, revision) = recognize(img, .up)
var out: [[String: Any]] = []
for ob in obs {
    let cands = ob.topCandidates(3)
    guard let top = cands.first else { continue }
    let b = ob.boundingBox
    out.append([
        "text": top.string,
        "confidence": round4(Double(top.confidence)),
        "bbox": [round4(Double(b.origin.x)), round4(Double(1 - b.origin.y - b.size.height)),
                 round4(Double(b.size.width)), round4(Double(b.size.height))],
        "candidates": cands.map { ["text": $0.string, "confidence": round4(Double($0.confidence))] },
    ])
}
emit([
    "engine": "apple_vision",
    "revision": revision,
    "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
    "languages": ["zh-Hans", "en-US"],
    "width": img.width,
    "height": img.height,
    "observations": out,
])
