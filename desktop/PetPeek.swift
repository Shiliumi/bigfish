import Foundation
import CoreGraphics

struct PetPeekArt: Decodable { let file: String; let width: CGFloat; let height: CGFloat; let bounds: [CGFloat]; let edge_line: CGFloat? }
struct PetPeekManifest: Decodable { let assets: [String: PetPeekArt] }
/// Dedicated art is aligned to the physical screen edge. Never rotate a standing video.
enum PetPeekGeometry {
    static func frame(art: PetPeekArt, edge: PetEdge, in size: CGSize) -> CGRect {
        guard art.bounds.count == 4 else { return CGRect(origin: .zero, size: size) }
        let b = art.bounds, width = max(1, b[2] - b[0]), height = max(1, b[3] - b[1])
        let visibleHeight = edge == .bottom ? max(1, (art.edge_line ?? b[3]) - b[1]) : height
        let scale = min(size.width / width, size.height / visibleHeight)
        let image = CGSize(width: art.width * scale, height: art.height * scale)
        var x = (size.width - width * scale) / 2 - b[0] * scale
        var y = (size.height - height * scale) / 2 - b[1] * scale
        if edge == .right { x = size.width - b[2] * scale }
        if edge == .left { x = -(art.width - b[2]) * scale }
        if edge == .top { y = -b[1] * scale }
        if edge == .bottom { y = size.height - (art.edge_line ?? b[3]) * scale }
        return CGRect(origin: CGPoint(x: x, y: y), size: image)
    }
}
