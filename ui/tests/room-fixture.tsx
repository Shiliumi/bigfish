import {createRoot} from 'react-dom/client'
import RoomPage from '../src/room/RoomPage'
import '../src/styles.css'
import '../src/responsive.css'
import '../src/pet.css'

const samples:object[]=[]
function sample(phase:string) {
  const button=document.querySelector('.room-character'),anchor=document.querySelector('.room-character-anchor')
  if(!button||!anchor)return
  const b=button.getBoundingClientRect(),a=anchor.getBoundingClientRect(),video=button.querySelector('video')
  samples.push({phase,active:button.matches(':active'),button:[b.x,b.y,b.width,b.height],anchor:[a.x,a.y,a.width,a.height],transform:getComputedStyle(button).transform,source:video?.getAttribute('src'),time:video?.currentTime})
  if(samples.length>40)samples.shift()
  const output=document.getElementById('regression-trace');if(output)output.textContent=JSON.stringify(samples)
}
window.addEventListener('pointerdown',event=>{if((event.target as Element).closest('.room-character')){sample('down');requestAnimationFrame(()=>sample('held'))}})
window.addEventListener('pointerup',()=>sample('up'))
const drags:object[]=[]
for(const phase of ['pointerdown','pointermove','pointerup'])window.addEventListener(phase,event=>{
  const e=event as PointerEvent;if(!(e.target as Element).matches('.room-stage>canvas'))return
  drags.push({phase,x:e.clientX,y:e.clientY,buttons:e.buttons});if(drags.length>24)drags.shift()
  const output=document.getElementById('drag-trace');if(output)output.textContent=JSON.stringify(drags)
},true)
function visibility() {
  const w=window as Window&{__FISH_WINDOW_VISIBLE__?:boolean};w.__FISH_WINDOW_VISIBLE__=w.__FISH_WINDOW_VISIBLE__===false
  window.dispatchEvent(new CustomEvent('fish:window-visibility'));document.getElementById('visibility-note')!.textContent=w.__FISH_WINDOW_VISIBLE__?'恢复显示':'已模拟隐藏'
}
function contextLoss() {
  const canvas=document.querySelector('.room-stage>canvas') as HTMLCanvasElement|null
  const extension=canvas?.getContext('webgl2')?.getExtension('WEBGL_lose_context')
  if(!extension){document.getElementById('context-note')!.textContent='此环境不提供上下文丢失扩展';return}
  extension.loseContext();setTimeout(()=>extension.restoreContext(),1200)
}
createRoot(document.getElementById('root')!).render(<main style={{height:'100dvh',display:'flex',flexDirection:'column'}}>
  <div className="workspace-page"><RoomPage onNavigate={()=>{}}/>
    <details style={{marginTop:20}}><summary>隔离测试记录（虚构状态）</summary>
      <button onClick={visibility}>模拟隐藏 / 恢复</button><span id="visibility-note"/>
      <button onClick={contextLoss}>模拟图形上下文丢失 / 恢复</button><span id="context-note"/>
      <output id="regression-trace" style={{display:'block',fontSize:10,overflowWrap:'anywhere'}}/>
      <output id="drag-trace" style={{display:'block',fontSize:10,overflowWrap:'anywhere'}}/>
    </details>
  </div>
</main>)
