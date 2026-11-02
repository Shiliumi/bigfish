import {createRoom} from './scene'
import {roomEnvironment} from './environment.mjs'
import type {CaptureJob} from './useRoomRenderer'
export async function renderRoomPhoto(job:CaptureJob){
  const host=document.createElement('div');host.setAttribute('aria-hidden','true');host.style.cssText='position:fixed;left:-12000px;top:0;width:1024px;height:768px;opacity:0;pointer-events:none;overflow:hidden;'
  document.body.append(host);let room:ReturnType<typeof createRoom>|undefined
  try{
    const character=new Image();character.src='/pet/idle-poster.png';await character.decode()
    room=createRoom(host,{select:()=>{},project:()=>{},lost:()=>{},restored:()=>{}})
    room.environment(roomEnvironment(job.environment.period,job.environment.weather),job.environment.lamp);room.layout(job.layout);room.active(true)
    return room.photo(job.view,character)
  }finally{room?.dispose();host.remove()}
}
