import { readFile, writeFile, mkdir, rename, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { SOCIAL_DEFAULTS, deliveryDecision, greetingCandidates } from './social.mjs';
export { SOCIAL_DEFAULTS, deliveryDecision } from './social.mjs';

export function createInbox(root, clock = Date.now) {
  const directory=path.join(root,'data'), store=path.join(directory,'inbox.json'), spool=path.join(directory,'outbox');
  let serial=Promise.resolve(), lastActivity=0;
  const exclusive=action=>{const operation=serial.then(action);serial=operation.catch(()=>{});return operation;};
  const read=async()=>{
    let data;try{data=JSON.parse(await readFile(store,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;data={messages:[],processed:[]};}
    return {...data,settings:{...SOCIAL_DEFAULTS,...data.settings},pending:data.pending||[]};
  };
  const save=async data=>{await mkdir(directory,{recursive:true});const tmp=store+'.'+randomUUID();await writeFile(tmp,JSON.stringify(data,null,2)+'\n',{mode:0o600});await rename(tmp,store);};
  async function validated(file,now){
    const full=path.join(spool,file),info=await stat(full);if(!info.isFile()||info.size>12000)return null;
    const data=JSON.parse(await readFile(full,'utf8'));
    // 学习搭子的问候：本机生成，没有来源链接，不参与冲浪来源核验。
    if(data.kind==='study'){
      if(typeof data.text!=='string'||data.text.trim().length<8||data.text.length>320)return null;
      const timestamp=Date.parse(data.created_at);if(!Number.isFinite(timestamp)||timestamp>now+60000)return null;
      return {kind:'study',text:data.text.trim(),source_title:String(data.source_title||'学习搭子').slice(0,120),created_at:new Date(timestamp).toISOString()};
    }
    if(data.worth_sharing!==true||typeof data.text!=='string'||data.text.trim().length<8||data.text.length>320||typeof data.why_share!=='string'||data.why_share.length<6)return null;
    const url=new URL(data.source_url);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)return null;
    const timestamp=Date.parse(data.created_at);if(!Number.isFinite(timestamp)||timestamp>now+60000)return null;
    if(!/^reports\/\d{4}-\d{2}-\d{2}\/[\w-]+\.md$/.test(data.report_path||''))return null;
    const report=await readFile(path.join(root,data.report_path),'utf8'),surf=JSON.parse(await readFile(path.join(directory,'surf-state.json'),'utf8'));
    if(!report.includes(data.source_url)||!surf.visited?.some(v=>v.url===data.source_url))return null;
    let sticker;if(/^[a-f0-9]{16}$/.test(data.sticker_id||'')){
      const library=JSON.parse(await readFile(path.join(directory,'stickers/library.json'),'utf8').catch(()=>' {"items":[]}'));
      if(library.items.some(item=>item.id===data.sticker_id))sticker=data.sticker_id;
    }
    return {kind:'surf',sticker_id:sticker,text:data.text.trim(),source_url:data.source_url,source_title:String(data.source_title||'刚看到的内容').slice(0,120),report_path:data.report_path,created_at:new Date(timestamp).toISOString()};
  }
  return {
    activity(){lastActivity=clock();},
    snapshot:()=>exclusive(async()=>{const data=await read();return {settings:data.settings,messages:data.messages,unread:data.messages.filter(m=>!m.read_at).length};}),
    settings:(enabled,greetings)=>exclusive(async()=>{if(typeof enabled!=='boolean')throw Error('请选择是否开启主动招呼。');const data=await read();data.settings.enabled=enabled;if(typeof greetings==='boolean')data.settings.greetings=greetings;await save(data);return data.settings;}),
    update:(id,updates)=>exclusive(async()=>{const data=await read(),message=data.messages.find(m=>m.id===id);if(!message)return null;if(updates.read)message.read_at=new Date(clock()).toISOString();if(updates.notified)message.notified_at=new Date(clock()).toISOString();if(updates.pet_notified)message.pet_notified_at=new Date(clock()).toISOString();if(updates.session_id&&typeof updates.session_id==='string'&&updates.session_id.length<200)message.session_id=updates.session_id;await save(data);return message;}),
    // Local routines use this directly; no unauthenticated publishing endpoint exists.
    queueLocal: candidate=>exclusive(async()=>{const data=await read();if(!['balance'].includes(candidate.kind)||typeof candidate.text!=='string'||!candidate.dedupe_key)throw Error('未知的本地招呼');if(data.messages.some(m=>m.dedupe_key===candidate.dedupe_key)||data.pending.some(m=>m.dedupe_key===candidate.dedupe_key))return;data.pending.push({...candidate,created_at:new Date(clock()).toISOString()});await save(data);}),
    cancelPending:kind=>exclusive(async()=>{const data=await read();const previous=data.pending.length;data.pending=data.pending.filter(m=>m.kind!==kind);if(previous!==data.pending.length)await save(data);}),
    tick:()=>exclusive(async()=>{
      const data=await read(),now=clock();let changed=false;
      const deliver=(candidate,key)=>{
        const decision=deliveryDecision(candidate,data.messages,data.settings,now,lastActivity);
        if(decision==='wait')return false;
        if(key)data.processed.push(key);
        if(decision==='send')data.messages.push({...candidate,id:randomUUID(),sent_at:new Date(now).toISOString(),read_at:null,notified_at:null,pet_notified_at:null});
        changed=true;return true;
      };
      const pending=[];for(const candidate of data.pending)if(!deliver(candidate))pending.push(candidate);data.pending=pending;
      for(const candidate of greetingCandidates(now,data.settings))if(!data.processed.includes(candidate.dedupe_key))deliver(candidate,candidate.dedupe_key);
      const files=(await readdir(spool).catch(error=>{if(error.code==='ENOENT')return [];throw error;})).filter(f=>/^[\w-]+\.json$/.test(f)).sort();
      for(const file of files){
        if(data.processed.includes(file))continue;
        let candidate;try{candidate=await validated(file,now);}catch{continue;}
        if(!candidate){data.processed.push(file);changed=true;continue;}deliver(candidate,file);
      }
      if(changed)await save(data);
    }),
  };
}
