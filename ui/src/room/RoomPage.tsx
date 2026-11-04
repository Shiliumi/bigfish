import { memo, useEffect, useRef, useState } from 'react'
import { ChevronDown, ArrowUpRight, CloudRain, Lamp, Lock, Unlock, Moon, RotateCcw, SlidersHorizontal, Plus, Minus, Camera, Move, Save, Undo2, RotateCw, Snowflake, Sun, Sunset, X } from 'lucide-react'
import { api } from '../api'
import {roomIntent} from './life-motion.mjs'
import RoomLife from './RoomLife'
import { createRoom, type RoomScene } from './scene'
import { roomActivity, roomEnvironment } from './environment.mjs'
import {objects,surfaces,placeObject,type ObjectId} from './layout.mjs'
import {useRoomLayout} from './useRoomLayout'
import {useRoomAtmosphere} from './atmosphere'
import type {RoomPhoto} from './types'
import RoomContents from './RoomContents'
import RoomAlbum from './RoomAlbum'
import './room.css'

type Destination='chat'|'explore'|'memory'|'inbox'
const slots:Record<string,{title:string;description:string;destination?:Destination;link?:string}> = {
  window:{title:'窗边',description:'窗外是小屋的海景。这里的雨雪是房间氛围，可以按你喜欢的样子切换。'},
  bed:{title:'软乎乎的床',description:'被子铺好了，鲸鱼抱枕也在。给小屋留一个可以歇一歇的角落。'},
  lamp:{title:'床头的小灯',description:'想亮一点，或者留点夜色，都可以。灯光只影响这间小屋。'},
  desk:{title:'靠窗的书桌',description:'她最近真正看过的内容，收在探索日志里。',destination:'explore',link:'看看她最近读了什么'},
  shelf:{title:'慢慢攒起来的回忆',description:'已经记录的小事，可以在记忆空间查看、修改，也可以让她忘记。',destination:'memory',link:'翻翻共同的回忆'},
  book:{title:'她的小本子',description:'她记下的小事，都放在记忆空间里。随时可以翻翻。',destination:'memory',link:'打开记忆空间'},
  chair:{title:'她的小椅子',description:'桌前留一个位置，看够了屏幕，也可以回来歇会儿。'},
  cup:{title:'一只小杯子',description:'给小杯子找个喜欢的位置，离屏幕远一点。'},
  rug:{title:'鲸鱼地毯',description:'给这条鲸留了一块软乎乎的地方。点点她，可以打个招呼。'},
  cushion:{title:'蓝色靠垫',description:'小屋里的一个舒服角落。'},
  plant:{title:'窗边的绿意',description:'给海边小屋添一点绿。'},
  picture:{title:'墙上的小画',description:'给房间留一点海的颜色。'},
}
function RoomPage({onNavigate,onAttachPhoto,onOpenStarMap}:{onOpenStarMap?:()=>void;onNavigate:(page:Destination)=>void;onAttachPhoto?:(photo:RoomPhoto)=>void}) {
  const [editing,setEditing]=useState(false),[taking,setTaking]=useState(false),[photo,setPhoto]=useState<RoomPhoto|null>(null),[notice,setNotice]=useState('')
  const room=useRoomLayout(!editing&&!taking)
  const pendingPhoto=useRef<Record<string,unknown>|null>(null)
  const host=useRef<HTMLDivElement>(null), character=useRef<HTMLDivElement>(null), engine=useRef<RoomScene|null>(null)
  const [generation,setGeneration]=useState(0), [failed,setFailed]=useState(false), [contextLost,setContextLost]=useState(false)
  const atmosphere=useRoomAtmosphere(),{period,weather,lamp}=atmosphere.value
  const setPeriod=(period:string)=>atmosphere.setValue(v=>({...v,period:period as typeof v.period}))
  const setWeather=(weather:string)=>atmosphere.setValue(v=>({...v,weather:weather as typeof v.weather}))
  const setLamp=(update:(lamp:boolean)=>boolean)=>atmosphere.setValue(v=>({...v,lamp:update(v.lamp)}))
  const [settings,setSettings]=useState(false), [selected,setSelected]=useState<string|null>(null)
  const lastPublished=useRef('')
  const [resident,setResident]=useState({pose:'idle',goal:'rug'}),[mode,setMode]=useState(()=>{try{const value=localStorage.getItem('fish.room.activity');return ['auto','walk','desk','sleep'].includes(value||'')?value!:'auto'}catch{return 'auto'}}),[runtime,setRuntime]=useState('idle'),[activity,setActivity]=useState({animation:'idle',label:'正在看看她在忙什么…'})
  const [visible,setVisible]=useState(()=>!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false)
  const [minute,setMinute]=useState(Date.now()), [greeting,setGreeting]=useState(false)
  const sceneEnvironment=roomEnvironment(period,weather,new Date(minute))
  useEffect(()=>{const visibility=()=>setVisible(!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false);document.addEventListener('visibilitychange',visibility);window.addEventListener('fish:window-visibility',visibility);return()=>{document.removeEventListener('visibilitychange',visibility);window.removeEventListener('fish:window-visibility',visibility)}},[])
  useEffect(()=>{
    if(!host.current)return
    setFailed(false);setContextLost(false)
    try { engine.current=createRoom(host.current,{select:setSelected,project:(x,y,size)=>{if(character.current){character.current.style.left=x+'px';character.current.style.top=y+'px';character.current.style.width=Math.max(70,size*1.13)+'px'}},lost:()=>setContextLost(true),restored:()=>setContextLost(false),move:room.setDraft,notice:setNotice,touch:()=>setGreeting(true)}) }
    catch {setFailed(true)}
    return()=>{engine.current?.dispose();engine.current=null}
  },[generation])
  useEffect(()=>{engine.current?.environment(roomEnvironment(period,weather,new Date(minute)),lamp)},[period,weather,lamp,minute,generation])
  useEffect(()=>{engine.current?.layout(room.draft)},[room.draft,generation])
  useEffect(()=>{engine.current?.editing(editing&&!room.busy&&!taking)},[editing,room.busy,taking,generation])
  useEffect(()=>{engine.current?.active(visible&&!failed)},[visible,failed,generation])
  useEffect(()=>{
    if(!visible)return
    setMinute(Date.now());const timer=setInterval(()=>setMinute(Date.now()),60_000);return()=>clearInterval(timer)
  },[visible])
  useEffect(()=>{
    if(!visible)return
    const controller=new AbortController();let pending=false
    async function poll(){if(pending)return;pending=true;try{const state=await api<{state:string;label:string}>('/companion',{signal:controller.signal});if(!controller.signal.aborted){setActivity(roomActivity(state));setRuntime(state.state)}}catch{if(!controller.signal.aborted)setActivity({animation:'look',label:'暂时联系不上鱼塘，房间还在'})}finally{pending=false}}
    void poll();const timer=setInterval(()=>void poll(),15_000);return()=>{controller.abort();clearInterval(timer)}
  },[visible])
  useEffect(()=>{try{localStorage.setItem('fish.room.activity',mode)}catch{}engine.current?.behavior(roomIntent(runtime,mode,new Date(minute)))},[runtime,mode,minute,generation])
  useEffect(()=>{if(!greeting)return;const timer=setTimeout(()=>setGreeting(false),3200);return()=>clearTimeout(timer)},[greeting])
  useEffect(()=>{window.dispatchEvent(new CustomEvent('fish.room.editing',{detail:editing}));return()=>{window.dispatchEvent(new CustomEvent('fish.room.editing',{detail:false}))}},[editing])
  useEffect(()=>{if(!visible)return;const publish=()=>{const state=engine.current?.residentState();if(state){setResident(old=>old.pose===state.pose&&old.goal===state.goal?old:{pose:state.pose,goal:state.goal});const key=JSON.stringify([state.pose,state.goal,mode,Math.floor(Date.now()/15000)]);if(lastPublished.current!==key){lastPublished.current=key;window.dispatchEvent(new CustomEvent('fish.room.pose',{detail:{pose:state.pose,goal:state.goal,mode}}))}}};publish();const timer=setInterval(publish,1000);return()=>{clearInterval(timer);window.dispatchEvent(new CustomEvent('fish.room.pose',{detail:null}))}},[visible,mode,generation])
  function place(surface:string){if(!selected||!(selected in objects))return;const id=selected as ObjectId,[x,z]=objects[id].presets[surface];try{room.setDraft(placeObject(room.draft,id,{surface,x,z,rotation:room.draft[id].rotation}));room.setError('')}catch(e){room.setError((e as Error).message)}}
  function rotate(){if(!selected||!(selected in objects))return;const id=selected as ObjectId;try{room.setDraft(placeObject(room.draft,id,{...room.draft[id],rotation:(room.draft[id].rotation+90)%360}));room.setError('')}catch(e){room.setError((e as Error).message)}}
  async function capture(view:'room'|'window'){
    if(!room.saved||room.dirty||taking||room.busy||!atmosphere.ready)return;setTaking(true);room.setError('')
    try{
      const environment={period:sceneEnvironment.period,weather,lamp},current=engine.current
      if(!current)throw Error('小屋还没有准备好。')
      await current.ready;current.layout(room.saved.layout);current.environment(roomEnvironment(period,weather,new Date(minute)),lamp)
      const old=pendingPhoto.current
      if(!old||old.revision!==room.base||old.view!==view||JSON.stringify(old.environment)!==JSON.stringify(environment))pendingPhoto.current={operation_id:crypto.randomUUID(),revision:room.base,view,environment,image:current.photo(view)}
      const result=await api<RoomPhoto>('/room/photos',{method:'POST',body:JSON.stringify(pendingPhoto.current)});pendingPhoto.current=null;room.rememberPhoto(result);setPhoto(result)
    }catch(e){room.setError((e as Error).message)}finally{setTaking(false)}
  }
  const slot=selected?slots[selected]:undefined
  return <section className="room-page" aria-label="大肥鱼的小屋">
    <header className="room-heading"><div><span className="room-eyebrow">A LITTLE PLACE OF HER OWN</span><h1>大肥鱼的小屋<span>01</span></h1><p>留一扇窗，也留一点慢慢生活的空间。</p></div><button className={'room-button '+(settings?'selected':'')} aria-expanded={settings} onClick={()=>setSettings(v=>!v)}><SlidersHorizontal size={16}/>房间氛围</button></header>
    {settings&&<div className="room-settings"><div role="group" aria-label="小屋时段">{[{id:'auto',name:'跟随时间',icon:Sun},{id:'day',name:'白天',icon:Sun},{id:'dusk',name:'黄昏',icon:Sunset},{id:'night',name:'夜晚',icon:Moon}].map(x=><button key={x.id} aria-pressed={period===x.id} onClick={()=>setPeriod(x.id)}><x.icon size={15}/>{x.name}</button>)}</div><div role="group" aria-label="小屋天气氛围">{[{id:'clear',name:'晴',icon:Sun},{id:'rain',name:'雨',icon:CloudRain},{id:'snow',name:'雪',icon:Snowflake}].map(x=><button key={x.id} aria-pressed={weather===x.id} onClick={()=>setWeather(x.id)}><x.icon size={15}/>{x.name}</button>)}</div><span>天气为小屋氛围 · 自动时段按北京时间</span></div>}
    <div className="room-actions"><button className={'room-button '+(editing?'selected':'')} aria-pressed={editing} onClick={()=>setEditing(v=>!v)} disabled={!room.saved||room.busy||taking}><Move size={16}/>{editing?'结束布置':'布置小屋'}</button>{(editing||room.dirty)&&<><button className="room-button" disabled={!room.dirty||room.busy||taking} onClick={()=>void room.update('save')}><Save size={15}/>{room.busy?'正在保存…':'保存布置'}</button><button className="room-button" disabled={!room.saved?.can_undo||room.dirty||room.busy||taking} onClick={()=>void room.update('undo')}><Undo2 size={15}/>撤销上次保存</button><button className="room-text-link" disabled={room.busy} onClick={()=>void room.reload()}>读取已保存布置</button><button className="room-text-link" disabled={room.busy||taking} onClick={()=>void room.update('reset')}>恢复默认</button></>}<div className="room-photo-actions"><button className="room-button" disabled={!room.saved||room.dirty||taking||room.busy||failed||contextLost||!atmosphere.ready} onClick={()=>void capture('room')}><Camera size={16}/>{taking?'拍照中…':'拍张全景'}</button><button className="room-button" disabled={!room.saved||room.dirty||taking||room.busy||failed||contextLost||!atmosphere.ready} onClick={()=>void capture('window')}>拍窗边</button></div></div>
    {(room.error||atmosphere.error||notice||room.dirty)&&<div className="room-notice" role={room.error?'alert':'status'}>{room.error||atmosphere.error||notice||'布置还没有保存，草稿会留在本机。保存后就可以拍照。'}{room.error&&<button onClick={()=>void room.reload()} disabled={room.busy}>重新读取</button>}</div>}
    {editing&&<div className="room-edit-palette" role="group" aria-label="选择要布置的物品">{(Object.keys(objects) as ObjectId[]).map(id=><button key={id} aria-pressed={selected===id} onClick={()=>setSelected(id)}>{objects[id].label}</button>)}<span>可以拖动物品，或点物品选择放置位置。</span></div>}
    <div className="room-life-controls"><span>{mode==='auto'?'随她活动':mode==='walk'?'想在屋里走走':mode==='desk'?'待在电脑前':'去床上歇会儿'}</span><details className="room-interaction"><summary className="room-button">互动<ChevronDown size={15}/></summary><div className="room-interaction-menu" role="group" aria-label="小屋人物活动">{[{id:'auto',text:'随她活动'},{id:'walk',text:'屋里走走'},{id:'desk',text:'去电脑前'},{id:'sleep',text:'去床上歇会儿'}].map(item=><button className={'room-button '+(mode===item.id?'selected':'')} key={item.id} aria-pressed={mode===item.id} onClick={event=>{setMode(item.id);event.currentTarget.closest('details')?.removeAttribute('open')}}>{item.text}</button>)}<small>手选会保留，选“随她活动”恢复自动。</small></div></details></div>
    <div className="room-card">
      <div className="room-scene-label"><span className="room-dot"/>{sceneEnvironment.label}<span className="room-scene-number">海边小屋</span></div>
      <div className="room-stage" ref={host} data-period={sceneEnvironment.period} data-pose={resident.pose} data-goal={resident.goal}>
        <div ref={character} className="room-character-anchor" hidden={failed||contextLost}>
        <button className="room-character" aria-label="摸摸大肥鱼" onClick={()=>setGreeting(true)}>
          {greeting&&<span className="room-hello">爹，进来坐会儿？</span>}
          <span className="room-touch-target" aria-hidden="true"/>
        </button></div>
        {(failed||contextLost)&&<div className="room-recovery" role="alert"><Moon size={28}/><strong>{contextLost?'小屋的画面暂停了':'小屋画面暂时没有打开'}</strong><p>可以重新打开画面，聊天和记忆仍然保留。</p><button className="room-button" onClick={()=>setGeneration(v=>v+1)}><RotateCcw size={15}/>重新打开小屋</button></div>}
        {slot&&<aside className="room-inspect" aria-label={slot.title}><button className="room-inspect-close" aria-label="关闭物品介绍" onClick={()=>setSelected(null)}><X size={16}/></button><span className="room-eyebrow">A LITTLE CORNER</span><h2>{slot.title}</h2><p>{slot.description}</p>{!editing&&(selected==='desk'||selected==='book'||selected==='shelf')&&<RoomContents key={selected} kind={selected==='desk'?'desk':'memory'} onMemory={()=>onNavigate('memory')}/>}{editing&&selected&&selected in objects&&<div className="room-placement"><span>放到</span>{objects[selected as ObjectId].surfaces.map(surface=><button key={surface} disabled={room.busy||taking} aria-pressed={room.draft[selected as ObjectId].surface===surface} onClick={()=>place(surface)}>{surfaces[surface].label}</button>)}<button onClick={rotate} disabled={room.busy||taking}><RotateCw size={14}/>转 90°</button><button disabled={room.dirty||room.busy||taking} aria-pressed={room.saved?.locks[selected as ObjectId]||false} onClick={()=>void room.update('lock',{object:selected!,locked:!room.saved?.locks[selected as ObjectId]})}>{room.saved?.locks[selected as ObjectId]?<Lock size={14}/>:<Unlock size={14}/>}不让她挪</button></div>}{selected==='lamp'&&<button className="room-button" aria-pressed={lamp} onClick={()=>setLamp(v=>!v)}><Lamp size={15}/>{lamp?'关掉台灯':'打开台灯'}</button>}{selected==='shelf'&&onOpenStarMap&&<button className="room-text-link" onClick={onOpenStarMap}>打开记忆星图<ArrowUpRight size={15}/></button>}{slot.destination&&<button className="room-text-link" onClick={()=>onNavigate(slot.destination!)}>{slot.link}<ArrowUpRight size={15}/></button>}</aside>}
      </div>
      <footer className="room-scene-toolbar"><span>拖动转视角 · ⌘/Ctrl + 滚轮缩放</span><div><button className="room-icon" aria-label="缩小小屋" onClick={()=>engine.current?.zoom(-.1)}><Minus size={16}/></button><button className="room-icon" aria-label="放大小屋" onClick={()=>engine.current?.zoom(.1)}><Plus size={16}/></button><button className="room-icon" aria-label={lamp?'关掉小屋台灯':'打开小屋台灯'} aria-pressed={lamp} onClick={()=>setLamp(v=>!v)}><Lamp size={17}/></button><button className="room-icon" aria-label="恢复小屋视角" onClick={()=>engine.current?.reset()}><RotateCcw size={16}/></button></div></footer>
    </div>
    <div className="room-bottom"><div className="room-presence"><img src="/pet/idle-poster.png" alt=""/><div><span>她这会儿</span><strong>{resident.pose==='walk'?'在屋里溜达':resident.pose==='sit'?(['surfing','working'].includes(runtime)?'在电脑前 · '+activity.label:'在电脑前坐坐'):resident.pose==='sleep'?'在床上睡会儿':activity.label}</strong></div><button className="room-text-link" onClick={()=>onNavigate('chat')}>和她聊聊<ArrowUpRight size={16}/></button></div><div className="room-corners" role="group" aria-label="看看房间里的角落"><button onClick={()=>setSelected('desk')}>书桌</button><button onClick={()=>setSelected('shelf')}>书架</button><button onClick={()=>setSelected('window')}>窗边</button></div></div>
    {!!room.saved?.actions.length&&<div className="room-action-note"><span>最近的布置</span>{room.saved.actions.slice(0,3).map(a=><p key={a.id}>{a.actor==='assistant'?'她':'你'}把{objects[a.object].label}放到了{surfaces[a.to.surface].label}<time>{new Date(a.created_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</time></p>)}</div>}
    <RoomLife/>
    <RoomAlbum recent={room.saved?.photos||[]} incoming={photo} onIncomingClose={()=>setPhoto(null)} onAttachPhoto={onAttachPhoto} onChanged={()=>void room.refreshPhotos()}/>
    <p className="room-footnote">小屋里的光、雨和日常动作在本机运行。角色与动画署名见应用「关于大肥鱼」。</p>
  </section>
}
export default memo(RoomPage)
