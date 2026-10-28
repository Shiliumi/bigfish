import Foundation
import CoreGraphics
@main struct PeekTest {
 static func main() {
  let art=PetPeekArt(file:"test.png",width:1000,height:1000,bounds:[100,50,950,900],edge_line:850)
  let size=CGSize(width:160,height:200)
  let right=PetPeekGeometry.frame(art:art,edge:.right,in:size), scale=right.width/1000
  assert(abs(right.minX+950*scale-size.width)<0.001)
  assert(right.minY+50*scale >= -0.001 && right.minY+900*scale <= size.height+0.001)
  let left=PetPeekGeometry.frame(art:art,edge:.left,in:size)
  assert(abs(left.minX+(1000-950)*scale)<0.001)
  let top=PetPeekGeometry.frame(art:art,edge:.top,in:size)
  assert(abs(top.minY+50*(top.width/1000))<0.001)
  let bottom=PetPeekGeometry.frame(art:art,edge:.bottom,in:size)
  assert(abs(bottom.minY+850*(bottom.width/1000)-size.height)<0.001)
  print("Dedicated peek art aligns to the real screen edge; natural silhouette remains inside on other sides.")
 }
}
