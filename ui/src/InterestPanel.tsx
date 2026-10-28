import {useState} from 'react'
import {ExternalLink,Sparkles} from 'lucide-react'
import {api} from './api'

export interface CuriositySnapshot {
 threads:{id:string;question:string;why:string;source_urls:string[];cooling_down:boolean}[]
 controls:{revision:number;items:{id:string;question:string;choice:'paused'|'retired';until:string|null;active:boolean}[]}
 used_today:number;daily_limit:number;last_outing:{question:string;status:string;outcome:string|null;reason:string|null}|null
}
const date=(value:string)=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})

export default function InterestPanel({data,onChanged}:{data:CuriositySnapshot;onChanged:(value:CuriositySnapshot)=>void}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
 const controls=data.controls||{revision:0,items:[]}
 async function change(id:string,choice:'pause'|'retire'|'resume'){
  setBusy(true);setError('');setNotice('')
  try{
   await api('/curiosity/'+id,{method:'PATCH',body:JSON.stringify({choice,revision:controls.revision})})
   onChanged(await api<CuriositySnapshot>('/curiosity'))
   setNotice(choice==='pause'?'先放三天，之后可自然接着看。':choice==='retire'?'这个问题先放下，想接着看时可以恢复。':'限制已解除；仍按原有的有效期和冷却时间安排。')
  }catch(e){
   setError((e as Error).message)
   try{onChanged(await api<CuriositySnapshot>('/curiosity'))}catch{/* Keep the last visible snapshot and error. */}
  }finally{setBusy(false)}
 }
 return <section className="curiosity-card" aria-label="兴趣与反馈" aria-busy={busy}>
  <header><span><Sparkles size={17}/>她最近惦记的</span><small>临时好奇，会变，也会放下</small></header>
  {data.threads.length?<div className="curiosity-threads">{data.threads.map(t=><article key={t.id}>
   <h3>{t.question}{t.cooling_down&&<em>先放一放</em>}</h3><p>{t.why}</p>
   {t.source_urls[0]&&<a href={t.source_urls[0]} target="_blank" rel="noopener noreferrer">从这次见闻接着想 <ExternalLink size={11}/></a>}
   <div className="interest-actions"><button disabled={busy} aria-label={'先放三天：'+t.question} onClick={()=>void change(t.id,'pause')}>先放三天</button><button disabled={busy} aria-label={'放下：'+t.question} onClick={()=>void change(t.id,'retire')}>放下这个问题</button></div>
  </article>)}</div>:<p className="curiosity-empty">还没有非追不可的问题。先看看，遇见喜欢的再留下。</p>}
  {controls.items.length>0&&<details className="interest-shelf"><summary>放在一边的 · {controls.items.length}</summary><div>{controls.items.map(t=><article key={t.id}><div><h3>{t.question}</h3><p>{t.choice==='retired'?'已放下，等待你恢复':t.active&&t.until?'暂停至 '+date(t.until)+'（北京时间）':'三天暂停已结束'}</p></div><button className="text-button" disabled={busy} aria-label={(t.active?'恢复：':'清除设置：')+t.question} onClick={()=>void change(t.id,'resume')}>{t.active?'恢复':'清除此设置'}</button></article>)}</div></details>}
  {error&&<p role="alert" className="learning-error">{error}</p>}{notice&&<p role="status" className="interest-notice">{notice}</p>}
  <footer>每天最多实际逛 {data.daily_limit} 次，出发机会可以跳过。<span>这些选择影响这个问题及已关联来源的主动推荐。原有见闻和成长记录保留；已出发的阅读会正常收好。</span>{data.last_outing?.reason&&<span>上次回来：{data.last_outing.reason}</span>}</footer>
 </section>
}
