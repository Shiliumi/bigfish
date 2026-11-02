import {useEffect,useRef,useState} from 'react'
import {api} from '../api'
import {validateAtmosphere,type Atmosphere} from './model.mjs'
type Stored={environment:Atmosphere|null;revision:number}
export function localAtmosphere():Atmosphere{
  try{return validateAtmosphere({period:localStorage.getItem('fish.room.period')||'auto',weather:localStorage.getItem('fish.room.weather')||'clear',lamp:localStorage.getItem('fish.room.lamp')!=='off'})}catch{return {period:'auto',weather:'clear',lamp:true}}
}
export async function ensureAtmosphere():Promise<Stored>{
  const value=await api<Stored>('/room/environment');if(value.environment)return value
  try{return await api<Stored>('/room/environment',{method:'PUT',body:JSON.stringify({revision:value.revision,environment:localAtmosphere()})})}
  catch(e){if((e as any).status===409)return api<Stored>('/room/environment');throw e}
}
export function useRoomAtmosphere(){
  const [value,setValue]=useState(localAtmosphere),[ready,setReady]=useState(false),[error,setError]=useState(''),version=useRef(0),sent=useRef(''),chain=useRef(Promise.resolve())
  useEffect(()=>{let active=true,timer:ReturnType<typeof setTimeout>;async function load(){try{const result=await ensureAtmosphere();if(!active)return;version.current=result.revision;sent.current=JSON.stringify(result.environment);setValue(result.environment!);setReady(true);setError('')}catch{if(active){setError('房间氛围暂未同步，正在重新连接。');timer=setTimeout(()=>void load(),5000)}}}void load();return()=>{active=false;clearTimeout(timer)}},[])
  useEffect(()=>{
    if(!ready)return;let active=true
    try{localStorage.setItem('fish.room.period',value.period);localStorage.setItem('fish.room.weather',value.weather);localStorage.setItem('fish.room.lamp',value.lamp?'on':'off')}catch{}
    chain.current=chain.current.then(async()=>{if(!active||sent.current===JSON.stringify(value))return
      try{const result=await api<Stored>('/room/environment',{method:'PUT',body:JSON.stringify({revision:version.current,environment:value})});version.current=result.revision;sent.current=JSON.stringify(value);if(active)setError('')}
      catch{try{const result=await api<Stored>('/room/environment');version.current=result.revision;if(active&&result.environment){sent.current=JSON.stringify(result.environment);setValue(result.environment)}}catch{}if(active)setError('房间氛围同步失败，已重新读取；请核对后再调整。')}
    });return()=>{active=false}
  },[value,ready])
  return {value,setValue,error,ready}
}
