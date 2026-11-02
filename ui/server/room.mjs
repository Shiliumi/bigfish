import {readFile,writeFile,rename,mkdir,unlink} from 'node:fs/promises';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {defaultLayout,validateLayout,layoutCaption,objects,placeObject} from '../src/room/layout.mjs';
import {validatePhoto} from './room-png.mjs';
const error=(text,status=400)=>Object.assign(new Error(text),{status});
const digest=value=>createHash('sha256').update(value).digest('hex');
export function createRoomStore(root){
  const folder=path.join(root,'data/room'),file=path.join(folder,'state.json');let pending=Promise.resolve();
  const locked=fn=>{const task=pending.then(fn);pending=task.catch(()=>{});return task;};
  async function load(){try{const s=JSON.parse(await readFile(file,'utf8'));if(s.schema!==1||!Number.isSafeInteger(s.revision)||s.revision<0||!Array.isArray(s.history)||!Array.isArray(s.receipts)||!Array.isArray(s.photos))throw Error();validateLayout(s.layout);s.locks??={cup:false,book:false,cushion:false};s.actions??=[];if(Object.keys(s.locks).sort().join()!=='book,cup,cushion'||Object.values(s.locks).some(v=>typeof v!=='boolean')||!Array.isArray(s.actions))throw Error();return s;}catch(e){if(e.code==='ENOENT')return {schema:1,revision:0,layout:defaultLayout(),history:[],receipts:[],photos:[],locks:{cup:false,book:false,cushion:false},actions:[]};throw error('小屋存档暂时无法读取，原文件已保留。',503);}}
  async function save(s){await mkdir(folder,{recursive:true,mode:0o700});const temp=file+'.'+randomUUID()+'.tmp';try{await writeFile(temp,JSON.stringify(s),{mode:0o600});await rename(temp,file);}finally{await unlink(temp).catch(()=>{});}}
  const publicPhoto=p=>({id:p.id,caption:p.caption,created_at:p.created_at,view:p.view,revision:p.revision,width:p.width,height:p.height,image_url:'/api/room/photos/'+p.id+'/image'});
  const snapshot=s=>({revision:s.revision,layout:s.layout,locks:s.locks,can_undo:s.history.length>0,photos:s.photos.slice(-24).reverse().map(publicPhoto),actions:s.actions.slice(-8).reverse()});
  function action(s,actor,id,from,to,operation_id){const value={id:'ra-'+digest(operation_id+id).slice(0,24),actor,object:id,from,to,revision:s.revision,created_at:new Date().toISOString()};s.actions.push(value);s.actions=s.actions.slice(-100);return value;}
  function receipt(s,data,fingerprint){if(typeof data.operation_id!=='string'||!/^[a-f0-9-]{36}$/.test(data.operation_id))throw error('请求标识不正确。');const old=s.receipts.find(r=>r.id===data.operation_id);if(old){if(old.hash!==fingerprint)throw error('同一请求的内容发生了变化。',409);return old;}}
  function revision(s,data){if(!Number.isSafeInteger(data.revision)||data.revision!==s.revision)throw error('房间布置已更新，请重新读取后再操作。',409);}
  function record(s,data,hash,extra={}){s.receipts.push({id:data.operation_id,hash,...extra});s.receipts=s.receipts.slice(-200);}
  return {
    snapshot:()=>locked(async()=>snapshot(await load())),
    update:data=>locked(async()=>{
      if(!data||typeof data!=='object'||Array.isArray(data))throw error('布置请求格式不正确。');
      if(!['save','undo','reset','lock'].includes(data.action))throw error('布置操作不支持。');
      const hash=digest(JSON.stringify(data)),s=await load();if(receipt(s,data,hash))return snapshot(s);revision(s,data);
      if(data.action==='lock'){if(!Object.hasOwn(objects,data.object)||typeof data.locked!=='boolean')throw error('锁定信息不正确。');s.locks[data.object]=data.locked;s.revision++;record(s,data,hash);await save(s);return snapshot(s);}
      const before=s.layout;
      let layout;if(data.action==='undo'){if(!s.history.length)throw error('还没有可以撤销的布置。');layout=validateLayout(s.history.at(-1));s.history.pop();}
      else {try{layout=validateLayout(data.action==='reset'?defaultLayout():data.layout);}catch(e){throw error(e.message);}if(JSON.stringify(layout)!==JSON.stringify(s.layout))s.history.push(s.layout);s.history=s.history.slice(-12);}
      s.layout=layout;s.revision++;for(const id of Object.keys(objects))if(JSON.stringify(before[id])!==JSON.stringify(layout[id]))action(s,'user',id,before[id],layout[id],data.operation_id);record(s,data,hash);await save(s);return snapshot(s);
    }),
    move:data=>locked(async()=>{
      if(!data||typeof data!=='object'||Array.isArray(data)||Object.keys(data).sort().join()!=='object,operation_id,revision,surface'||!Object.hasOwn(objects,data.object)||!Object.hasOwn(objects[data.object].presets,data.surface))throw error('这项房间动作不支持。');
      const hash=digest(JSON.stringify(data)),s=await load(),old=receipt(s,data,hash);if(old)return {ok:true,receipt:old.result};revision(s,data);
      if(s.locks[data.object])throw error('这件物品被你锁定了，她不能移动。',409);
      const [x,z]=objects[data.object].presets[data.surface],from=s.layout[data.object];let layout;
      try{layout=placeObject(s.layout,data.object,{surface:data.surface,x,z,rotation:from.rotation});}catch(e){throw error(e.message);}
      const changed=JSON.stringify(layout)!==JSON.stringify(s.layout);let result;
      if(changed){s.history.push(s.layout);s.history=s.history.slice(-12);s.layout=layout;s.revision++;result=action(s,'assistant',data.object,from,layout[data.object],data.operation_id);}
      else result={id:'ra-'+digest(data.operation_id+data.object).slice(0,24),actor:'assistant',object:data.object,from,to:from,revision:s.revision,changed:false,created_at:new Date().toISOString()};
      record(s,data,hash,{result});await save(s);return {ok:true,receipt:result};
    }),
    photo:data=>locked(async()=>{
      if(!data||typeof data!=='object'||Array.isArray(data))throw error('拍照请求格式不正确。');
      let image;try{image=validatePhoto(data.image);}catch(e){throw error(e.message);}
      if(!['room','window'].includes(data.view)||!['day','dusk','night'].includes(data.environment?.period)||!['clear','rain','snow'].includes(data.environment?.weather)||typeof data.environment?.lamp!=='boolean')throw error('拍照信息不正确。');
      const hash=digest(JSON.stringify({revision:data.revision,view:data.view,environment:data.environment,image:digest(image.bytes)})),s=await load(),old=receipt(s,data,hash);
      if(old){const p=s.photos.find(p=>p.id===old.photo_id);if(!p)throw error('照片记录暂时不可用。',503);return publicPhoto(p);}revision(s,data);
      const id='ph-'+digest(data.operation_id).slice(0,24),name=path.join(folder,id+'.png'),existing=s.photos.find(p=>p.id===id);if(existing){if(existing.hash!==hash)throw error('同一张照片的内容发生了变化。',409);return publicPhoto(existing);}await mkdir(folder,{recursive:true,mode:0o700});
      const created_at=new Date().toISOString(),p={id,hash,revision:s.revision,view:data.view,created_at,environment:data.environment,layout:s.layout,caption:(data.view==='window'?'窗边':'小屋全景')+' · '+({day:'白天',dusk:'黄昏',night:'夜晚'}[data.environment.period])+' · '+({clear:'晴天',rain:'雨天',snow:'雪天'}[data.environment.weather])+'。'+layoutCaption(s.layout)+'。',width:image.width,height:image.height};
      const temp=name+'.'+randomUUID()+'.tmp';try{await writeFile(temp,image.bytes,{mode:0o600});await rename(temp,name);s.photos.push(p);record(s,data,hash,{photo_id:id});await save(s);}finally{await unlink(temp).catch(()=>{});}return publicPhoto(p);
    }),
    detail:id=>locked(async()=>{const s=await load(),p=s.photos.find(p=>p.id===id);if(!p)throw error('这张照片不存在。',404);return publicPhoto(p);}),
    image:id=>locked(async()=>{const s=await load();if(!/^ph-[a-f0-9]{24}$/.test(id)||!s.photos.some(p=>p.id===id))throw error('这张照片不存在。',404);try{return await readFile(path.join(folder,id+'.png'));}catch{throw error('照片文件暂时无法读取。',503);}}),
  };
}
