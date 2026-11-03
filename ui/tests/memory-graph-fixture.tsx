import {createRoot} from 'react-dom/client'
import {useState} from 'react'
import MemoryStarMap from '../src/memory/MemoryStarMap'
import MemoryTimeline from '../src/MemoryTimeline'
import '../src/styles.css'
import '../src/responsive.css'
const pending=new Set<number>(),originalFrame=requestAnimationFrame,originalCancel=cancelAnimationFrame
let frames=0
window.requestAnimationFrame=callback=>{const id=originalFrame(time=>{pending.delete(id);frames++;callback(time)});pending.add(id);return id}
window.cancelAnimationFrame=id=>{pending.delete(id);originalCancel(id)}
setInterval(()=>{const output=document.querySelector('[data-testid="stars-diagnostics"]');if(output)output.textContent=`frames=${frames}; pending=${pending.size}; canvases=${document.querySelectorAll('.stars-stage>canvas').length}`},1000)
function visibility(){const w=window as Window&{__FISH_WINDOW_VISIBLE__?:boolean};w.__FISH_WINDOW_VISIBLE__=w.__FISH_WINDOW_VISIBLE__===false;window.dispatchEvent(new Event('fish:window-visibility'))}
function contextLoss(){const canvas=document.querySelector('.stars-stage>canvas') as HTMLCanvasElement|null;const extension=canvas?.getContext('webgl2')?.getExtension('WEBGL_lose_context');if(extension){extension.loseContext();setTimeout(()=>extension.restoreContext(),1500)}}
function Fixture(){const [view,setView]=useState('stars');return <main style={{height:'100dvh',display:'flex',flexDirection:'column',background:'#f7f9fc'}}><div className="workspace-page" style={{maxWidth:1300,margin:'0 auto',padding:30}}><p style={{fontSize:11,color:'#8c9aaa'}}>隔离验收 · 以下全部为虚构片段，不读取或修改真实记忆。</p><div className="memory-view-switch"><button onClick={()=>setView('stars')}>记忆星图</button><button onClick={()=>setView('list')}>原记录列表</button><button onClick={()=>setView('away')}>切走</button></div>{view==='stars'?<MemoryStarMap/>:view==='list'?<MemoryTimeline/>:<p>星图已卸载。</p>}<details><summary>隔离图形诊断</summary><button onClick={visibility}>模拟窗口隐藏 / 恢复</button><button onClick={contextLoss}>模拟图形丢失 / 恢复</button><output data-testid="stars-diagnostics" style={{display:'block'}}/></details></div></main>}
createRoot(document.getElementById('root')!).render(<Fixture/>);
