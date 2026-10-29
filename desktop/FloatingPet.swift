import Cocoa
import AVFoundation
import QuartzCore

struct PetClip: Decodable { let label: String, duration: Double, mov: String, poster: String }
struct PetAssets: Decodable { let animations: [String: PetClip] }
final class PetPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

/// Hardware-decoded 24fps alpha video. Overlapping players prevent black flashes.
final class PetVideoView: NSView {
    var clips: [String: PetClip] = [:]
    var tapped: ((Bool, Bool) -> Void)?, dragBegan: (() -> Void)?, dragEnded: (() -> Void)?, menuBuilder: (() -> NSMenu)?, hoverChanged: ((Bool) -> Void)?
    private let poster = CALayer(), peekArtwork = CALayer()
    private var peekAssets: [String: PetPeekArt] = [:], selectedPeek: PetPeekArt?
    private var movie: AVPlayerLayer?, player: AVQueuePlayer?, looper: AVPlayerLooper?, readiness: NSKeyValueObservation?
    private var name = "", generation = 0, active = true
    private var startMouse = NSPoint.zero, startOrigin = NSPoint.zero, moved = false
    private var tracking: NSTrackingArea?
    private var peekEdge: PetEdge?, referenceWidth: CGFloat = 220
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    override init(frame: NSRect) {
        super.init(frame: frame); wantsLayer = true; layer?.backgroundColor = NSColor.clear.cgColor; layer?.masksToBounds = true
        poster.contentsGravity = .resizeAspect; layer?.addSublayer(poster)
        peekArtwork.contentsGravity = .resizeAspect; peekArtwork.opacity = 0; peekArtwork.contentsScale = NSScreen.main?.backingScaleFactor ?? 2; layer?.addSublayer(peekArtwork)
        if let url = Bundle.main.url(forResource: "peek-manifest", withExtension: "json", subdirectory: "pet"), let data = try? Data(contentsOf: url), let manifest = try? JSONDecoder().decode(PetPeekManifest.self, from: data) { peekAssets = manifest.assets }
        if let url = Bundle.main.url(forResource: "manifest", withExtension: "json", subdirectory: "pet"), let data = try? Data(contentsOf: url), let manifest = try? JSONDecoder().decode(PetAssets.self, from: data) { clips = manifest.animations }
        setAccessibilityElement(true); setAccessibilityRole(.button); setAccessibilityLabel("大肥鱼小鲸鱼，摸摸头、拖动或点开聊天，右键可选动作")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func accessibilityPerformPress() -> Bool { tapped?(true, true); return true }
    override func layout() { super.layout(); CATransaction.begin(); CATransaction.setDisableActions(true); configure(poster); for item in layer?.sublayers?.compactMap({$0 as? AVPlayerLayer}) ?? [] { configure(item) }; configurePeek(); CATransaction.commit() }
    func setPeek(_ edge: PetEdge?, width: CGFloat) {
        CATransaction.begin(); CATransaction.setDisableActions(true)
        peekEdge = edge; referenceWidth = width; peekArtwork.removeAllAnimations()
        if let edge = edge, let art = peekAssets[edge == .left || edge == .right ? "right" : edge.rawValue], let folder = Bundle.main.resourceURL?.appendingPathComponent("pet"), let image = NSImage(contentsOf: folder.appendingPathComponent(art.file)) {
            generation += 1; readiness = nil; player?.pause(); player = nil; looper = nil; movie = nil
            for item in layer?.sublayers?.compactMap({$0 as? AVPlayerLayer}) ?? [] { item.player?.pause(); item.removeFromSuperlayer() }
            selectedPeek = art; peekArtwork.contents = image.cgImage(forProposedRect: nil, context: nil, hints: nil); peekArtwork.opacity = 1; poster.opacity = 0
        } else { selectedPeek = nil; peekArtwork.opacity = 0; poster.opacity = 1; name = "" }
        needsLayout = true; layoutSubtreeIfNeeded(); CATransaction.commit(); breathePeek()
    }
    private func configure(_ item: CALayer) { item.setAffineTransform(.identity); item.frame = bounds }
    private func configurePeek() {
        guard let edge = peekEdge, let art = selectedPeek else { return }
        peekArtwork.setAffineTransform(.identity); peekArtwork.frame = PetPeekGeometry.frame(art: art, edge: edge, in: bounds.size)
        if edge == .left { peekArtwork.setAffineTransform(CGAffineTransform(scaleX: -1, y: 1)) }
    }
    private func breathePeek() {
        guard active, let edge = peekEdge, selectedPeek != nil, !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
        peekArtwork.removeAllAnimations()
        let horizontal = edge == .left || edge == .right
        let animation = CABasicAnimation(keyPath: horizontal ? "position.x" : "position.y")
        let point = horizontal ? peekArtwork.position.x : peekArtwork.position.y
        animation.fromValue = point; animation.toValue = point + (edge == .left || edge == .top ? -1.4 : 1.4)
        animation.duration = 2.7; animation.autoreverses = true; animation.repeatCount = .infinity; animation.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        peekArtwork.add(animation, forKey: "peek-breath")
    }
    override func updateTrackingAreas() {
        super.updateTrackingAreas(); if let tracking = tracking { removeTrackingArea(tracking) }
        tracking = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self); addTrackingArea(tracking!)
    }
    override func mouseEntered(with event: NSEvent) { hoverChanged?(true) }
    override func mouseExited(with event: NSEvent) { hoverChanged?(false) }
    func play(_ requested: String) {
        if peekEdge != nil && selectedPeek != nil { return }
        let chosen = clips[requested] == nil ? "idle" : requested
        guard name != chosen, let clip = clips[chosen] else { return }
        name = chosen; generation += 1; let token = generation
        let folder = Bundle.main.resourceURL!.appendingPathComponent("pet")
        if let image = NSImage(contentsOf: folder.appendingPathComponent(clip.poster)) { poster.contents = image.cgImage(forProposedRect: nil, context: nil, hints: nil) }
        let outdated = layer?.sublayers?.compactMap { $0 as? AVPlayerLayer } ?? []
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion { for item in outdated { item.player?.pause(); item.removeFromSuperlayer() }; movie = nil; player?.pause(); player = nil; looper = nil; poster.opacity = 1; return }
        let next = AVQueuePlayer(); next.isMuted = true; next.automaticallyWaitsToMinimizeStalling = false
        let loop = AVPlayerLooper(player: next, templateItem: AVPlayerItem(url: folder.appendingPathComponent(clip.mov)))
        let nextLayer = AVPlayerLayer(player: next); nextLayer.videoGravity = .resizeAspect; configure(nextLayer); nextLayer.opacity = 0; nextLayer.backgroundColor = NSColor.clear.cgColor
        layer?.addSublayer(nextLayer)
        readiness = nextLayer.observe(\.isReadyForDisplay, options: [.new, .initial]) { [weak self, weak nextLayer] view, _ in
            guard view.isReadyForDisplay else { return }
            DispatchQueue.main.async {
                guard let self = self, let nextLayer = nextLayer, self.generation == token else { return }
                CATransaction.begin(); CATransaction.setAnimationDuration(0.12); nextLayer.opacity = 1; self.poster.opacity = 0; for item in outdated { item.opacity = 0 }; CATransaction.commit()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) { for item in outdated { item.player?.pause(); item.removeFromSuperlayer() } }
            }
        }
        movie = nextLayer; player = next; looper = loop
        if active { next.play() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self, weak nextLayer] in
            guard let self = self, let nextLayer = nextLayer, self.generation == token, !nextLayer.isReadyForDisplay else { return }
            self.poster.opacity = 1; for item in outdated { item.player?.pause(); item.removeFromSuperlayer() }
        }
    }
    func setActive(_ value: Bool) { active = value; if !value { peekArtwork.removeAllAnimations() } else { breathePeek() }; if value && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion { player?.play() } else { player?.pause() } }
    func refreshMotionPreference() { if peekEdge != nil { peekArtwork.removeAllAnimations(); breathePeek() }; let saved = name; name = ""; play(saved) }
    func bounce() {
        guard !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
        let animation = CASpringAnimation(keyPath: "transform.translation.y"); animation.fromValue = -9; animation.toValue = 0; animation.damping = 7; animation.stiffness = 160; animation.mass = 0.6; animation.duration = animation.settlingDuration
        layer?.add(animation, forKey: "put-down")
    }
    override func mouseDown(with event: NSEvent) { startMouse = NSEvent.mouseLocation; startOrigin = window?.frame.origin ?? .zero; moved = false }
    override func mouseDragged(with event: NSEvent) {
        let point = NSEvent.mouseLocation
        if !moved && abs(point.x - startMouse.x) + abs(point.y - startMouse.y) > 4 { moved = true; dragBegan?(); startOrigin = window?.frame.origin ?? startOrigin; startMouse = point }
        if moved { window?.setFrameOrigin(NSPoint(x: startOrigin.x + point.x - startMouse.x, y: startOrigin.y + point.y - startMouse.y)) }
    }
    override func mouseUp(with event: NSEvent) { if moved { dragEnded?(); bounce() } else { let point = convert(event.locationInWindow, from: nil); bounce(); tapped?(point.y < bounds.height * 0.48, event.clickCount >= 2) } }
    override func rightMouseDown(with event: NSEvent) { if let menu = menuBuilder?() { NSMenu.popUpContextMenu(menu, with: event, for: self) } }
    override func keyDown(with event: NSEvent) { if event.keyCode == 36 || event.keyCode == 49 { tapped?(false, true) } else { super.keyDown(with: event) } }
}

