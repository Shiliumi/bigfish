import Foundation
import AVFoundation
import CoreGraphics
@main struct Inspect {
    static func main() throws {
        for path in CommandLine.arguments.dropFirst() {
            let asset = AVURLAsset(url: URL(fileURLWithPath: path)), generator = AVAssetImageGenerator(asset: AVURLAsset(url: URL(fileURLWithPath: path)))
            let image = try generator.copyCGImage(at: CMTime(seconds: 2, preferredTimescale: 600), actualTime: nil)
            guard image.width == 640, image.height == 720 else { fatalError("Wrong source resolution") }
            var bytes = [UInt8](repeating: 0, count: 640 * 720 * 4)
            let context = CGContext(data: &bytes, width: 640, height: 720, bitsPerComponent: 8, bytesPerRow: 640 * 4, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            context.draw(image, in: CGRect(x: 0, y: 0, width: 640, height: 720))
            let opaque = stride(from: 3, to: bytes.count, by: 4).filter { bytes[$0] > 240 }.count
            let transparent = stride(from: 3, to: bytes.count, by: 4).filter { bytes[$0] < 10 }.count
            guard transparent > 100000, opaque > 30000 else { fatalError("Alpha or character missing: \(path)") }
            print(URL(fileURLWithPath: path).lastPathComponent, "640x720", "alpha verified", "opaque pixels", opaque, "duration", CMTimeGetSeconds(asset.duration))
        }
    }
}
