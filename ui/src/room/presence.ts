import {useEffect} from 'react'
import {api} from '../api'
export function useRoomPresence(){useEffect(()=>{
  let editing=false,character:Record<string,unknown>|null=null,stopped=false,pending=false,again=false,timer:ReturnType<typeof setTimeout>|undefined
  async function send(){if(stopped)return;if(pending){again=true;return}pending=true
    const visible=!document.hidden&&(window as any).__FISH_WINDOW_VISIBLE__!==false
    try{await api('/room/life/presence',{method:'POST',body:JSON.stringify({draft:!!localStorage.getItem('fish.room.layoutDraft'),editing:editing&&visible,character:visible?character:null})})}catch{}finally{pending=false;if(again){again=false;void send()}}
  }
  const schedule=()=>{clearTimeout(timer);timer=setTimeout(()=>void send(),150)}
  const edit=(e:Event)=>{editing=Boolean((e as CustomEvent).detail);schedule()},pose=(e:Event)=>{character=(e as CustomEvent).detail;schedule()}
  window.addEventListener('fish.room.draft',schedule);window.addEventListener('fish.room.editing',edit);window.addEventListener('fish.room.pose',pose);window.addEventListener('fish:window-visibility',schedule);document.addEventListener('visibilitychange',schedule)
  void send();const heartbeat=setInterval(()=>void send(),15000)
  return()=>{stopped=true;clearTimeout(timer);clearInterval(heartbeat);window.removeEventListener('fish.room.draft',schedule);window.removeEventListener('fish.room.editing',edit);window.removeEventListener('fish.room.pose',pose);window.removeEventListener('fish:window-visibility',schedule);document.removeEventListener('visibilitychange',schedule)}
},[])}
