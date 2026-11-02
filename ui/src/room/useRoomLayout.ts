import {useEffect,useRef,useState} from 'react'
import {api} from '../api'
import {defaultLayout,validateLayout,type Layout} from './layout.mjs'
import type {RoomSnapshot,RoomPhoto} from './types'
const key='fish.room.layoutDraft'
export function useRoomLayout(){
  const [saved,setSaved]=useState<RoomSnapshot|null>(null),[draft,setDraft]=useState<Layout>(defaultLayout),[base,setBase]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const mounted=useRef(true)
  function accept(value:RoomSnapshot){setSaved(value);setDraft(value.layout);setBase(value.revision);try{localStorage.removeItem(key)}catch{}}
  async function reload(){setBusy(true);try{accept(await api<RoomSnapshot>('/room'));setError('')}catch(e){setError((e as Error).message)}finally{if(mounted.current)setBusy(false)}}
  useEffect(()=>{mounted.current=true;const abort=new AbortController();api<RoomSnapshot>('/room',{signal:abort.signal}).then(value=>{if(abort.signal.aborted)return;setSaved(value);let old;try{old=JSON.parse(localStorage.getItem(key)||'null');if(old&&Number.isSafeInteger(old.revision)){setDraft(validateLayout(old.layout));setBase(old.revision);if(old.revision!==value.revision)setError('另一个窗口更新了布置。你的草稿仍在，保存前请核对。');return}}catch{}setDraft(value.layout);setBase(value.revision)}).catch(e=>{if(!abort.signal.aborted)setError(e.message)});return()=>{mounted.current=false;abort.abort()}},[])
  const dirty=!!saved&&JSON.stringify(draft)!==JSON.stringify(saved.layout)
  useEffect(()=>{if(!saved)return;try{if(dirty)localStorage.setItem(key,JSON.stringify({revision:base,layout:draft}));else localStorage.removeItem(key)}catch{}},[draft,base,saved,dirty])
  async function update(action:'save'|'undo'|'reset'){
    if(!saved||busy)return;setBusy(true);setError('')
    try{const value=await api<RoomSnapshot>('/room',{method:'PUT',body:JSON.stringify({action,revision:base,operation_id:crypto.randomUUID(),...(action==='save'?{layout:draft}:{})})});if(mounted.current)accept(value)}catch(e){if(mounted.current)setError((e as Error).message)}finally{if(mounted.current)setBusy(false)}
  }
  function rememberPhoto(photo:RoomPhoto){setSaved(s=>s?{...s,photos:[photo,...s.photos.filter(p=>p.id!==photo.id)].slice(0,24)}:s)}
  return {saved,draft,setDraft,base,busy,error,setError,dirty,reload,update,rememberPhoto}
}
