import {useEffect,useState} from 'react'
import {api} from '../api'
interface Wish{id:string;item?:string;text?:string;why?:string;status:string;source?:{url:string}[]}
interface Life{revision:number;enabled:boolean;pause_reason:string|null;wishes:Wish[];moves:{id:string;why:string;object:string;surface:string}[]}
const states:Record<string,string>={open:'还惦记着',accepted:'爸爸先记下了',declined:'先不添置',fulfilled:'已由你标记满足',expired:'先放下了',source_unavailable:'来源已收起'}
export default function RoomLife(){const [data,setData]=useState<Life|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  async function load(){try{setData(await api<Life>('/room/life'));setError('')}catch{setError('生活记录暂时没有连上，稍后再看看。')}}
  useEffect(()=>{let active=true;const refresh=()=>{if(active&&!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false)void load()};refresh();const timer=setInterval(refresh,10000);return()=>{active=false;clearInterval(timer)}},[])
  async function update(change:Record<string,unknown>){if(!data||busy)return;setBusy(true);try{setData(await api<Life>('/room/life',{method:'PUT',body:JSON.stringify({revision:data.revision,...change})}));setError('')}catch(e){setError((e as Error).message);void load()}finally{setBusy(false)}}
  return <section className="room-life" aria-label="她的小屋生活"><header><div><span className="room-eyebrow">LITTLE THINGS SHE WANTS</span><h2>她的小打算</h2></div><button className="room-button" role="switch" aria-checked={data?.enabled??false} disabled={!data||busy} onClick={()=>void update({action:'settings',enabled:!data?.enabled})}>自主布置与愿望 {data?.enabled?'开':'关'}</button></header>
    {error&&<p role="alert">{error}</p>}{data?.pause_reason&&<p className="room-life-pause">{data.pause_reason}</p>}
    {!data?.wishes.length&&<p className="room-life-empty">碰到真想放进小屋的东西，再留个愿望。没有想法的时候，就先这样待着。</p>}
    <div className="room-wishes">{data?.wishes.map(w=><article key={w.id}><span>{states[w.status]||w.status}</span>{w.item&&<h3>{w.item}</h3>}{w.text&&<p>{w.text}</p>}{w.why&&<small>{w.why}</small>}{w.source?.map(s=><a href={s.url} key={s.url} target="_blank" rel="noopener noreferrer">这次读到的来源 ↗</a>)}{['open','accepted'].includes(w.status)&&<footer><button disabled={busy} onClick={()=>void update({action:'wish',id:w.id,status:'accepted'})}>先记下</button><button disabled={busy} onClick={()=>void update({action:'wish',id:w.id,status:'declined'})}>先不添</button><button disabled={busy} onClick={()=>void update({action:'wish',id:w.id,status:'fulfilled'})}>已满足（手动标记）</button></footer>}</article>)}</div>
    {!!data?.moves.length&&<details><summary>她自己调整过的小角落</summary>{data.moves.map(m=><p key={m.id}>{m.why}</p>)}</details>}
    <p className="room-footnote">想法来自真实冲浪收尾，不另开模型任务。锁定的物品她不能挪；愿望不代表已购买或已放进房间。</p>
  </section>
}
