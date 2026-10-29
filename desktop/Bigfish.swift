import Cocoa
import WebKit
import UserNotifications

final class FishDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, UNUserNotificationCenterDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var statusItem: NSStatusItem!
    let base = URL(string: "http://127.0.0.1:9120")!
    let network = URLSession(configuration: .ephemeral)
    var timer: Timer?
    var pet: FloatingPet!
    var petTimer: Timer?, petPolling = false
    var loaded = false, polling = false, starting = false
    var pageNeedsRecovery = false, healthChecking = false, lastRecovery = Date.distantPast
    var recoveryTimer: Timer?
    var recoveryOverlay: NSView?, recoveryAttempts = 0
    var pendingLetter: String?
    var pendingPanel = false, pendingSettings = false
    var pendingPetText: String?, uiReady = false
    var root: String { Bundle.main.object(forInfoDictionaryKey: "FishProjectRoot") as! String }
    var notifying = Set<String>()
    var petNotifying = Set<String>()
    var interruptions = PetInterruptionGate(), lastPresenceSent = Date.distantPast

    func applicationWillFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        if NSRunningApplication.runningApplications(withBundleIdentifier: "local.aifish.desktop").contains(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }) { NSApp.terminate(nil); return }
        makeMenus()
        web = makeWebView()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1260, height: 840), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "大肥鱼"; window.minSize = NSSize(width: 520, height: 420); window.center(); window.setFrameAutosaveName("BigfishMainWindow")
        window.isReleasedWhenClosed = false; window.delegate = self
        let host = NSView(frame: NSRect(origin: .zero, size: window.contentLayoutRect.size))
        window.contentView = host; installWebView(in: host)
        pet = FloatingPet()
        pet.open = { [weak self] in self?.showWindow(); self?.web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:chat'))") }
        pet.inbox = { [weak self] in self?.showInbox() }
        pet.visibilityChanged = { [weak self] in self?.publishPetStatus() }
        pet.openLetter = { [weak self] id in self?.showWindow(letter: id) }
        pet.noticeShown = { [weak self] id in self?.acknowledgePet(id) }
        pet.canInterrupt = { [weak self] in self?.interruptions.allows(now: Date()) ?? false }
        pet.activity = { [weak self] in self?.recordActivity() }
        pet.send = { [weak self] text in self?.sendPet(text) }
        petTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.pollPet() }
        web.loadHTMLString("<html><meta charset='utf-8'><body style='background:#f7f8fa;color:#5b6d89;font:16px -apple-system;text-align:center;padding:27vh 20px'>大肥鱼正在醒来…<p style='font-size:12px;color:#909db1'>启动本地鱼塘，稍等一下。</p></body></html>", baseURL: nil)
        if !CommandLine.arguments.contains("--background") { showWindow() }
        network.dataTask(with: desktopRequest(base)) { _, response, _ in
            DispatchQueue.main.async { if (response as? HTTPURLResponse)?.statusCode == 200 { self.connect() } else { self.startBackend() } }
        }.resume()
        timer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in self?.pollInbox() }
        recoveryTimer = Timer.scheduledTimer(withTimeInterval: 20, repeats: true) { [weak self] _ in
            guard let self = self, self.window.isVisible, NSApp.isActive else { return }; self.checkPage()
        }
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(wokeUp), name: NSWorkspace.didWakeNotification, object: nil)
    }
    func desktopRequest(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        if localURL(url), let key = try? String(contentsOfFile: NSHomeDirectory() + "/Library/Application Support/Bigfish/desktop-access.key", encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) { request.setValue(key, forHTTPHeaderField: "X-Fish-Desktop") }
        return request
    }
    func makeWebView() -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.userContentController.add(self, name: "fish")
        config.userContentController.addUserScript(WKUserScript(source: "window.__FISH_DESKTOP__ = true;", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: .zero, configuration: config); view.navigationDelegate = self; view.uiDelegate = self; return view
    }
    func installWebView(in host: NSView) {
        web.frame = host.bounds; web.autoresizingMask = [.width, .height]
        host.addSubview(web); host.needsLayout = true
        window.makeFirstResponder(web)
    }
    func makeMenus() {
        let main = NSMenu(), appItem = NSMenuItem(), appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于大肥鱼", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(withTitle: "打开鱼塘", action: #selector(showFromMenu), keyEquivalent: "0")
        appMenu.addItem(withTitle: "Hermes 面板", action: #selector(showHermes), keyEquivalent: "2")
        appMenu.addItem(withTitle: "设置…", action: #selector(showSettings), keyEquivalent: ",")
        appMenu.addItem(withTitle: "鱼的来信", action: #selector(showInbox), keyEquivalent: "i")
        appMenu.addItem(withTitle: "显示 / 收起小鲸鱼", action: #selector(togglePet), keyEquivalent: "p")
        appMenu.addItem(withTitle: "恢复小鲸鱼位置", action: #selector(resetPet), keyEquivalent: "")
        appMenu.addItem(withTitle: "靠左探头", action: #selector(dockPetLeft), keyEquivalent: "")
        appMenu.addItem(withTitle: "靠右探头", action: #selector(dockPetRight), keyEquivalent: "")
        appMenu.addItem(withTitle: "预览招呼气泡", action: #selector(previewPetGreeting), keyEquivalent: "")
        appMenu.addItem(withTitle: "重新载入鱼塘", action: #selector(reloadFish), keyEquivalent: "r")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "允许来信通知…", action: #selector(requestNotifications), keyEquivalent: "")
        appMenu.addItem(withTitle: "通知设置…", action: #selector(notificationSettings), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏大肥鱼", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "退出大肥鱼", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; main.addItem(appItem)
        let editItem = NSMenuItem(), edit = NSMenu(title: "编辑")
        for (title, action, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] { edit.addItem(withTitle: title, action: Selector(action), keyEquivalent: key) }
        editItem.submenu = edit; main.addItem(editItem); NSApp.mainMenu = main
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        let image = NSImage(contentsOf: Bundle.main.url(forResource: "character", withExtension: "png")!)
        image?.size = NSSize(width: 21, height: 21); statusItem.button?.image = image; statusItem.button?.toolTip = "大肥鱼 · 在后台逛逛"
        let menu = NSMenu(); menu.addItem(withTitle: "打开大肥鱼", action: #selector(showFromMenu), keyEquivalent: ""); menu.addItem(withTitle: "鱼的来信", action: #selector(showInbox), keyEquivalent: ""); menu.addItem(withTitle: "通知设置…", action: #selector(notificationSettings), keyEquivalent: ""); menu.addItem(.separator()); menu.addItem(withTitle: "退出", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
        for item in menu.items where item.action != #selector(NSApplication.terminate(_:)) { item.target = self }
        let petItem = NSMenuItem(title: "显示 / 收起小鲸鱼", action: #selector(togglePet), keyEquivalent: ""); petItem.target = self; menu.insertItem(petItem, at: 2)
        for item in appMenu.items where [#selector(about), #selector(showFromMenu), #selector(showInbox), #selector(showHermes), #selector(showSettings), #selector(requestNotifications), #selector(notificationSettings)].contains(item.action) { item.target = self }
        statusItem.menu = menu
        for item in appMenu.items where [#selector(togglePet), #selector(resetPet), #selector(dockPetLeft), #selector(dockPetRight), #selector(previewPetGreeting), #selector(reloadFish)].contains(item.action) { item.target = self }
    }
    @objc func togglePet() { pet?.toggle(); pollPet() }
    @objc func resetPet() { pet?.resetPosition(); pet?.show() }
    @objc func dockPetLeft() { pet?.dockAt(.left) }
    @objc func dockPetRight() { pet?.dockAt(.right) }
    @objc func previewPetGreeting() { pet?.previewGreeting() }
    @objc func reloadFish() { lastRecovery = .distantPast; recoveryAttempts = 0; pageNeedsRecovery = true; recoverPage(rebuild: true) }
    func sendPet(_ text: String) {
        guard uiReady, !pageNeedsRecovery else {
            pendingPetText = text; pet.receiveChat(status: "thinking", text: "正在唤醒鱼塘，稍等一下。")
            recoverPage()
            DispatchQueue.main.asyncAfter(deadline: .now() + 20) { [weak self] in
                guard let self = self, self.pendingPetText != nil else { return }
                self.pendingPetText = nil; self.pet.receiveChat(status: "error", text: "鱼塘还没醒过来，这句暂时没发。文字保留着，可以稍后再试。")
            }; return
        }
        guard let data = try? JSONSerialization.data(withJSONObject: ["text": text]), let value = String(data: data, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:pet-prompt',{detail:\(value)}))") { _, error in
            if error != nil { DispatchQueue.main.async { self.pet.receiveChat(status: "error", text: "鱼塘连接中断了。请稍后再试，这句不会自动重复发送。") } }
        }
    }
    func publishPetStatus() { web?.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:pet-status',{detail:{visible:\(pet?.visible == true ? "true" : "false"),size:'\(pet?.sizeName ?? "medium")',peeked:\(pet?.peeked == true ? "true" : "false"),edge:'\(pet?.peekDirection ?? "right")',autoDock:\(pet?.autoDock == true ? "true" : "false")}}))") }
    func pollPet() {
        guard pet?.visible == true, !petPolling else { return }; petPolling = true
        network.dataTask(with: desktopRequest(base.appendingPathComponent("api/companion"))) { data, response, _ in
            if (response as? HTTPURLResponse)?.statusCode == 401 { self.network.dataTask(with: self.desktopRequest(self.base)) { _, _, _ in DispatchQueue.main.async { self.petPolling = false } }.resume(); return }
            let snapshot = data.flatMap { (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any] }
            DispatchQueue.main.async {
                self.petPolling = false
                self.interruptions.update(allowed: snapshot?["can_interrupt"] as? Bool ?? false, minutes: snapshot?["activity_minutes"] as? Double, now: Date())
                self.pet?.update(snapshot ?? ["animation": "idle", "label": "鱼塘暂时离线"])
            }
        }.resume()
    }
    @objc func showHermes() { pendingPanel = true; showWindow(); openPendingPanel() }
    func openPendingPanel() { if pendingPanel && uiReady { pendingPanel = false; web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:hermes'))") } }
    @objc func showSettings() { pendingSettings = true; if window != nil { showWindow(); openPendingSettings() } }
    func openPendingSettings() { if pendingSettings && uiReady { pendingSettings = false; web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:settings'))") } }
    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls where url.scheme == "bigfish" {
            if url.host == "settings" { showSettings() }
            if url.host == "hermes" { pendingPanel = true; if window != nil { showWindow(); openPendingPanel() } }
        }
    }
    @objc func showFromMenu() { showWindow() }
    func showWindow(letter: String? = nil) {
        recordActivity()
        if let letter = letter { pendingLetter = letter }
        window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        web.needsLayout = true; web.needsDisplay = true
        if pageNeedsRecovery { recoverPage() } else { checkPage() }
        if loaded { openPendingLetter() }
    }
    @objc func showInbox() {
        showWindow()
        if loaded { web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:inbox'))") }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    @objc func about() {
        NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "大肥鱼", .applicationVersion: "1.6", .credits: NSAttributedString(string: "你的本地 AI 冲浪搭子\n\n社区鲸鱼娘图标：可以叫我云大人 / 雾雪 · kiriyuki.com\n形象基于 ZipZipPipe 与 上善无形\n图标：github.com/Loping151/dsh-nekowhale-stickers\n动画：github.com/PC2005-cloud/dsh-pet\nCC BY-NC-SA 4.0 · 个人非商业使用 · 非 DeepSeek 官方应用")])
    }
    @objc func requestNotifications() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            if settings.authorizationStatus == .denied { DispatchQueue.main.async { self.publishNotificationStatus(); self.notificationSettings() }; return }
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge]) { _, _ in DispatchQueue.main.async { self.publishNotificationStatus(); self.pollInbox() } }
        }
    }
    func publishNotificationStatus() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let status = settings.authorizationStatus.rawValue
            DispatchQueue.main.async { self.web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('fish:notification-status', {detail:{status:\(status)}}))") }
        }
    }
    @objc func notificationSettings() { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!) }
    @objc func wokeUp() { pollInbox(); checkPage(); if !loaded && !pageNeedsRecovery { startBackend() } }
    func applicationDidBecomeActive(_ notification: Notification) { if window?.isVisible == true { checkPage() } }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        pageNeedsRecovery = true; loaded = false; uiReady = false; healthChecking = false
        if window.isVisible && NSApp.isActive { recoverPage() }
    }
    func recoverPage(rebuild: Bool = false) {
        guard Date().timeIntervalSince(lastRecovery) > 8 else { return }
        if recoveryAttempts >= 3 && Date().timeIntervalSince(lastRecovery) < 120 { return }
        if Date().timeIntervalSince(lastRecovery) >= 120 { recoveryAttempts = 0 }
        recoveryAttempts += 1
        lastRecovery = Date(); loaded = false; uiReady = false; pageNeedsRecovery = true
        healthChecking = false; recoveryProbe = UUID().uuidString
        if rebuild || recoveryAttempts > 1 {
            let host = window.contentView!
            web.stopLoading(); web.configuration.userContentController.removeScriptMessageHandler(forName: "fish"); web.navigationDelegate = nil; web.uiDelegate = nil
            recoveryOverlay?.removeFromSuperview(); recoveryOverlay = nil
            web.removeFromSuperview(); web = makeWebView(); installWebView(in: host)
        }
        showRecoveryOverlay()
        web.load(desktopRequest(base))
        let attempt = lastRecovery
        DispatchQueue.main.asyncAfter(deadline: .now() + 16) { [weak self] in
            guard let self = self, self.lastRecovery == attempt, !self.uiReady, (self.window.isVisible && NSApp.isActive || self.pendingPetText != nil) else { return }
            self.recoverPage(rebuild: true)
        }
    }
    func showRecoveryOverlay() {
        guard recoveryOverlay == nil else { return }
        let box = NSVisualEffectView(frame: NSRect(x: max(0, web.bounds.midX - 185), y: max(0, web.bounds.midY - 55), width: 370, height: 110)); box.material = .windowBackground; box.state = .active; box.wantsLayer = true; box.layer?.cornerRadius = 15; box.autoresizingMask = [.minXMargin,.maxXMargin,.minYMargin,.maxYMargin]
        let label = NSTextField(wrappingLabelWithString: "鱼塘正在重新连上…\n未发送的文字会留着。"); label.alignment = .center; label.font = .systemFont(ofSize: 13); label.textColor = .secondaryLabelColor; label.frame = NSRect(x: 20, y: 48, width: 330, height: 44); box.addSubview(label)
        let button = NSButton(title: "重新载入", target: self, action: #selector(reloadFish)); button.bezelStyle = .rounded; button.frame = NSRect(x: 130, y: 12, width: 110, height: 26); box.addSubview(button); web.addSubview(box); recoveryOverlay = box
    }
    func checkPage() {
        guard !healthChecking, !starting, Date().timeIntervalSince(lastRecovery) > 8 else { return }
        if pageNeedsRecovery { recoverPage(); return }
        guard loaded else { return }; healthChecking = true
        let probe = UUID().uuidString
        recoveryProbe = probe
        web.evaluateJavaScript("Boolean(window.__FISH_UI_READY__ && document.getElementById('root')?.childElementCount)") { result, error in
            DispatchQueue.main.async {
                guard self.recoveryProbe == probe, self.healthChecking else { return }; self.healthChecking = false
                if error != nil || result as? Bool != true { self.pageNeedsRecovery = true; self.recoverPage(rebuild: error != nil) }
            }
        }
        // A suspended or crashed WebKit renderer can fail to answer evaluation at all.
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in
            guard let self = self, self.recoveryProbe == probe, self.healthChecking else { return }
            self.healthChecking = false; self.pageNeedsRecovery = true; self.recoverPage(rebuild: true)
        }
    }
    var recoveryProbe = ""
    func startBackend() {
        guard !starting else { return }; starting = true
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env"); process.arguments = ["python3", self.root + "/scripts/ui.py", "--no-open"]
            process.environment = ProcessInfo.processInfo.environment.merging(["PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"]) { _, new in new }
            process.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
            let logDirectory = NSHomeDirectory() + "/Library/Logs/AI-Fish"
            try? FileManager.default.createDirectory(atPath: logDirectory, withIntermediateDirectories: true)
            let logPath = logDirectory + "/desktop-native.log"
            FileManager.default.createFile(atPath: logPath, contents: nil)
            let output = FileHandle(forWritingAtPath: logPath); process.standardOutput = output; process.standardError = output
            do { try process.run(); DispatchQueue.global().asyncAfter(deadline: .now() + 50) { if process.isRunning { process.terminate() } }; process.waitUntilExit(); try? output?.close()
                DispatchQueue.main.async { self.starting = false; if process.terminationStatus == 0 { self.connect() } else { self.startupError() } }
            } catch { DispatchQueue.main.async { self.starting = false; self.startupError() } }
        }
    }
    func startupError() {
        let alert = NSAlert(); alert.messageText = "鱼塘还没启动起来"; alert.informativeText = "可以重试。启动记录保存在项目 .setup/desktop-native.log。"; alert.addButton(withTitle: "重试"); alert.addButton(withTitle: "稍后")
        if alert.runModal() == .alertFirstButtonReturn { startBackend() }
    }
    func connect() {
        network.dataTask(with: desktopRequest(base)) { _, response, error in
            DispatchQueue.main.async { if error == nil && (response as? HTTPURLResponse)?.statusCode == 200 { self.web.load(self.desktopRequest(self.base)); UNUserNotificationCenter.current().getNotificationSettings { settings in if settings.authorizationStatus == .notDetermined { DispatchQueue.main.async { self.requestNotifications() } } }; self.pollInbox() } else { self.startupError() } }
        }.resume()
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard webView.url?.host == "127.0.0.1" else { return }; loaded = true; pageNeedsRecovery = false; openPendingLetter()
    }
    func openPendingLetter() {
        guard let id = pendingLetter, let data = try? JSONSerialization.data(withJSONObject: ["id": id]), let literal = String(data: data, encoding: .utf8) else { return }
        pendingLetter = nil; web.evaluateJavaScript("window.__FISH_PENDING_LETTER__ = \(literal).id; window.dispatchEvent(new CustomEvent('fish:open-letter', {detail: \(literal)}))")
    }
    func localURL(_ url: URL) -> Bool { url.scheme == "http" && url.host == "127.0.0.1" && url.port == 9120 }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if localURL(url) || url.absoluteString == "about:blank" { decisionHandler(.allow); return }
        if navigationAction.navigationType == .linkActivated && ["http", "https"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, ["http", "https"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }; return nil
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let url = message.frameInfo.request.url, localURL(url), let body = message.body as? [String: String] else { return }
        if body["type"] == "app.folder", let folder = body["folder"], let relative = ["reports":"reports", "memory":".hermes/memories", "logs":".setup"][folder] { NSWorkspace.shared.open(URL(fileURLWithPath: root + "/" + relative)) }
        if body["type"] == "notifications.status" { publishNotificationStatus() }
        if body["type"] == "ui.presence" { recordActivity(publish: false) }
        if body["type"] == "ui.ready" { loaded = true; uiReady = true; pageNeedsRecovery = false; recoveryAttempts = 0; recoveryOverlay?.removeFromSuperview(); recoveryOverlay = nil; publishPetStatus(); openPendingPanel(); openPendingSettings(); if let text = pendingPetText { pendingPetText = nil; sendPet(text) } }
        if body["type"] == "notifications.request" { requestNotifications() }
        if body["type"] == "notifications.settings" { notificationSettings() }
        if body["type"] == "pet.status" { publishPetStatus() }
        if body["type"] == "pet.toggle" { togglePet() }
        if body["type"] == "pet.reset" { resetPet() }
        if body["type"] == "pet.chat", let status = body["status"] { pet.receiveChat(status: status, text: body["text"] ?? "") }
        if body["type"] == "pet.action", let name = body["name"] { pet.perform(name) }
        if body["type"] == "pet.size", let size = body["size"] { pet.setSize(size) }
        if body["type"] == "pet.quick-chat" { pet.quickChat() }
        if body["type"] == "pet.dock.toggle" { pet.toggleAutoDock() }
        if body["type"] == "pet.peek.toggle" { pet.togglePeek() }
        if body["type"] == "pet.greeting.preview" { pet.previewGreeting() }
    }
    func recordActivity(publish: Bool = true) {
        let now = Date(); interruptions.noteActivity(now: now)
        guard publish && now.timeIntervalSince(lastPresenceSent) > 60 else { return }; lastPresenceSent = now
        var request = desktopRequest(base.appendingPathComponent("api/presence")); request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue("studio", forHTTPHeaderField: "X-Fish-Client"); request.httpBody = Data("{}".utf8)
        network.dataTask(with: request).resume()
    }
    func pollInbox() {
        guard !polling else { return }; polling = true
        network.dataTask(with: desktopRequest(base.appendingPathComponent("api/inbox"))) { data, response, _ in
            if (response as? HTTPURLResponse)?.statusCode == 401 {
                self.network.dataTask(with: self.desktopRequest(self.base)) { _, _, _ in DispatchQueue.main.async { self.polling = false } }.resume(); return
            }
            DispatchQueue.main.async {
                self.polling = false
                guard let data = data, let snapshot = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], let messages = snapshot["messages"] as? [[String: Any]] else { return }
                let unread = snapshot["unread"] as? Int ?? 0; NSApp.dockTile.badgeLabel = unread > 0 ? String(unread) : nil
                self.interruptions.update(allowed: snapshot["can_interrupt"] as? Bool ?? false, minutes: (snapshot["settings"] as? [String: Any])?["activityMinutes"] as? Double, now: Date())
                let eligible = Set(snapshot["alert_ids"] as? [String] ?? [])
                UNUserNotificationCenter.current().getNotificationSettings { settings in
                    guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else { return }
                    DispatchQueue.main.async {
                        guard self.interruptions.allows(now: Date()), self.pet?.visible != true else { return }
                        for message in messages where message["read_at"] is NSNull && message["notified_at"] is NSNull {
                            guard let id = message["id"] as? String, let text = message["text"] as? String, let timestamp = message["sent_at"] as? String, !self.notifying.contains(id) else { continue }
                            let date = ISO8601DateFormatter(); date.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                            guard eligible.contains(id), let sent = date.date(from: timestamp), Date().timeIntervalSince(sent) >= -60, Date().timeIntervalSince(sent) < 15 * 60 else { continue }
                            let content = UNMutableNotificationContent(); content.title = "大肥鱼"; content.body = text; content.threadIdentifier = "fish-discoveries"; content.userInfo = ["letter_id": id]
                            self.notifying.insert(id)
                            UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "fish-" + id, content: content, trigger: nil)) { error in
                                if error == nil { self.acknowledge(id) }
                                DispatchQueue.main.async { self.notifying.remove(id) }
                            }
                        }
                    }
                }
            }
        }.resume()
    }
    func acknowledge(_ id: String) {
        var request = desktopRequest(base.appendingPathComponent("api/inbox/" + id)); request.httpMethod = "PUT"; request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue("studio", forHTTPHeaderField: "X-Fish-Client"); request.httpBody = Data("{\"notified\":true}".utf8)
        network.dataTask(with: request).resume()
    }
    func acknowledgePet(_ id: String) {
        guard !petNotifying.contains(id) else { return }; petNotifying.insert(id)
        var request = desktopRequest(base.appendingPathComponent("api/inbox/" + id)); request.httpMethod = "PUT"; request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue("studio", forHTTPHeaderField: "X-Fish-Client"); request.httpBody = Data("{\"pet_notified\":true,\"notified\":true}".utf8)
        network.dataTask(with: request) { _, _, _ in DispatchQueue.main.async { self.petNotifying.remove(id) } }.resume()
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let id = response.notification.request.content.userInfo["letter_id"] as? String
        DispatchQueue.main.async { self.showWindow(letter: id) }; completionHandler()
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        DispatchQueue.main.async { completionHandler(NSApp.isActive && self.window.isVisible ? [] : [.banner, .list]) }
    }
}

@main struct BigfishMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = FishDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
