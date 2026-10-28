import Cocoa

final class GreetingPanel: NSPanel { override var canBecomeKey: Bool { true } }
final class GreetingContent: NSView {
    var hovered = false
    private var tracking: NSTrackingArea?
    override func updateTrackingAreas() {
        super.updateTrackingAreas(); if let tracking = tracking { removeTrackingArea(tracking) }
        tracking = NSTrackingArea(rect: bounds, options: [.activeAlways,.mouseEnteredAndExited,.inVisibleRect], owner: self); addTrackingArea(tracking!)
    }
    override func mouseEntered(with event: NSEvent) { hovered = true }
    override func mouseExited(with event: NSEvent) { hovered = false }
}

/// A passive bubble, deliberately separate from the focusable chat composer.
final class PetGreeting: NSObject {
    let panel: GreetingPanel, content: GreetingContent
    let text = NSTextField(wrappingLabelWithString: ""), title = NSTextField(labelWithString: "大肥鱼"), button = NSButton(title: "接着聊", target: nil, action: nil)
    var open: (() -> Void)?, dismiss: (() -> Void)?
    var visible: Bool { panel.isVisible }
    var hovered: Bool { content.hovered || panel.isKeyWindow }
    override init() {
        panel = GreetingPanel(contentRect: NSRect(x: 0, y: 0, width: 300, height: 176), styleMask: [.borderless,.nonactivatingPanel], backing: .buffered, defer: false)
        content = GreetingContent(frame: NSRect(x: 0, y: 0, width: 300, height: 176)); super.init()
        panel.title = "大肥鱼的招呼气泡"; panel.backgroundColor = .clear; panel.isOpaque = false; panel.hasShadow = true; panel.level = .floating; panel.hidesOnDeactivate = false; panel.isReleasedWhenClosed = false; panel.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary]
        panel.contentView = content; content.wantsLayer = true; content.layer?.backgroundColor = NSColor(calibratedRed: 0.99, green: 0.995, blue: 1, alpha: 0.98).cgColor; content.layer?.cornerRadius = 18; content.layer?.borderColor = NSColor(calibratedRed: 0.84, green: 0.90, blue: 0.97, alpha: 1).cgColor; content.layer?.borderWidth = 1
        title.font = .systemFont(ofSize: 12, weight: .semibold); title.textColor = NSColor(calibratedRed: 0.31, green: 0.41, blue: 0.56, alpha: 1); title.frame = NSRect(x: 18, y: 142, width: 235, height: 18); content.addSubview(title)
        text.font = .systemFont(ofSize: 12); text.textColor = NSColor(calibratedRed: 0.34, green: 0.42, blue: 0.54, alpha: 1); text.frame = NSRect(x: 18, y: 46, width: 264, height: 88); text.maximumNumberOfLines = 5; text.lineBreakMode = .byTruncatingTail; text.setAccessibilityLabel("小鲸鱼的主动招呼"); content.addSubview(text)
        button.frame = NSRect(x: 167, y: 12, width: 115, height: 25); button.bezelStyle = .rounded; button.font = .systemFont(ofSize: 10); button.target = self; button.action = #selector(openAction); content.addSubview(button)
        let close = NSButton(title: "×", target: self, action: #selector(closeAction)); close.frame = NSRect(x: 266, y: 140, width: 21, height: 22); close.isBordered = false; close.setAccessibilityLabel("收起招呼气泡"); content.addSubview(close)
        let hint = NSTextField(labelWithString: "不用急着回。"); hint.font = .systemFont(ofSize: 9); hint.textColor = .secondaryLabelColor; hint.frame = NSRect(x: 18, y: 18, width: 120, height: 14); content.addSubview(hint)
    }
    func show(message: String, kind: String, near frame: CGRect, screens: [PetScreen]) {
        text.stringValue = message; title.stringValue = kind == "preview" ? "大肥鱼 · 招呼预览" : "大肥鱼"; button.title = kind == "balance" ? "补点鱼粮 ↗" : kind == "surf" ? "看看发现" : "聊两句"
        let area = PetDockGeometry.screen(for: frame, screens: screens)?.visible ?? NSScreen.main!.visibleFrame
        let size = panel.frame.size
        var point = CGPoint(x: frame.midX < area.midX ? frame.maxX + 8 : frame.minX - size.width - 8, y: frame.midY - size.height / 2)
        point.x = min(max(point.x, area.minX + 8), area.maxX - size.width - 8); point.y = min(max(point.y, area.minY + 8), area.maxY - size.height - 8)
        panel.setFrameOrigin(point); panel.orderFrontRegardless()
        // Preview is explicitly opened from the menu. Actual incoming greetings
        // only order the nonactivating panel forward and never take keyboard focus.
        if kind == "preview" { panel.makeKeyAndOrderFront(nil) }
    }
    func hide() { panel.orderOut(nil) }
    @objc private func openAction() { open?() }
    @objc private func closeAction() { hide(); dismiss?() }
}
