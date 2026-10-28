import Foundation

struct PetPose: Equatable { var animation: String; var caption: String }

/// Local behaviour. Only an explicit chat submission requests the model.
final class PetBehavior {
    private(set) var runtime = "idle", runtimeCaption = "在鱼塘待着呢", unread = -1
    private(set) var dragging = false
    private var action: PetPose?, actionUntil: TimeInterval = 0, nextIdle: TimeInterval
    private var lastTap: TimeInterval = 0, taps = 0, idleIndex = 0
    let idleActions = ["look", "stretch", "yawn", "rice", "tail"]
    var busy: Bool { ["thinking", "working", "surfing"].contains(runtime) }
    init(now: TimeInterval = Date().timeIntervalSince1970) { nextIdle = now + 35 }
    @discardableResult func update(state: String, caption: String, unread count: Int, now: TimeInterval) -> Bool {
        let wasBusy = busy, newLetter = unread >= 0 && count > unread
        runtime = state; runtimeCaption = caption; unread = count
        if wasBusy && !busy { perform("celebrate", caption: "说完啦。", now: now, duration: 5) }
        if newLetter && !busy { perform("greeting", caption: "爹，有个东西想给你看。", now: now) }
        return newLetter
    }
    func perform(_ animation: String, caption: String = "", now: TimeInterval, duration: TimeInterval = 10) {
        action = PetPose(animation: animation, caption: caption); actionUntil = now + duration; nextIdle = actionUntil + 30
    }
    @discardableResult func tap(head: Bool, now: TimeInterval) -> PetPose {
        taps = now - lastTap < 2 ? taps + 1 : 1; lastTap = now
        let pose: PetPose
        if taps >= 4 { pose = PetPose(animation: "grumpy", caption: "等会儿，头要被你摸秃了。") }
        else if head { pose = PetPose(animation: taps % 2 == 1 ? "tickle" : "shy", caption: taps % 2 == 1 ? "嘿嘿，爹。" : "好了好了，摸到啦。") }
        else { pose = PetPose(animation: taps % 2 == 1 ? "happy" : "greeting", caption: "在呢，怎么啦？") }
        perform(pose.animation, caption: pose.caption, now: now); return pose
    }
    func beginDrag() { dragging = true }
    func endDrag(now: TimeInterval) { dragging = false; perform("shy", caption: "被爹拎到这里了。", now: now, duration: 5) }
    func pose(now: TimeInterval, hour: Int) -> PetPose {
        if dragging { return PetPose(animation: "drag", caption: "诶——轻点拎！") }
        if let action = action, now < actionUntil { return action }
        action = nil
        if busy { return PetPose(animation: runtime == "thinking" ? "thinking" : "working", caption: runtimeCaption) }
        if runtime == "offline" { return PetPose(animation: "look", caption: runtimeCaption) }
        if hour >= 23 || hour < 7 { return PetPose(animation: "sleep", caption: "小声点，鱼睡着了。") }
        if now >= nextIdle { let name = idleActions[idleIndex % idleActions.count]; idleIndex += 1; perform(name, now: now); return action! }
        return PetPose(animation: "idle", caption: unread > 0 ? "有来信，等爹来看。" : "在鱼塘待着呢")
    }
}
