import Foundation
@main struct Tests {
    static func main() {
        let pet = PetBehavior(now: 100)
        assert(!pet.update(state: "idle", caption: "idle", unread: 3, now: 100), "Old letters must not trigger a fresh greeting")
        assert(pet.pose(now: 101, hour: 13).animation == "idle")
        assert(pet.update(state: "idle", caption: "idle", unread: 4, now: 102))
        assert(pet.pose(now: 102, hour: 13).animation == "greeting")
        pet.beginDrag(); assert(pet.pose(now: 103, hour: 13).animation == "drag")
        pet.endDrag(now: 104); assert(pet.pose(now: 105, hour: 13).animation == "shy")
        pet.update(state: "thinking", caption: "thinking", unread: 4, now: 110)
        assert(pet.pose(now: 150, hour: 2).animation == "thinking", "Work wins over sleep or random idle actions")
        pet.tap(head: true, now: 151); assert(pet.pose(now: 151, hour: 13).animation == "tickle")
        assert(pet.pose(now: 162, hour: 13).animation == "thinking", "A touch reaction must return to the live task")
        pet.tap(head: true, now: 163); pet.tap(head: true, now: 164); pet.tap(head: true, now: 165); pet.tap(head: true, now: 166)
        assert(pet.pose(now: 166, hour: 13).animation == "grumpy")
        pet.update(state: "idle", caption: "idle", unread: 4, now: 180)
        assert(pet.pose(now: 200, hour: 2).animation == "sleep")
        let quiet = PetBehavior(now: 100)
        assert(quiet.pose(now: 136, hour: 13).animation == "look")
        assert(quiet.pose(now: 147, hour: 13).animation == "idle")
        assert(quiet.pose(now: 177, hour: 13).animation == "stretch")
        print("Pet behaviour: work priority, gesture expiry, dragging, idle variety, quiet sleep, no old-letter replay passed")
    }
}
