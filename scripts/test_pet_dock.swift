import Foundation
import CoreGraphics
@main struct Tests {
    static func main() {
        let right=PetScreen(id:"main",frame:CGRect(x:0,y:0,width:1440,height:900),visible:CGRect(x:0,y:60,width:1440,height:815))
        let left=PetScreen(id:"left",frame:CGRect(x:-1920,y:0,width:1920,height:1080),visible:CGRect(x:-1920,y:0,width:1920,height:1055))
        let size=CGSize(width:220,height:277.5)
        let rightDock=PetDockGeometry.nearby(frame:CGRect(origin:CGPoint(x:1220,y:300),size:size),screens:[right])!
        assert(rightDock.edge == .right)
        assert(PetDockGeometry.nearby(frame:CGRect(origin:CGPoint(x:500,y:300),size:size),screens:[right]) == nil)
        assert(PetDockGeometry.nearby(frame:CGRect(origin:CGPoint(x:0,y:300),size:size),screens:[right,left]) == nil,"A seam between monitors must remain traversable")
        let leftDock=PetDockState(edge:.left,screen:"left",anchor:0.5)
        for edge in PetEdge.allCases {
            let state=PetDockState(edge:edge,screen:"left",anchor:0.99)
            let peek=PetDockGeometry.frame(state,width:220,screens:[right,left],expanded:false)!
            let full=PetDockGeometry.frame(state,width:220,screens:[right,left],expanded:true)!
            assert(left.frame.contains(peek));assert(left.visible.contains(full));assert(full.width==220)
        }
        assert(PetDockGeometry.frame(leftDock,width:220,screens:[right,left],expanded:false)!.minX == -1920)
        let now=Date(timeIntervalSince1970:100000),formatter=ISO8601DateFormatter();formatter.formatOptions=[.withInternetDateTime,.withFractionalSeconds]
        let queue=PetNoticeQueue(),notice:[String:Any]=["id":"one","text":"爹，我来冒个泡。","sent_at":formatter.string(from:now)]
        queue.append(notice,now:now);queue.append(notice,now:now);assert(queue.take()?["id"] as? String=="one");assert(queue.take()==nil)
        queue.append(notice,now:now);assert(!queue.hasPending)
        queue.append(["id":"old","text":"old","sent_at":formatter.string(from:now.addingTimeInterval(-3600))],now:now);assert(!queue.hasPending)
        print("Pet docking: body bounds, shared seams, negative-coordinate screens, safe expansion and once-only notice queue passed")
    }
}
