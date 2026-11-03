import {useEffect,useRef,useState} from 'react'
import {BookOpen,ChevronLeft,ChevronRight,Expand,Minus,Pin,Plus,RefreshCw,Search,Sparkles,X} from 'lucide-react'
import {api} from '../api'
import MemoryEpisodeEditor from './MemoryEpisodeEditor'
import {dateAt,dateOffset,relatedStars} from './star-layout.mjs'
import type {MemoryGraphData,MemoryStar} from './types'
import type {StarScene} from './star-scene'
import './stars.css'

const date=(value:string)=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})
const status=(node:MemoryStar)=>node.effective_status==='expired'?'已过时':node.effective_status==='future'?'尚未生效':node.kind==='impression'?'情境印象':'共同经历'

export default function MemoryStarMap(){
  const [query,setQuery]=useState(''),[scope,setScope]=useState('current'),[kind,setKind]=useState('all'),[pinned,setPinned]=useState(false)
  const [from,setFrom]=useState(''),[to,setTo]=useState(''),[data,setData]=useState<MemoryGraphData|null>(null)
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[selected,setSelected]=useState<string|null>(null),[editor,setEditor]=useState<string|null>(null)
  const [notice,setNotice]=useState('')
  const [rotating,setRotating]=useState(false),[generation,setGeneration]=useState(0),[failed,setFailed]=useState(false),[lost,setLost]=useState(false),[list,setList]=useState(false)
  const [visible,setVisible]=useState(()=>!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false)
  const [reduced,setReduced]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches)
  const host=useRef<HTMLDivElement>(null),engine=useRef<StarScene|null>(null),dataRef=useRef(data),selectionRef=useRef(selected),editorRef=useRef(editor),visibleRef=useRef(visible),rotationRef=useRef(rotating)
  const refreshRef=useRef<()=>void>(()=>{}),filterKey=useRef('')
  dataRef.current=data;selectionRef.current=selected;editorRef.current=editor;visibleRef.current=visible;rotationRef.current=rotating
  const hasStars=Boolean(data?.nodes.length)
  useEffect(()=>{const change=()=>setVisible(!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false);const media=matchMedia('(prefers-reduced-motion: reduce)'),motion=()=>setReduced(media.matches)
    document.addEventListener('visibilitychange',change);window.addEventListener('fish:window-visibility',change);media.addEventListener('change',motion)
    return()=>{document.removeEventListener('visibilitychange',change);window.removeEventListener('fish:window-visibility',change);media.removeEventListener('change',motion)}
  },[])
  useEffect(()=>{
    const key=JSON.stringify([query,scope,kind,pinned,from,to])
    if(filterKey.current!==key){filterKey.current=key;setData(null);setSelected(null);setEditor(null);setLoading(true);setNotice('')}
    if(!visible)return
    let alive=true,request:AbortController|undefined,pending=false,sequence=0
    async function refresh(clear=false){
      if(!alive||pending&&!clear)return
      request?.abort();request=new AbortController();const abort=request,seq=++sequence;pending=true
      if(clear){setData(null);setSelected(null);setEditor(null)}
      setLoading(true)
      try{
        const params=new URLSearchParams({q:query,scope,kind,pinned:String(pinned),from,to})
        const value=await api<MemoryGraphData>('/memory-graph?'+params,{signal:abort.signal})
        if(!alive||abort.signal.aborted||seq!==sequence)return
        const previous=dataRef.current,chosen=selectionRef.current,current=value.nodes.find(n=>n.id===chosen),before=previous?.nodes.find(n=>n.id===chosen)
        if(chosen&&(!current||before?.revision!==current.revision||before?.effective_status!==current.effective_status)){setSelected(null);setEditor(null);setNotice('选中的回忆已更新或不再符合筛选，星图已重新核对。')}
        setData(value);setError('')
      }catch(e){if(alive&&!abort.signal.aborted&&seq===sequence){setError((e as Error).message);setData(null);setSelected(null);setEditor(null)}}
      finally{if(alive&&seq===sequence){pending=false;setLoading(false)}}
    }
    refreshRef.current=()=>void refresh(true)
    const invalidated=()=>void refresh(true),start=setTimeout(()=>void refresh(),200),timer=setInterval(()=>void refresh(),10_000)
    window.addEventListener('fish.memory.changed',invalidated)
    return()=>{alive=false;request?.abort();clearTimeout(start);clearInterval(timer);window.removeEventListener('fish.memory.changed',invalidated);refreshRef.current=()=>{}}
  },[query,scope,kind,pinned,from,to,visible])
  useEffect(()=>{
    if(!hasStars||!host.current)return
    let disposed=false;setFailed(false);setLost(false)
    void import('./star-scene').then(({createStarScene})=>{
      if(disposed||!host.current)return
      try{
        const instance=createStarScene(host.current,{select:id=>setSelected(id),lost:()=>setLost(true),restored:()=>setLost(false)})
        engine.current=instance;if(dataRef.current)instance.data(dataRef.current);instance.select(selectionRef.current);instance.rotate(rotationRef.current);instance.active(visibleRef.current)
      }catch{setFailed(true)}
    }).catch(()=>{if(!disposed)setFailed(true)})
    return()=>{disposed=true;engine.current?.dispose();engine.current=null}
  },[hasStars,generation])
  useEffect(()=>{if(data)engine.current?.data(data)},[data?.revision,generation])
  useEffect(()=>engine.current?.select(selected),[selected,data?.revision,generation])
  useEffect(()=>engine.current?.active(visible),[visible,generation])
  useEffect(()=>engine.current?.rotate(rotating),[rotating,generation])
  const node=data?.nodes.find(n=>n.id===selected),related=data&&node?relatedStars(data,node.id):[]
  const range=data?.range,days=range?.from&&range.to?dateOffset(range.from,range.to):0
  const cursor=range?.from?Math.max(0,Math.min(days,to?dateOffset(range.from,to):days)):0
  const firstDay=range?.from&&from?Math.max(0,Math.min(days,dateOffset(range.from,from))):0
  const canSlide=Boolean(days&&range?.to&&(!from||from<=range.to))
  function step(delta:number){if(range?.from)setTo(dateAt(range.from,Math.max(firstDay,Math.min(days,cursor+delta))))}
  return <section className="memory-stars" aria-label="记忆星图">
    <header className="stars-heading"><div><span className="learning-kicker">OUR CONSTELLATION</span><h2>一起攒下的小星星</h2><p>每一颗都是聊过的片段，点亮它，看看那时说了什么。</p></div><button className="secondary-button" disabled={loading||!visible} onClick={()=>refreshRef.current()}><RefreshCw size={15} className={loading?'spin':''}/>刷新星图</button></header>
    <div className="stars-filters">
      <label className="search-field"><Search size={15}/><input aria-label="搜索星图记法或别名" value={query} maxLength={100} placeholder="搜索当前记法或手动别名…" onChange={e=>setQuery(e.target.value)}/></label>
      <select aria-label="星图记忆类型" value={kind} onChange={e=>setKind(e.target.value)}><option value="all">全部类型</option><option value="event">共同经历</option><option value="impression">情境印象</option></select>
      <select aria-label="星图有效状态" value={scope} onChange={e=>setScope(e.target.value)}><option value="current">当前有效</option><option value="history">含过时 / 未生效</option></select>
      <button className={'stars-filter-button '+(pinned?'selected':'')} aria-pressed={pinned} onClick={()=>setPinned(v=>!v)}><Pin size={14}/>只看固定</button>
    </div>
    <div className="stars-date-filters"><label>从<input type="date" aria-label="星图开始日期" value={from} max={to||undefined} onChange={e=>setFrom(e.target.value)}/></label><label>到<input type="date" aria-label="星图结束日期" value={to} min={from||undefined} onChange={e=>setTo(e.target.value)}/></label>{(from||to)&&<button className="text-button" onClick={()=>{setFrom('');setTo('')}}>全部日期</button>}<span>按原记录日期筛选 · 北京时间</span></div>
    {error&&<p className="learning-error" role="alert">{error}<button className="text-button" onClick={()=>refreshRef.current()}>重新读取</button></p>}
    {notice&&<p className="stars-limit" role="status">{notice}<button className="text-button" onClick={()=>setNotice('')}>知道了</button></p>}
    <div className="stars-workspace" aria-busy={loading}>
      <div className="stars-viewport"><div className="stars-stage" ref={host}>
        <div className="stars-stage-title"><span className="stars-small-dot"/>我们的记忆星空<small>{data?`${data.stats.shown} 颗星 · ${data.edges.length} 条关联`:error?'等待重新读取':'正在核对回忆'}</small></div>
        {!hasStars&&<div className="stars-empty" role="status"><Sparkles size={32}/><strong>{loading?'正在翻开共同的回忆…':error?'星图暂时没有打开':'这里还没有亮起的星星'}</strong><p>{loading?'只读取本机记录，不请求模型。':error?'可以点击重新读取，恢复后会重新核对有效记忆。':query||from||to||pinned||kind!=='all'?'试试放宽筛选，看看别的日子。':'等真实经历慢慢攒起来；这里不放示例回忆。'}</p></div>}
        {(failed||lost)&&hasStars&&<div className="stars-empty stars-recovery" role="alert"><strong>星空画面暂时暂停了</strong><p>仍可以用下方记录列表查看来源。</p><button className="secondary-button" onClick={()=>setGeneration(v=>v+1)}>重新打开画面</button></div>}
        {hasStars&&<footer className="stars-canvas-tools"><span>拖动旋转 · ⌘ / Ctrl + 滚轮缩放</span><div><button aria-label="缩小星图" onClick={()=>engine.current?.zoom(-1)}><Minus size={16}/></button><button aria-label="放大星图" onClick={()=>engine.current?.zoom(1)}><Plus size={16}/></button><button aria-label="复位星图视角" onClick={()=>engine.current?.reset()}><Expand size={16}/></button><button aria-label="缓慢旋转星图" aria-pressed={rotating&&!reduced} disabled={reduced} onClick={()=>setRotating(v=>!v)}>{rotating&&!reduced?'暂停旋转':'慢慢转'}</button></div></footer>}
      </div>
      <div className="stars-timeline"><div><span>记录到这一天</span><strong>{to||range?.to||'还没有记录'}</strong><span>{loading?'读取中…':data?`当前筛选 ${data.stats.matched} 段`:''}</span></div><div><button aria-label="星图前一天" disabled={!canSlide||cursor<=firstDay||loading} onClick={()=>step(-1)}><ChevronLeft size={16}/></button><input type="range" aria-label="星图记录截止日期" min={firstDay} max={Math.max(firstDay+1,days)} value={Math.max(firstDay,cursor)} disabled={!canSlide||firstDay===days} onChange={e=>range?.from&&setTo(dateAt(range.from,Number(e.target.value)))}/><button aria-label="星图后一天" disabled={!canSlide||cursor>=days||loading} onClick={()=>step(1)}><ChevronRight size={16}/></button></div><small>日期改变展示范围，记法始终采用当前版本，不还原已更正的旧内容。</small></div>
      </div>
      <aside className="stars-inspector" aria-label="星图说明与选中回忆">
        {node?<><header><span className={'star-kind '+node.kind}>{status(node)}{node.pinned?' · 已固定':''}</span><button className="icon-button" aria-label="取消选择星星" onClick={()=>setSelected(null)}><X size={16}/></button></header><time>{date(node.recorded_at)}</time><h3>那次一起聊过</h3><p className="star-summary" aria-live="polite">{node.summary}</p><div className="star-validity">{node.corrected_at&&<span>已更正 · 版本 {node.revision}</span>}{node.valid_until&&<span>有效至 {date(node.valid_until)}</span>}{node.effective_status!=='active'&&<span>历史记录 · 不参与当前召回</span>}</div><button className="primary-button stars-source-button" onClick={()=>setEditor(node.id)}><BookOpen size={15}/>查看来源 / 更正 / 遗忘</button><div className="stars-related"><h4>这颗星的关联 <span>{related.length}</span></h4>{!related.length&&<p>暂时没有可核对的连线，不勉强连起来。</p>}{related.slice(0,12).map(link=>{const other=data?.nodes.find(n=>n.id===link.id);return other&&<button key={link.id} onClick={()=>setSelected(link.id)}><strong>{other.summary}</strong><small>{link.reasons.map(r=>r.label).join('；')}</small></button>})}{related.length>12&&<p>画面显示全部关联，这里列出前 12 段。</p>}</div></>:<><span className="learning-kicker">LITTLE THINGS, KEPT</span><h3>点一颗星，重逢一下</h3><p>亮点是已有的共同经历，连线有明确依据；距离和位置只用于排布。</p><div className="stars-overview"><div><strong>{data?.stats.current??'—'}</strong><span>当前有效</span></div><div><strong>{data?.stats.pinned??'—'}</strong><span>图中固定</span></div></div><div className="stars-legend"><span><i className="event"/>共同经历</span><span><i className="impression"/>情境印象</span><span><i className="pinned"/>已固定</span></div><p className="stars-fineprint">同一对话相邻记录连线；共同的手动别名也会连线。连线不代表因果，星星大小不表示“记忆强度”。过时记录仅在历史筛选中显示为暗星。</p><h4>最近几颗</h4>{data?.nodes.slice(0,4).map(n=><button className="stars-recent" key={n.id} onClick={()=>setSelected(n.id)}><span>{n.summary}</span><small>{date(n.recorded_at)}</small></button>)}</>}
      </aside>
    </div>
    {Boolean(data?.stats.omitted)&&<p className="stars-limit" role="status">符合条件 {data!.stats.matched} 段，本图显示最近 {data!.stats.node_limit} 段。用日期或关键词缩小范围，可以查看更早的记录。</p>}
    {Boolean(data?.stats.omitted_edges)&&<p className="stars-limit">关联较多，画面最多显示 {data!.stats.edge_limit} 条连线；其余记录仍可单独打开。</p>}
    <details className="stars-accessible-list" open={list} onToggle={e=>setList(e.currentTarget.open)}><summary>按日期查看星图中的记录 · 可用键盘选择 {data?.nodes.length||0} 段</summary>{list&&<div>{data?.nodes.map(n=><button key={n.id} aria-pressed={selected===n.id} onClick={()=>setSelected(n.id)}><span className={'star-kind '+n.kind}>{status(n)}{n.pinned?' · 已固定':''}</span><time>{date(n.recorded_at)}</time><p>{n.summary}</p></button>)}</div>}</details>
    <p className="stars-footnote">这张图只读取共同经历库，不汇总整份核心人设或所有冲浪报告。更正、过时与遗忘会同步移除旧关联；原始聊天仍由 Hermes 保存。没有额外模型调用。</p>
    {editor&&<MemoryEpisodeEditor key={editor} id={editor} onClose={()=>setEditor(null)} onChanged={()=>{}}/>}
  </section>
}