final class PetChat: NSViewController, NSTextFieldDelegate {
    var submit: ((String) -> Void)?, openFish: (() -> Void)?, openInbox: (() -> Void)?, close: (() -> Void)?
    let text = NSTextView(), field = NSTextField(), status = NSTextField(labelWithString: ""), sendButton = NSButton(title: "发送", target: nil, action: nil)
    let scroll = NSScrollView()
    var waiting = false
    var lastSubmitted = ""
    override func loadView() {
        let root = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: 330, height: 338)); root.material = .popover; root.state = .active; root.appearance = NSAppearance(named: .aqua); view = root
        let title = NSTextField(labelWithString: "大肥鱼"); title.font = .systemFont(ofSize: 15, weight: .semibold); title.frame = NSRect(x: 20, y: 298, width: 160, height: 22); root.addSubview(title)
        let close = NSButton(title: "×", target: self, action: #selector(closePopover)); close.frame = NSRect(x: 287, y: 298, width: 26, height: 24); close.isBordered = false; close.setAccessibilityLabel("收起对话气泡"); root.addSubview(close)
        status.font = .systemFont(ofSize: 10); status.textColor = .secondaryLabelColor; status.frame = NSRect(x: 20, y: 275, width: 285, height: 18); root.addSubview(status)
        scroll.frame = NSRect(x: 20, y: 99, width: 290, height: 165); scroll.drawsBackground = false; scroll.hasVerticalScroller = true; scroll.borderType = .noBorder
        text.frame = NSRect(x: 0, y: 0, width: 278, height: 165); text.isEditable = false; text.isSelectable = true; text.drawsBackground = false; text.font = .systemFont(ofSize: 13); text.textColor = NSColor(calibratedRed: 0.28, green: 0.34, blue: 0.44, alpha: 1); text.textContainerInset = NSSize(width: 0, height: 4); text.autoresizingMask = [.width]; text.isVerticallyResizable = true; text.isHorizontallyResizable = false; text.textContainer?.widthTracksTextView = true
        text.setAccessibilityLabel("小鲸鱼的回复"); scroll.documentView = text; root.addSubview(scroll)
        field.frame = NSRect(x: 20, y: 53, width: 229, height: 30); field.placeholderString = "和她说点什么…"; field.font = .systemFont(ofSize: 12); field.bezelStyle = .roundedBezel; field.delegate = self; field.target = self; field.action = #selector(send); field.setAccessibilityLabel("桌宠聊天消息"); root.addSubview(field)
        sendButton.target = self; sendButton.action = #selector(send); sendButton.frame = NSRect(x: 255, y: 53, width: 56, height: 30); sendButton.bezelStyle = .rounded; sendButton.contentTintColor = .systemBlue; root.addSubview(sendButton)
        let fish = NSButton(title: "打开完整聊天 ↗", target: self, action: #selector(openChat)); fish.frame = NSRect(x: 14, y: 15, width: 150, height: 24); fish.isBordered = false; fish.font = .systemFont(ofSize: 10); root.addSubview(fish)
        let inbox = NSButton(title: "看看来信", target: self, action: #selector(letters)); inbox.frame = NSRect(x: 237, y: 15, width: 80, height: 24); inbox.isBordered = false; inbox.font = .systemFont(ofSize: 10); root.addSubview(inbox)
    }
    @objc func closePopover() { close?() }
    @objc func openChat() { openFish?() }
    @objc func letters() { openInbox?() }
    @objc func send() { let value = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines); guard !value.isEmpty, !waiting else { return }; lastSubmitted = value; waiting = true; sendButton.isEnabled = false; status.stringValue = "正在递给她…"; submit?(value) }
    func receive(status value: String, message: String) {
        loadViewIfNeeded(); waiting = ["thinking", "streaming", "approval"].contains(value); sendButton.isEnabled = !waiting
        status.stringValue = value == "streaming" ? "她正在说…" : value == "thinking" ? "她在想怎么回你…" : value == "approval" ? "需要在完整聊天中确认" : value == "error" ? "这次没能完成回复" : "和完整聊天共用这一段对话"
        if value == "thinking" { field.stringValue = ""; text.string = "" }
        if value == "error" && field.stringValue.isEmpty { field.stringValue = lastSubmitted }
        if value == "complete" { lastSubmitted = "" }
        if !message.isEmpty { text.string = String(message.prefix(12000)).replacingOccurrences(of: "!\\[[^\\]]*\\]\\([^)]*\\)", with: "（表情包在完整聊天里）", options: .regularExpression); if value == "streaming" { text.scrollToEndOfDocument(nil) } }
    }
    func focusInput() { view.window?.makeFirstResponder(field) }
}

