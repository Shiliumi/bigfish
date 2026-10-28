import {useEffect,useRef,useState} from 'react'
import {api} from './api'
interface Settings {enabled:boolean;daily_tokens:number;revision:number;activated_at:string}
interface Budget {day:string;used:number;remaining:number;reserved:number;unknown:number;blocked:number;settings:Settings;groups:{source:string;task:string;status:string;calls:number;charged:number}[]}
const number=(n:number)=>n.toLocaleString('zh-CN')
export default function BudgetPanel(){
 const [data,setData]=useState<Budget|null>(null),[limit,setLimit]=useState(''),[enabled,setEnabled]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const sequence=useRef(0)
 async function load(){const id=++sequence.current;try{const value=await api<Budget>('/budget');if(id===sequence.current){setData(value);setLimit(String(value.settings.daily_tokens));setEnabled(value.settings.enabled);setError('')}}catch(e){if(id===sequence.current)setError((e as Error).message)}}
 useEffect(()=>{void load();return()=>{sequence.current++}},[])
 async function save(){if(!data)return;const n=Number(limit);if(!/^\d+$/.test(limit)||!Number.isSafeInteger(n)||n<10000||n>200000000){setError('每日额度需为 10,000–200,000,000 的整数 token。');return}setBusy(true);try{await api('/budget',{method:'PUT',body:JSON.stringify({enabled,daily_tokens:n,revision:data.settings.revision})});await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <section className="budget-panel" aria-label="每日后台鱼粮额度"><header><div><h3>后台每天吃多少鱼粮</h3><p>从适配启用后记录，未补算此前消耗。北京时间每天重新计额，正常聊天独立记录。</p></div><button className="text-button" disabled={busy} onClick={()=>void load()}>刷新额度</button></header>
 {error&&<p role="alert" className="learning-error">{error}</p>}
 {data?<><div className="budget-numbers"><span>今日后台计入<strong>{number(data.used)}</strong> token</span><span>剩余额度<strong>{number(data.remaining)}</strong> token</span><span>本地拦下<strong>{number(data.blocked)}</strong> 次请求</span></div>
 <form onSubmit={e=>{e.preventDefault();void save()}} className="budget-form"><label className="budget-toggle"><input type="checkbox" checked={enabled} disabled={busy} onChange={e=>setEnabled(e.target.checked)}/>启用后台额度</label><label>每日总 token<input aria-label="后台每日 token 额度" inputMode="numeric" value={limit} disabled={busy} onChange={e=>setLimit(e.target.value)}/></label><button className="secondary-button" disabled={busy} type="submit">{busy?'保存中…':'保存额度'}</button></form>
 <p className="learning-footnote">覆盖本应用 Hermes 的全部定时任务，包括自行添加的任务；额度用尽会拦住它们的后续主模型请求。聊天主请求不受此额度限制。输入（含缓存）和输出相加，推理不重复计入，这不是金额预算。</p>
 <p className="learning-footnote">正在预留 {number(data.reserved)} token，用量未知暂占 {number(data.unknown)} token。主后台请求先保守预留，完成后退回未用部分；单次输出最多 8,192 token。未知用量和失联请求不会按零结算。</p>
 <details><summary>记录范围与预算边界</summary><p className="learning-footnote">从 {new Date(data.settings.activated_at).toLocaleString('zh-CN')} 开始记账，未导入此前消耗；以请求开始日归额。后台辅助调用、会话标题与对话后的复盘也会计入，但 Hermes 的辅助接口只支持观察，无法在该接口逐次拦截。无法归属的辅助调用单列；正在进行的请求、辅助调用及底层重试仍可能超额，服务商账单为准。</p><div className="learning-table-wrap"><table><caption>今日请求记录 · 按用途与状态</caption><thead><tr><th>来源</th><th>用途</th><th>状态</th><th>次数</th><th>计入 token</th></tr></thead><tbody>{data.groups.map((r,i)=><tr key={i}><td>{({background:'后台',chat:'聊天',unassigned:'归属未知'}[r.source]||'其他')}</td><td>{r.task==='main'?'主请求':r.task.replace(/^aux:/,'辅助 · ')}</td><td>{({actual:'已结算',reserved:'预留中',unknown:'用量未知',blocked:'本地拦下'}[r.status]||r.status)}</td><td>{number(r.calls)}</td><td>{number(r.charged)}</td></tr>)}</tbody></table></div></details>
 </>:<p className="learning-footnote">正在读取本机额度…</p>}
 </section>
}
