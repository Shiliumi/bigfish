import {randomUUID} from 'node:crypto';
import {roomEnvironment} from '../src/room/environment.mjs';
const fail=(message,status=400)=>Object.assign(new Error(message),{status});
const uuid=value=>typeof value==='string'&&/^[a-f0-9-]{36}$/.test(value);

// Only a live, authenticated application renderer can fulfil a request. No desktop
// screenshot, camera, old gallery fallback, or model-generated picture is involved.
export function createRoomCapture(room,{timeout=25_000,wait=15_000,intent=async()=> 'idle'}={}){
  const jobs=new Map(),waiting=new Map();let closed=false;
  const take=worker=>{for(const job of jobs.values())if(job.state==='queued'){job.state='rendering';job.worker=worker;return {id:job.id,lease:job.lease,view:job.view,layout:job.layout,environment:job.environment,revision:job.revision,character_intent:job.character_intent};}return null;};
  function dispatch(){for(const [worker,entry]of waiting){const job=take(worker);if(!job)break;entry.finish(job);}}
  function finish(job,error,result){if(['done','failed'].includes(job.state))return;clearTimeout(job.timer);job.state=error?'failed':'done';job.result=result;job.error=error;error?job.reject(error):job.resolve(result);}
  return {
    async request(data){
      if(closed)throw fail('小屋拍照服务正在重启。',503);
      if(!data||Object.keys(data).sort().join()!=='operation_id,revision,view'||!uuid(data.operation_id)||!Number.isSafeInteger(data.revision)||!['room','window'].includes(data.view))throw fail('拍照请求不正确。');
      const fingerprint=JSON.stringify({revision:data.revision,view:data.view}),old=jobs.get(data.operation_id);if(old){if(old.fingerprint!==fingerprint)throw fail('同一拍照请求的内容发生了变化。',409);return old.promise;}
      // Bound retained receipts without expiring or reassigning an in-flight renderer.
      for(const [id,job]of jobs)if(['done','failed'].includes(job.state)&&Date.now()-job.started>300_000)jobs.delete(id);
      if([...jobs.values()].filter(j=>!['done','failed'].includes(j.state)).length>=4||jobs.size>=128)throw fail('小屋正在拍照，请稍后再试。',429);
      const snapshot=await room.snapshot();if(snapshot.revision!==data.revision)throw fail('房间布置已更新，请重新查看再拍照。',409);
      // Two requests can both be awaiting the snapshot; recheck before reserving the ID.
      if(jobs.has(data.operation_id)){const existing=jobs.get(data.operation_id);if(existing.fingerprint!==fingerprint)throw fail('同一拍照请求的内容发生了变化。',409);return existing.promise;}
      if(closed||[...jobs.values()].filter(j=>!['done','failed'].includes(j.state)).length>=4||jobs.size>=128)throw fail('小屋拍照服务暂不可用，请稍后再试。',503);
      const settings=snapshot.environment||{period:'auto',weather:'clear',lamp:true},period=roomEnvironment(settings.period,settings.weather).period;
      const character_intent=await intent();
      if(jobs.has(data.operation_id)){const existing=jobs.get(data.operation_id);if(existing.fingerprint!==fingerprint)throw fail('同一拍照请求的内容发生了变化。',409);return existing.promise;}
      if(closed)throw fail('小屋拍照服务正在重启。',503);
      const job={character_intent,id:data.operation_id,fingerprint,view:data.view,revision:data.revision,layout:snapshot.layout,environment:{period,weather:settings.weather,lamp:settings.lamp},state:'queued',started:Date.now(),lease:randomUUID()};
      job.promise=new Promise((resolve,reject)=>{job.resolve=resolve;job.reject=reject;});jobs.set(job.id,job);
      job.timer=setTimeout(()=>finish(job,fail('小屋画面暂未响应，照片没有拍成；请打开应用后再试。',503)),timeout);dispatch();return job.promise;
    },
    async claim(worker,signal){
      if(!uuid(worker)||closed)throw fail('房间渲染连接不可用。',503);if(signal?.aborted)return null;
      const job=take(worker);if(job)return job;if(waiting.has(worker))throw fail('这个渲染连接已在等待。',409);if(waiting.size>=8)throw fail('房间渲染连接过多。',429);
      return new Promise(resolve=>{let timer;const finish=value=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);waiting.delete(worker);resolve(value);},abort=()=>finish(null);waiting.set(worker,{finish});timer=setTimeout(()=>finish(null),wait);signal?.addEventListener('abort',abort,{once:true});});
    },
    async complete(data){
      const job=jobs.get(data?.id);if(!job||job.lease!==data.lease||job.state!=='rendering')throw fail('拍照请求已失效，未使用这张画面。',409);
      if(data.error){finish(job,fail('小屋画面没有成功渲染，请重新打开应用后再试。',503));return {ok:false};}
      if(typeof data.image!=='string')throw fail('拍照画面缺失。');job.state='saving';clearTimeout(job.timer);
      try{const photo=await room.photo({operation_id:job.id,revision:job.revision,view:job.view,environment:job.environment,image:data.image});const result={ok:true,photo,markdown:'![大肥鱼的小屋]('+photo.image_url+')'};finish(job,null,result);return result;}
      catch(error){finish(job,error);throw error;}
    },
    close(){closed=true;for(const job of jobs.values())finish(job,fail('小屋拍照服务已重启，请重新拍照。',503));for(const entry of waiting.values())entry.finish(null);},
  };
}
