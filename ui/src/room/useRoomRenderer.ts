import {useEffect} from 'react'
import {api} from '../api'
import {ensureAtmosphere} from './atmosphere'
import type {Layout} from './layout.mjs'
export interface CaptureJob {character_intent?:string;id:string;lease:string;view:'room'|'window';revision:number;layout:Layout;environment:{period:string;weather:string;lamp:boolean}}
export function useRoomRenderer(enabled:boolean){
  useEffect(()=>{
    if(!enabled)return;const abort=new AbortController(),worker=crypto.randomUUID();let timer:ReturnType<typeof setTimeout>|undefined
    async function run(){
      try{await ensureAtmosphere()}catch{}
      while(!abort.signal.aborted){
        try{
          const {job}=await api<{job:CaptureJob|null}>('/room/render/claim',{method:'POST',signal:abort.signal,body:JSON.stringify({worker})});if(!job||abort.signal.aborted)continue
          try{const {renderRoomPhoto}=await import('./capture');if(abort.signal.aborted)break;const image=await renderRoomPhoto(job);if(abort.signal.aborted)break;await api('/room/render/complete',{method:'POST',signal:abort.signal,body:JSON.stringify({id:job.id,lease:job.lease,image})})}
          catch{if(!abort.signal.aborted)await api('/room/render/complete',{method:'POST',signal:abort.signal,body:JSON.stringify({id:job.id,lease:job.lease,error:'render_failed'})}).catch(()=>{})}
        }catch{if(!abort.signal.aborted)await new Promise<void>(resolve=>{const finish=()=>{clearTimeout(timer);abort.signal.removeEventListener('abort',finish);resolve()};timer=setTimeout(finish,2000);abort.signal.addEventListener('abort',finish,{once:true})})}
      }
    }
    void run();return()=>{abort.abort();clearTimeout(timer)}
  },[enabled])
}
