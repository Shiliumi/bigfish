import {useEffect,useRef,useState} from 'react'
import {api} from '../api'
import {defaultLayout,validateLayout,type Layout} from './layout.mjs'
import type {RoomSnapshot,RoomPhoto} from './types'
const key='fish.room.layoutDraft'
export function useRoomLayout(watch=true){
  const [saved,setSaved]=useState<RoomSnapshot|null>(null),[draft,setDraft]=useState<Layout>(defaultLayout),[base,setBase]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const mounted=useRef(true)
  function accept(value:RoomSnapshot){setSaved(value);setDraft(value.layout);setBase(value.revision);try{localStorage.removeItem(key)}catch{}}
  async function reload(){setBusy(true);try{accept(await api<RoomSnapshot>('/room'));setError('')}catch(e){setError((e as Error).message)}finally{if(mounted.current)setBusy(false)}}
  useEffect(()=>{mounted.current=true;const abort=new AbortController();api<RoomSnapshot>('/room',{signal:abort.signal}).then(value=>{if(abort.signal.aborted)return;setSaved(value);let old;try{old=JSON.parse(localStorage.getItem(key)||'null');if(old&&Number.isSafeInteger(old.revision)){setDraft(validateLayout(old.layout));setBase(old.revision);if(old.revision!==value.revision)setError('另一个窗口更新了布置。你的草稿仍在，保存前请核对。');return}}catch{}setDraft(value.layout);setBase(value.revision)}).catch(e=>{if(!abort.signal.aborted)setError(e.message)});return()=>{mounted.current=false;abort.abort()}},[])
  const dirty=!!saved&&JSON.stringify(draft)!==JSON.stringify(saved.layout)
  const current=useRef({saved,dirty,busy});current.current={saved,dirty,busy}
  useEffect(()=>{
    if(!watch)return;const controller=new AbortController();let pending=false
    async function refresh(){if(pending||current.current.busy||document.hidden||(window as any).__FISH_WINDOW_VISIBLE__===false)return;pending=true
      try{const value=await api<RoomSnapshot>('/room',{signal:controller.signal}),state=current.current;if(controller.signal.aborted||!state.saved||value.revision<state.saved.revision)return
        if(value.revision!==state.saved.revision){if(state.dirty){setError('另一个窗口更新了布置。你的草稿仍在，保存前请核对。');return}accept(value)}
        else if(JSON.stringify(value.photos)!==JSON.stringify(state.saved.photos))setSaved(value)
      }catch{}finally{pending=false}}
    const timer=setInterval(()=>void refresh(),10_000);window.addEventListener('fish:window-visibility',refresh);document.addEventListener('visibilitychange',refresh)
    return()=>{controller.abort();clearInterval(timer);window.removeEventListener('fish:window-visibility',refresh);document.removeEventListener('visibilitychange',refresh)}
  },[watch])
  useEffect(()=>{if(!saved)return;try{if(dirty)localStorage.setItem(key,JSON.stringify({revision:base,layout:draft}));else localStorage.removeItem(key)}catch{}},[draft,base,saved,dirty])
  async function update(action:'save'|'undo'|'reset'|'lock',extra?:{object:string;locked:boolean}){
    if(!saved||busy)return;setBusy(true);setError('')
    try{const value=await api<RoomSnapshot>('/room',{method:'PUT',body:JSON.stringify({action,revision:base,operation_id:crypto.randomUUID(),...(action==='save'?{layout:draft}:{}),...extra})});if(mounted.current)accept(value)}catch(e){if(mounted.current)setError((e as Error).message)}finally{if(mounted.current)setBusy(false)}
  }
  function rememberPhoto(photo:RoomPhoto){setSaved(s=>s?{...s,photos:[photo,...s.photos.filter(p=>p.id!==photo.id)].slice(0,24)}:s)}
  return {saved,draft,setDraft,base,busy,error,setError,dirty,reload,update,rememberPhoto}
}
