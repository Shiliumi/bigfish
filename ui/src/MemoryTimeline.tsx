import {useEffect,useRef,useState} from 'react'
import {BookOpen,Pin,Search,RefreshCw} from 'lucide-react'
import MemoryEpisodeEditor from './memory/MemoryEpisodeEditor'
import type {Episode} from './memory/types'
import {api} from './api'
import './learning.css'
const date=(value:string)=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})
export default function MemoryTimeline(){
 const [query,setQuery]=useState(''),[scope,setScope]=useState('current'),[items,setItems]=useState<Episode[]>([]),[stats,setStats]=useState({total:0,historical:0}),[error,setError]=useState(''),[loading,setLoading]=useState(false),[selected,setSelected]=useState<string|null>(null)
 const sequence=useRef(0)
 async function load(){const id=++sequence.current;setLoading(true);try{const value=await api<{items:Episode[];stats:{total:number;historical:number}}>('/episodes?q='+encodeURIComponent(query)+'&scope='+scope);if(id===sequence.current){setItems(value.items);setStats(value.stats);setError('')}}catch(e){if(id===sequence.current)setError((e as Error).message)}finally{if(id===sequence.current)setLoading(false)}}
 useEffect(()=>{const timer=setTimeout(()=>void load(),250);return()=>{clearTimeout(timer);sequence.current++}},[query,scope])
 return <section className="learning-panel memory-timeline" aria-label="共同经历"><header className="learning-heading"><div><span className="learning-kicker">OUR LITTLE HISTORY</span><h2>一起聊过的，慢慢记得</h2><p>更正后的记法用于当前召回，旧原文留作历史。普通印象可以慢慢淡化。</p></div><button className="icon-button" aria-label="刷新共同经历" disabled={loading} onClick={()=>void load()}><RefreshCw size={16} className={loading?'spin':''}/></button></header>
 <div className="learning-actions"><label className="search-field"><Search size={15}/><input aria-label="搜索共同经历" value={query} onChange={e=>setQuery(e.target.value)} placeholder="作品、昵称、别名，或昨天聊过的话题…"/></label><select aria-label="回忆有效状态" value={scope} onChange={e=>setScope(e.target.value)}><option value="current">当前有效</option><option value="history">包含过时记录</option></select><span className="learning-count">有效 {stats.total} · 过时 {stats.historical}</span></div>
 {error&&<p role="alert" className="learning-error">{error}</p>}
 <div className="episode-grid">{items.map(item=><button className="episode-card" key={item.id} onClick={()=>setSelected(item.id)}><span><BookOpen size={15}/>{new Date(item.recorded_at).toLocaleDateString('zh-CN')}{Boolean(item.pinned)&&<Pin size={13}/>}<em>{item.effective_status==='expired'?'已过时':item.effective_status==='future'?'尚未生效':item.kind==='impression'?'情境印象':'具体经历'}{item.corrected_at?' · 已更正':''}</em></span><p>{item.summary}</p><small>{item.valid_until?'有效至 '+date(item.valid_until):'保留经历，按相关性想起'}{item.match_kind?' · '+({alias:'别名关联',equivalent:'相关词关联',keywords:'关键词匹配'}[item.match_kind]||'相关线索'):''} · 查看来源</small></button>)}</div>
 {!loading&&!items.length&&<div className="learning-empty"><BookOpen size={25}/><p>{query?'这次没翻到，换个具体话题试试。':'还没有符合条件的片段。新对话的经历会慢慢积攒在这里。'}</p></div>}
 <p className="learning-footnote">默认展示近期与已固定的 30 段；搜索支持少量常见同义词、手动别名，以及昨天、前天、上周和明确日期。日期按原聊天记录的北京时间筛选。过时记录只在历史中查看，不进入当前召回；固定也不延长有效期。遗忘会清除此回忆及修改历史，原始 Hermes 聊天仍保留。</p>
 {selected&&<MemoryEpisodeEditor id={selected} onClose={()=>setSelected(null)} onChanged={()=>void load()}/>}
 </section>
}
