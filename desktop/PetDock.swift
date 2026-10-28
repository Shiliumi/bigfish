import Foundation
import CoreGraphics

enum PetEdge: String, Codable, CaseIterable { case left, right, top, bottom }
struct PetDockState: Codable { var edge: PetEdge; var screen: String; var anchor: Double }
struct PetScreen { var id: String; var frame: CGRect; var visible: CGRect }

/// Pure desktop geometry, including negative-coordinate monitors and shared seams.
enum PetDockGeometry {
    static func body(in frame: CGRect) -> CGRect {
        let height = max(1, frame.height - 30)
        return CGRect(x: frame.minX + frame.width * 0.12, y: frame.minY + 30 + height * 0.06, width: frame.width * 0.76, height: height * 0.79)
    }
    static func screen(for frame: CGRect, screens: [PetScreen]) -> PetScreen? {
        screens.max { a, b in area(a.frame.intersection(frame)) < area(b.frame.intersection(frame)) }
    }
    private static func area(_ rect: CGRect) -> CGFloat { rect.isNull ? 0 : rect.width * rect.height }
    static func external(_ edge: PetEdge, screen: PetScreen, at point: CGPoint, screens: [PetScreen]) -> Bool {
        let probe: CGPoint
        switch edge {
        case .left: probe = CGPoint(x: screen.frame.minX - 1, y: point.y)
        case .right: probe = CGPoint(x: screen.frame.maxX + 1, y: point.y)
        case .top: probe = CGPoint(x: point.x, y: screen.frame.maxY + 1)
        case .bottom: probe = CGPoint(x: point.x, y: screen.frame.minY - 1)
        }
        return !screens.contains { $0.id != screen.id && $0.frame.contains(probe) }
    }
    static func nearby(frame: CGRect, screens: [PetScreen], threshold: CGFloat = 34) -> PetDockState? {
        guard let screen = screen(for: frame, screens: screens) else { return nil }
        let box = body(in: frame), area = screen.frame, point = CGPoint(x: box.midX, y: box.midY)
        let distances: [(PetEdge, CGFloat)] = [(.left, box.minX - area.minX), (.right, area.maxX - box.maxX), (.top, area.maxY - box.maxY), (.bottom, box.minY - area.minY)]
        guard let nearest = distances.filter({ $0.1 <= threshold && external($0.0, screen: screen, at: point, screens: screens) }).min(by: { abs($0.1) < abs($1.1) }) else { return nil }
        let vertical = nearest.0 == .left || nearest.0 == .right
        let raw = vertical ? (point.y - area.minY) / max(1, area.height) : (point.x - area.minX) / max(1, area.width)
        return PetDockState(edge: nearest.0, screen: screen.id, anchor: min(max(Double(raw), 0), 1))
    }
    static func peekSize(width: CGFloat, edge: PetEdge) -> CGSize {
        edge == .left || edge == .right ? CGSize(width: width * 0.70, height: width * 0.95) : edge == .top ? CGSize(width: width * 0.72, height: width * 1.02) : CGSize(width: width * 0.90, height: width * 0.85)
    }
    static func frame(_ dock: PetDockState, width: CGFloat, screens: [PetScreen], expanded: Bool) -> CGRect? {
        guard let screen = screens.first(where: { $0.id == dock.screen }) ?? screens.first else { return nil }
        let area = expanded ? screen.visible : screen.frame, size = expanded ? CGSize(width: width, height: width * 720 / 640 + 30) : peekSize(width: width, edge: dock.edge)
        let margin: CGFloat = expanded ? 14 : 0
        let anchor = CGFloat(min(max(dock.anchor, 0), 1)); var origin = CGPoint.zero
        switch dock.edge {
        case .left: origin = CGPoint(x: area.minX + margin, y: area.minY + area.height * anchor - size.height / 2)
        case .right: origin = CGPoint(x: area.maxX - size.width - margin, y: area.minY + area.height * anchor - size.height / 2)
        case .top: origin = CGPoint(x: area.minX + area.width * anchor - size.width / 2, y: area.maxY - size.height - margin)
        case .bottom: origin = CGPoint(x: area.minX + area.width * anchor - size.width / 2, y: area.minY + margin)
        }
        origin.x = min(max(origin.x, area.minX), area.maxX - size.width)
        origin.y = min(max(origin.y, area.minY), area.maxY - size.height)
        return CGRect(origin: origin, size: size)
    }
}

/// Once-only notices. Historic unread mail does not repeatedly pull the pet out.
final class PetNoticeQueue {
    private var seen = Set<String>(), queued: [[String: Any]] = []
    var hasPending: Bool { !queued.isEmpty }
    func append(_ notice: [String: Any], now: Date) {
        guard let id = notice["id"] as? String, let text = notice["text"] as? String, !text.isEmpty, !seen.contains(id) else { return }
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let stamp = notice["sent_at"] as? String, let sent = formatter.date(from: stamp), now.timeIntervalSince(sent) >= -60, now.timeIntervalSince(sent) < 15 * 60 else { return }
        seen.insert(id); queued.append(notice)
    }
    func take() -> [String: Any]? { queued.isEmpty ? nil : queued.removeFirst() }
}
