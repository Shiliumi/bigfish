import {createRoot} from 'react-dom/client'
import App from '../src/App'
import '../src/styles.css'
import '../src/responsive.css'
import '../src/pet.css'
function legacy(value:string){localStorage.setItem('fish.page',value);location.reload()}
createRoot(document.getElementById('root')!).render(<><App/><details className="fixture-controls" style={{position:'fixed',bottom:4,left:4,zIndex:100,fontSize:10,background:'#fff'}}><summary>隔离验收（虚构档案）</summary>{['stickers','routines','hermes'].map(v=><button key={v} onClick={()=>legacy(v)}>旧入口 {v}</button>)}</details></>)