final class FloatingPet: NSObject {
    let panel: PetPanel, sprite: PetVideoView
    let behavior = PetBehavior(), popover = NSPopover(), chat = PetChat(), label = NSTextField(labelWithString: "")
    var timer: Timer?
    var open: (() -> Void)?, inbox: (() -> Void)?, visibilityChanged: (() -> Void)?, send: ((String) -> Void)?
    var canInterrupt: (() -> Bool) = { false }
    var activity: (() -> Void)?
    private var hovering = false
    let greeting = PetGreeting(), notices = PetNoticeQueue()
    var noticeShown: ((String) -> Void)?, openLetter: ((String) -> Void)?
    private(set) var dock: PetDockState?
    private(set) var peeked = false
    var peekDirection: String { dock?.edge.rawValue ?? "right" }
    private(set) var autoDock = UserDefaults.standard.object(forKey: "fish.pet.autoDock") == nil || UserDefaults.standard.bool(forKey: "fish.pet.autoDock")
    private var returnAt = Date.distantFuture, greetingUntil = Date.distantPast, activeNotice: [String: Any]?
    private(set) var sizeName: String
    var visible: Bool { panel.isVisible }
    let sizes: [String: CGFloat] = ["small": 180, "medium": 220, "large": 270]
    override init() {
        sizeName = UserDefaults.standard.string(forKey: "fish.pet.size") ?? "medium"
        panel = PetPanel(contentRect: NSRect(x: 0, y: 0, width: 220, height: 280), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        sprite = PetVideoView(frame: NSRect(x: 0, y: 30, width: 220, height: 247.5)); super.init()
        panel.title = "大肥鱼 · 小鲸鱼"; panel.backgroundColor = .clear; panel.isOpaque = false; panel.hasShadow = false; panel.level = .floating; panel.hidesOnDeactivate = false; panel.isReleasedWhenClosed = false; panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 220, height: 280)); panel.contentView = root; root.addSubview(sprite)
        label.alignment = .center; label.font = .systemFont(ofSize: 10, weight: .medium); label.textColor = NSColor(calibratedRed: 0.32, green: 0.43, blue: 0.59, alpha: 1); label.drawsBackground = true; label.backgroundColor = NSColor.white.withAlphaComponent(0.92); label.wantsLayer = true; label.layer?.cornerRadius = 11; label.layer?.masksToBounds = true; root.addSubview(label)
        popover.contentViewController = chat; popover.behavior = .transient; popover.animates = false; popover.contentSize = NSSize(width: 330, height: 338)
        chat.submit = { [weak self] text in self?.send?(text) }
        chat.close = { [weak self] in self?.activity?(); self?.popover.performClose(nil) }
        chat.openFish = { [weak self] in self?.popover.performClose(nil); self?.open?() }
        chat.openInbox = { [weak self] in self?.popover.performClose(nil); self?.inbox?() }
        greeting.open = { [weak self] in self?.openGreeting() }; greeting.dismiss = { [weak self] in self?.returnAt = Date().addingTimeInterval(2) }
        sprite.tapped = { [weak self] head, focus in guard let self = self else { return }; self.expandFromDock(); let pose = self.behavior.tap(head: head, now: Date().timeIntervalSince1970); self.tick(); self.presentChat(pose.caption, focus: focus) }
        sprite.dragBegan = { [weak self] in guard let self = self else { return }; self.activity?(); self.popover.performClose(nil); self.greeting.hide(); self.expandFromDock(); self.dock = nil; self.saveDock(); self.behavior.beginDrag(); self.tick() }
        sprite.dragEnded = { [weak self] in self?.activity?(); self?.behavior.endDrag(now: Date().timeIntervalSince1970); self?.settleAfterDrag(); self?.tick() }
        sprite.menuBuilder = { [weak self] in self?.menu() ?? NSMenu() }
        sprite.hoverChanged = { [weak self] value in self?.hovering = value; self?.tick() }
        setSize(sizeName, persist: false)
        if let saved = UserDefaults.standard.string(forKey: "fish.pet.position") { panel.setFrameOrigin(NSPointFromString(saved)); clampAndSave() } else { resetPosition() }
        if let data = UserDefaults.standard.data(forKey: "fish.pet.dock"), let saved = try? JSONDecoder().decode(PetDockState.self, from: data) { dock = saved; applyPeek() }
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(screensChanged), name: NSWorkspace.didWakeNotification, object: nil)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(motionChanged), name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(screensChanged), name: NSApplication.didChangeScreenParametersNotification, object: nil)
        if UserDefaults.standard.object(forKey: "fish.pet.visible") == nil || UserDefaults.standard.bool(forKey: "fish.pet.visible") { show() }
    }
    func update(_ snapshot: [String: Any]) {
        behavior.update(state: snapshot["state"] as? String ?? "offline", caption: snapshot["label"] as? String ?? "鱼塘暂时离线", unread: snapshot["unread"] as? Int ?? 0, now: Date().timeIntervalSince1970)
        if let ids = snapshot["alert_ids"] as? [String] { notices.retain(ids: Set(ids)) }
        if let notice = snapshot["notice"] as? [String: Any] { notices.append(notice, now: Date()) }; tick()
    }
    func receiveChat(status: String, text: String) { chat.receive(status: status, message: text); if status == "complete" { behavior.perform("happy", caption: "回爹的话，收到。", now: Date().timeIntervalSince1970) }; tick() }
    func presentChat(_ message: String? = nil, focus: Bool = true) {
        activity?()
        if !visible { show() }; expandFromDock(); greeting.hide(); chat.loadViewIfNeeded()
        if let message = message, !chat.waiting { chat.text.string = message; chat.status.stringValue = "摸摸她，也可以直接聊两句" }
        popover.show(relativeTo: NSRect(x: 12, y: 20, width: sprite.bounds.width - 24, height: sprite.bounds.height - 30), of: sprite, preferredEdge: .minX)
        if focus { NSApp.activate(ignoringOtherApps: true); popover.contentViewController?.view.window?.makeKey(); chat.focusInput() }
    }
    func tick() {
        guard visible else { return }
        if !canInterrupt() && greeting.visible && activeNotice?["id"] != nil { greeting.hide(); activeNotice = nil; returnAt = Date().addingTimeInterval(2) }
        if !behavior.dragging && !chat.waiting && !popover.isShown && !greeting.visible, let notice = notices.take(now: Date(), allowed: canInterrupt()) { presentGreeting(notice) }
        if greeting.visible && Date() > greetingUntil && !greeting.hovered { greeting.hide(); returnAt = Date().addingTimeInterval(2) }
        if dock != nil && !peeked && Date() > returnAt && !hovering && !greeting.visible && !popover.isShown && !chat.waiting && !behavior.dragging { applyPeek() }
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        let pose = behavior.pose(now: Date().timeIntervalSince1970, hour: calendar.component(.hour, from: Date())); sprite.play(peeked ? "idle" : pose.animation)
        label.stringValue = pose.caption; label.isHidden = peeked || pose.caption.isEmpty || (!hovering && !behavior.busy && behavior.unread <= 0 && !behavior.dragging)
        label.frame = NSRect(x: 5, y: 4, width: panel.frame.width - 10, height: 23)
    }
    func show() { panel.orderFrontRegardless(); sprite.setActive(true); UserDefaults.standard.set(true, forKey: "fish.pet.visible"); visibilityChanged?(); tick(); if timer == nil { let t = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in self?.tick() }; timer = t; RunLoop.main.add(t, forMode: .common) } }
    @objc func hide() { popover.performClose(nil); greeting.hide(); panel.orderOut(nil); sprite.setActive(false); timer?.invalidate(); timer = nil; UserDefaults.standard.set(false, forKey: "fish.pet.visible"); visibilityChanged?() }
    func toggle() { visible ? hide() : show() }
    @objc func openFish() { open?() }
    @objc func openInbox() { inbox?() }
    @objc func quickChat() { presentChat(focus: true) }
    @objc func chooseAction(_ sender: NSMenuItem) { guard let action = sender.representedObject as? String else { return }; if action.hasPrefix("size:") { setSize(String(action.dropFirst(5))); return }; if action.hasPrefix("dock:"), let edge = PetEdge(rawValue: String(action.dropFirst(5))) { dockAt(edge); return }; perform(action) }
    func perform(_ action: String) { guard sprite.clips[action] != nil else { return }; expandFromDock(); behavior.perform(action, now: Date().timeIntervalSince1970, duration: sprite.clips[action]?.duration ?? 10); sprite.bounce(); tick() }
    func setSize(_ requested: String, persist: Bool = true) {
        sizeName = sizes[requested] == nil ? "medium" : requested; let width = sizes[sizeName]!, height = width * 720 / 640
        panel.setContentSize(NSSize(width: width, height: height + 30)); sprite.frame = NSRect(x: 0, y: 30, width: width, height: height)
        if persist { UserDefaults.standard.set(sizeName, forKey: "fish.pet.size"); if dock != nil && peeked { applyPeek() } else { clampAndSave() }; visibilityChanged?() }
    }
    @objc func resetPosition() { dock = nil; saveDock(); peeked = false; setFullGeometry(); let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1000, height: 800); panel.setFrameOrigin(NSPoint(x: screen.maxX - panel.frame.width - 26, y: screen.minY + 26)); clampAndSave() }
    @objc func screensChanged() { if dock != nil && peeked { applyPeek() } else { clampAndSave() } }
    @objc func motionChanged() { sprite.refreshMotionPreference() }
    func clampAndSave() {
        if peeked { return }
        guard let fallback = NSScreen.main else { return }
        let screen = NSScreen.screens.max(by: { $0.visibleFrame.intersection(panel.frame).width * $0.visibleFrame.intersection(panel.frame).height < $1.visibleFrame.intersection(panel.frame).width * $1.visibleFrame.intersection(panel.frame).height })?.visibleFrame ?? fallback.visibleFrame
        panel.setFrameOrigin(NSPoint(x: min(max(panel.frame.minX, screen.minX), screen.maxX - panel.frame.width), y: min(max(panel.frame.minY, screen.minY), screen.maxY - panel.frame.height))); UserDefaults.standard.set(NSStringFromPoint(panel.frame.origin), forKey: "fish.pet.position")
    }
    private func screens() -> [PetScreen] { NSScreen.screens.map { screen in PetScreen(id: (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.stringValue ?? "main", frame: screen.frame, visible: screen.visibleFrame) } }
    private func saveDock() {
        if let dock = dock, let data = try? JSONEncoder().encode(dock) { UserDefaults.standard.set(data, forKey: "fish.pet.dock") } else { UserDefaults.standard.removeObject(forKey: "fish.pet.dock") }
    }
    private func setFullGeometry() {
        let width = sizes[sizeName]!, height = width * 720 / 640
        panel.setContentSize(NSSize(width: width, height: height + 30)); sprite.frame = NSRect(x: 0, y: 30, width: width, height: height); sprite.setPeek(nil, width: width)
    }
    private func settleAfterDrag() {
        if autoDock, let found = PetDockGeometry.nearby(frame: panel.frame, screens: screens()) { dock = found; applyPeek() }
        else { dock = nil; saveDock(); clampAndSave(); visibilityChanged?() }
    }
    func dockAt(_ edge: PetEdge) {
        let all = screens(); guard let screen = PetDockGeometry.screen(for: panel.frame, screens: all) else { return }
        let along = edge == .left || edge == .right ? (panel.frame.midY - screen.visible.minY) / screen.visible.height : (panel.frame.midX - screen.visible.minX) / screen.visible.width
        dock = PetDockState(edge: edge, screen: screen.id, anchor: min(max(Double(along), 0), 1)); applyPeek(); if !visible { show() }
    }
    private func applyPeek() {
        guard let state = dock, let target = PetDockGeometry.frame(state, width: sizes[sizeName]!, screens: screens(), expanded: false) else { return }
        let all = screens(); if let screen = all.first(where: {$0.id == state.screen}), !PetDockGeometry.external(state.edge, screen: screen, at: CGPoint(x: target.midX, y: target.midY), screens: all) { dock = nil; saveDock(); peeked = false; setFullGeometry(); clampAndSave(); return }
        popover.performClose(nil); peeked = true
        panel.setFrame(target, display: true); sprite.frame = CGRect(origin: .zero, size: target.size); sprite.setPeek(state.edge, width: sizes[sizeName]!); label.isHidden = true
        saveDock(); visibilityChanged?(); if visible { sprite.play("idle") }
    }
    func expandFromDock() {
        returnAt = Date().addingTimeInterval(20)
        guard peeked, let state = dock, let target = PetDockGeometry.frame(state, width: sizes[sizeName]!, screens: screens(), expanded: true) else { return }
        peeked = false; setFullGeometry(); panel.setFrame(target, display: true); visibilityChanged?()
    }
    @objc func togglePeek() { if peeked { expandFromDock() } else if dock != nil { applyPeek() } else { dockAt(.right) } }
    @objc func toggleAutoDock() {
        autoDock.toggle(); UserDefaults.standard.set(autoDock, forKey: "fish.pet.autoDock")
        if !autoDock { expandFromDock(); dock = nil; saveDock() } else { settleAfterDrag() }; visibilityChanged?()
    }
    @objc func previewGreeting() { presentGreeting(["kind":"preview","text":"爹？我从边边钻出来啦。小鲸鱼冒泡成功。"] ) }
    private func presentGreeting(_ notice: [String: Any]) {
        if !visible { show() }; expandFromDock(); activeNotice = notice
        let message = notice["text"] as? String ?? "爹，我来冒个泡。", kind = notice["kind"] as? String ?? "greeting"
        behavior.perform("greeting", caption: "爹，看这里。", now: Date().timeIntervalSince1970)
        greeting.show(message: message, kind: kind, near: panel.frame, screens: screens()); greetingUntil = Date().addingTimeInterval(18); returnAt = Date().addingTimeInterval(22)
        if let id = notice["id"] as? String { noticeShown?(id) }
    }
    private func openGreeting() {
        greeting.hide(); returnAt = Date().addingTimeInterval(20)
        if activeNotice?["kind"] as? String == "balance" { NSWorkspace.shared.open(URL(string: "https://platform.deepseek.com")!); return }
        if let id = activeNotice?["id"] as? String { openLetter?(id) } else { presentChat(focus: true) }
    }
    func menu() -> NSMenu {
        let menu = NSMenu()
        for (title, action) in [("和她聊两句", #selector(quickChat)), ("打开完整聊天", #selector(openFish)), ("看看鱼的来信", #selector(openInbox))] { let item = menu.addItem(withTitle: title, action: action, keyEquivalent: ""); item.target = self }
        menu.addItem(.separator())
        for (title, name) in [("摸摸头", "tickle"), ("戳一下", "shy"), ("喂口白饭", "rice"), ("伸懒腰", "stretch"), ("尾巴拍拍", "tail"), ("打个瞌睡", "sleep"), ("挥挥手", "greeting")] { let item = menu.addItem(withTitle: title, action: #selector(chooseAction(_:)), keyEquivalent: ""); item.target = self; item.representedObject = name }
        menu.addItem(.separator())
        let dockItem = menu.addItem(withTitle: "靠边自动探头", action: #selector(toggleAutoDock), keyEquivalent: ""); dockItem.target = self; dockItem.state = autoDock ? .on : .off
        let edges = NSMenu()
        for (title, edge) in [("靠左探头", PetEdge.left), ("靠右探头", .right), ("从上面探头", .top), ("从下面探头", .bottom)] { let item = edges.addItem(withTitle: title, action: #selector(chooseAction(_:)), keyEquivalent: ""); item.target = self; item.representedObject = "dock:" + edge.rawValue }
        let edgeItem = menu.addItem(withTitle: "探头位置", action: nil, keyEquivalent: ""); edgeItem.submenu = edges
        for (title, action) in [(peeked ? "出来晃晃" : "回边边待着", #selector(togglePeek)), ("预览招呼气泡", #selector(previewGreeting))] { let item = menu.addItem(withTitle: title, action: action, keyEquivalent: ""); item.target = self }
        let sizesMenu = NSMenu()
        for (title, name) in [("小只", "small"), ("正常", "medium"), ("大只", "large")] { let item = sizesMenu.addItem(withTitle: title, action: #selector(chooseAction(_:)), keyEquivalent: ""); item.target = self; item.representedObject = "size:" + name; item.state = sizeName == name ? .on : .off }
        let sizeItem = menu.addItem(withTitle: "小鲸鱼大小", action: nil, keyEquivalent: ""); sizeItem.submenu = sizesMenu
        for (title, action) in [("恢复位置", #selector(resetPosition)), ("收起小鲸鱼", #selector(hide))] { let item = menu.addItem(withTitle: title, action: action, keyEquivalent: ""); item.target = self }; return menu
    }
}
