import {createRoom} from './scene'
import {roomEnvironment} from './environment.mjs'
import type {CaptureJob} from './useRoomRenderer'
export async function renderRoomPhoto(job:CaptureJob){
  const host=document.createElement('div');host.setAttribute('aria-hidden','true');host.style.cssText='position:fixed;left:-12000px;top:0;width:1024px;height:768px;opacity:0;pointer-events:none;overflow:hidden;'
  document.body.append(host);let room:ReturnType<typeof createRoom>|undefined
  try{
    room=createRoom(host,{select:()=>{},project:()=>{},lost:()=>{},restored:()=>{}})
    room.environment(roomEnvironment(job.environment.period,job.environment.weather),job.environment.lamp);room.layout(job.layout);room.active(true)
    await room.ready;room.behavior(job.character_intent||'idle',true);return room.photo(job.view)
  }finally{room?.dispose();host.remove()}
}
