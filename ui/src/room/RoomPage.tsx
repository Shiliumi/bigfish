import { memo, useEffect, useRef, useState } from 'react'
import { ArrowUpRight, CloudRain, Lamp, Moon, RotateCcw, SlidersHorizontal, Snowflake, Sun, Sunset, X } from 'lucide-react'
import { api } from '../api'
import { PetVideo } from '../Companion'
import { createRoom, type RoomScene } from './scene'
import { roomActivity, roomEnvironment } from './environment.mjs'
import './room.css'

interface Clip {label:string;duration:number;poster:string;preview:string;mov:string;webm:string;width:number;height:number;fps:number}
interface Manifest {version:number;animations:Record<string,Clip>}
type Destination='chat'|'explore'|'memory'|'inbox'
const slots:Record<string,{title:string;description:string;destination?:Destination;link?:string}> = {
  window:{title:'窗边',description:'窗外是小屋的海景。这里的雨雪是房间氛围，可以按你喜欢的样子切换。'},
  bed:{title:'软乎乎的床',description:'被子铺好了，鲸鱼抱枕也在。给小屋留一个可以歇一歇的角落。'},
  lamp:{title:'床头的小灯',description:'想亮一点，或者留点夜色，都可以。灯光只影响这间小屋。'},
  desk:{title:'靠窗的书桌',description:'她最近真正看过的内容，收在探索日志里。',destination:'explore',link:'看看她最近读了什么'},
  shelf:{title:'慢慢攒起来的回忆',description:'已经记录的小事，可以在记忆空间查看、修改，也可以让她忘记。',destination:'memory',link:'翻翻共同的回忆'},
  book:{title:'地上的小本子',description:'她记下的小事，都放在记忆空间里。随时可以翻翻。',destination:'memory',link:'打开记忆空间'},
  chair:{title:'她的小椅子',description:'桌前留一个位置，看够了屏幕，也可以回来歇会儿。'},
  cup:{title:'一只小杯子',description:'留在桌边，离屏幕远一点。'},
  rug:{title:'鲸鱼地毯',description:'给这条鲸留了一块软乎乎的地方。点点她，可以打个招呼。'},
  cushion:{title:'蓝色靠垫',description:'小屋里的一个舒服角落。'},
  plant:{title:'窗边的绿意',description:'给海边小屋添一点绿。'},
  picture:{title:'墙上的小画',description:'给房间留一点海的颜色。'},
}
function preference(key:string, choices:string[], fallback:string) {try {const v=localStorage.getItem(key);return choices.includes(v||'')?v!:fallback}catch{return fallback}}
function RoomPage({onNavigate}:{onNavigate:(page:Destination)=>void}) {
  const host=useRef<HTMLDivElement>(null), character=useRef<HTMLDivElement>(null), engine=useRef<RoomScene|null>(null)
  const [generation,setGeneration]=useState(0), [failed,setFailed]=useState(false), [contextLost,setContextLost]=useState(false)
  const [period,setPeriod]=useState(()=>preference('fish.room.period',['auto','day','dusk','night'],'auto'))
  const [weather,setWeather]=useState(()=>preference('fish.room.weather',['clear','rain','snow'],'clear'))
  const [lamp,setLamp]=useState(()=>preference('fish.room.lamp',['on','off'],'on')==='on')
  const [settings,setSettings]=useState(false), [selected,setSelected]=useState<string|null>(null)
  const [manifest,setManifest]=useState<Manifest|null>(null), [activity,setActivity]=useState({animation:'idle',label:'正在看看她在忙什么…'})
  const [visible,setVisible]=useState(()=>!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false)
  const [minute,setMinute]=useState(Date.now()), [greeting,setGreeting]=useState(false)
  const sceneEnvironment=roomEnvironment(period,weather,new Date(minute))
  useEffect(()=>{const visibility=()=>setVisible(!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false);document.addEventListener('visibilitychange',visibility);window.addEventListener('fish:window-visibility',visibility);return()=>{document.removeEventListener('visibilitychange',visibility);window.removeEventListener('fish:window-visibility',visibility)}},[])
  useEffect(()=>{
    if(!host.current)return
    setFailed(false);setContextLost(false)
    try { engine.current=createRoom(host.current,{select:setSelected,project:(x,y,size)=>{if(character.current){character.current.style.left=x+'px';character.current.style.top=y+'px';character.current.style.width=Math.max(70,size*1.13)+'px'}},lost:()=>setContextLost(true),restored:()=>setContextLost(false)}) }
    catch {setFailed(true)}
    return()=>{engine.current?.dispose();engine.current=null}
  },[generation])
  useEffect(()=>{engine.current?.environment(roomEnvironment(period,weather,new Date(minute)),lamp)},[period,weather,lamp,minute,generation])
  useEffect(()=>{engine.current?.active(visible&&!failed)},[visible,failed,generation])
  useEffect(()=>{
    if(!visible)return
    setMinute(Date.now());const timer=setInterval(()=>setMinute(Date.now()),60_000);return()=>clearInterval(timer)
  },[visible])
  useEffect(()=>{
    if(!visible)return
    const controller=new AbortController();let pending=false
    async function poll(){if(pending)return;pending=true;try{const state=await api<{state:string;label:string}>('/companion',{signal:controller.signal});if(!controller.signal.aborted)setActivity(roomActivity(state))}catch{if(!controller.signal.aborted)setActivity({animation:'look',label:'暂时联系不上鱼塘，房间还在'})}finally{pending=false}}
    void poll();const timer=setInterval(()=>void poll(),15_000);return()=>{controller.abort();clearInterval(timer)}
  },[visible])
  useEffect(()=>{const controller=new AbortController();fetch('/pet/manifest.json',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(setManifest).catch(()=>{});return()=>controller.abort()},[])
  useEffect(()=>{try{localStorage.setItem('fish.room.period',period);localStorage.setItem('fish.room.weather',weather);localStorage.setItem('fish.room.lamp',lamp?'on':'off')}catch{}},[period,weather,lamp])
  useEffect(()=>{if(!greeting)return;const timer=setTimeout(()=>setGreeting(false),(manifest?.animations.greeting?.duration||10)*1000);return()=>clearTimeout(timer)},[greeting,manifest])
  const slot=selected?slots[selected]:undefined
  return <section className="room-page" aria-label="大肥鱼的小屋">
    <header className="room-heading"><div><span className="room-eyebrow">A LITTLE PLACE OF HER OWN</span><h1>大肥鱼的小屋<span>01</span></h1><p>留一扇窗，也留一点慢慢生活的空间。</p></div><button className={'room-button '+(settings?'selected':'')} aria-expanded={settings} onClick={()=>setSettings(v=>!v)}><SlidersHorizontal size={16}/>房间氛围</button></header>
    {settings&&<div className="room-settings"><div role="group" aria-label="小屋时段">{[{id:'auto',name:'跟随时间',icon:Sun},{id:'day',name:'白天',icon:Sun},{id:'dusk',name:'黄昏',icon:Sunset},{id:'night',name:'夜晚',icon:Moon}].map(x=><button key={x.id} aria-pressed={period===x.id} onClick={()=>setPeriod(x.id)}><x.icon size={15}/>{x.name}</button>)}</div><div role="group" aria-label="小屋天气氛围">{[{id:'clear',name:'晴',icon:Sun},{id:'rain',name:'雨',icon:CloudRain},{id:'snow',name:'雪',icon:Snowflake}].map(x=><button key={x.id} aria-pressed={weather===x.id} onClick={()=>setWeather(x.id)}><x.icon size={15}/>{x.name}</button>)}</div><span>天气为小屋氛围 · 自动时段按北京时间</span></div>}
    <div className="room-card">
      <div className="room-scene-label"><span className="room-dot"/>{sceneEnvironment.label}<span className="room-scene-number">海边小屋</span></div>
      <div className="room-stage" ref={host} data-period={sceneEnvironment.period}>
        <div ref={character} className="room-character-anchor" hidden={failed||contextLost}>
        <button className="room-character" aria-label="摸摸大肥鱼" onClick={()=>setGreeting(true)}>
          {greeting&&<span className="room-hello">爹，进来坐会儿？</span>}
          {manifest&&visible?<PetVideo animation={greeting?'greeting':activity.animation} manifest={manifest}/>:<img src="/pet/idle-poster.png" alt="大肥鱼"/>}
        </button></div>
        {(failed||contextLost)&&<div className="room-recovery" role="alert"><Moon size={28}/><strong>{contextLost?'小屋的画面暂停了':'小屋画面暂时没有打开'}</strong><p>可以重新打开画面，聊天和记忆仍然保留。</p><button className="room-button" onClick={()=>setGeneration(v=>v+1)}><RotateCcw size={15}/>重新打开小屋</button></div>}
        {slot&&<aside className="room-inspect" aria-label={slot.title}><button className="room-inspect-close" aria-label="关闭物品介绍" onClick={()=>setSelected(null)}><X size={16}/></button><span className="room-eyebrow">A LITTLE CORNER</span><h2>{slot.title}</h2><p>{slot.description}</p>{selected==='lamp'&&<button className="room-button" aria-pressed={lamp} onClick={()=>setLamp(v=>!v)}><Lamp size={15}/>{lamp?'关掉台灯':'打开台灯'}</button>}{slot.destination&&<button className="room-text-link" onClick={()=>onNavigate(slot.destination!)}>{slot.link}<ArrowUpRight size={15}/></button>}</aside>}
      </div>
      <footer className="room-scene-toolbar"><span>拖动转视角 · 滚轮缩放 · 点点房间里的东西</span><div><button className="room-icon" aria-label={lamp?'关掉小屋台灯':'打开小屋台灯'} aria-pressed={lamp} onClick={()=>setLamp(v=>!v)}><Lamp size={17}/></button><button className="room-icon" aria-label="恢复小屋视角" onClick={()=>engine.current?.reset()}><RotateCcw size={16}/></button></div></footer>
    </div>
    <div className="room-bottom"><div className="room-presence"><img src="/pet/idle-poster.png" alt=""/><div><span>她这会儿</span><strong>{activity.label}</strong></div><button className="room-text-link" onClick={()=>onNavigate('chat')}>和她聊聊<ArrowUpRight size={16}/></button></div><div className="room-corners" role="group" aria-label="看看房间里的角落"><button onClick={()=>setSelected('desk')}>书桌</button><button onClick={()=>setSelected('shelf')}>书架</button><button onClick={()=>setSelected('window')}>窗边</button></div></div>
    <p className="room-footnote">小屋里的光、雨和日常动作在本机运行。角色与动画署名见应用「关于大肥鱼」。</p>
  </section>
}
export default memo(RoomPage)
