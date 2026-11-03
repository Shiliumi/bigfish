import {readFile,writeFile,rename,mkdir,readdir,lstat,realpath,unlink} from 'node:fs/promises';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {objects} from '../src/room/layout.mjs';
import {readInterestControls,interestBlocked} from './interest-controls.mjs';
const hash=value=>createHash('sha256').update(value).digest('hex');
const error=(message,status=400)=>Object.assign(new Error(message),{status});
const clean=(value,min=1,max=240)=>typeof value==='string'&&value.trim().length>=min&&value.trim().length<=max&&!/sk-[\w-]{16,}|Bearer\s+[\w.-]{16,}/i.test(value)?value.trim():null;
const utcDay=t=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(t);
async function json(file,fallback){try{const info=await lstat(file);if(info.isSymbolicLink()||info.size>2*1024*1024)throw Error('文件不可读取');return JSON.parse(await readFile(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
async function atomic(file,value){await mkdir(path.dirname(file),{recursive:true,mode:0o700});const temp=file+'.'+randomUUID();try{await writeFile(temp,JSON.stringify(value),{mode:0o600});await rename(temp,file);}finally{await unlink(temp).catch(()=>{});}}

export function createRoomLife(root,{room,clock=Date.now,available=async()=>true,requirePresence=false}={}){
  const folder=path.join(root,'data/room-events'),file=path.join(root,'data/room/life.json');let serial=Promise.resolve(),presenceReady=!requirePresence;
  const locked=fn=>{const task=serial.then(fn);serial=task.catch(()=>{});return task;};
  async function load(){const s=await json(file,{schema:1,revision:0,enabled:true,guard:{draft:false,editing_until:0},wishes:[],receipts:[],moves:[],prepared:null});
    if(s.schema!==1||!Number.isSafeInteger(s.revision)||typeof s.enabled!=='boolean'||!Array.isArray(s.wishes)||!Array.isArray(s.receipts)||!Array.isArray(s.moves)||!s.guard||typeof s.guard.draft!=='boolean'||!Number.isFinite(s.guard.editing_until)||s.guard.editing_until<0)throw error('小屋生活记录暂时无法读取，原档案已保留。',503);return s;}
  async function verifyEvidence(event){
    if(!event||event.schema!==1||!/^browse-[a-f0-9]{16}$/.test(event.run_id)||event.id!=='rl-'+hash(event.run_id).slice(0,24)||!/^reports\/\d{4}-\d{2}-\d{2}\/[\w-]*surf[\w-]*\.md$/.test(event.report_path)||!Array.isArray(event.observation_ids)||!event.observation_ids.length||event.observation_ids.length>3)throw error('房间生活来源不正确。');
    const [receipt,state,surf,controls]=await Promise.all([json(path.join(root,'data/surf-completions',event.run_id+'.json'),null),json(path.join(root,'data/curiosity/state.json'),{}),json(path.join(root,'data/surf-state.json'),{}),readInterestControls(root)]);
    if(receipt?.status!=='committed')throw error('冲浪收尾尚未提交。',425);
    const relative='data/room-events/'+event.id+'.json',write=receipt.writes?.find(w=>w.path===relative);
    let original;for(const candidate of [path.join(root,relative),path.join(folder,'handled',event.id+'.json')]){try{const info=await lstat(candidate);if(info.isSymbolicLink()||info.size>12000)throw error('生活候选文件无效。');original=await readFile(candidate);break;}catch(e){if(e.code!=='ENOENT')throw e;}}
    if(!original||write?.sha256!==hash(original)||JSON.stringify(JSON.parse(original))!==JSON.stringify(event))throw error('生活候选与已提交的收尾不匹配。');
    const run=state.runs?.find(r=>r.id===event.run_id&&r.status==='finished');
    if(!run||run.report_path!==event.report_path||receipt.result?.report_path!==event.report_path||event.observation_ids.some(id=>!receipt.result?.observation_ids?.includes(id)))throw error('本轮回执与来源不匹配。');
    const obsFile=path.join(root,'data/personality/observations.jsonl'),info=await lstat(obsFile);if(info.isSymbolicLink()||info.size>4*1024*1024)throw error('观察档案需要整理后再核对。',503);
    const observations=(await readFile(obsFile,'utf8')).split('\n').flatMap(line=>{try{return[JSON.parse(line)];}catch{return[];}}),rows=event.observation_ids.map(id=>observations.find(o=>o.id===id));
    const reportFile=await realpath(path.join(root,event.report_path)),reportRoot=await realpath(path.join(root,'reports'));if(!reportFile.startsWith(reportRoot+path.sep)||(await lstat(reportFile)).size>512000)throw error('阅读报告不可核对。');
    const report=await readFile(reportFile,'utf8');
    for(const row of rows){let url;try{url=new URL(row?.url);}catch{throw error('阅读来源已失效。');}
      if(event.observation_hashes?.[row.id]!==hash(['id','url','report_path','seen_at','read_depth','observation','candidate_trait','reason'].map(k=>row[k]||'').join('\0')))throw error('阅读观察已更正，停止引用旧理由。');
      if(!['http:','https:'].includes(url.protocol)||url.username||url.password||!['body','comments','captions','video_with_captions'].includes(row.read_depth)||row.report_path!==event.report_path||!report.includes(row.url)||!surf.visited?.some(v=>v.url===row.url&&v.report===event.report_path)||interestBlocked(controls,run.thread_id,row.url,clock()))throw error('阅读来源已失效或相关兴趣已收起。');
    }
    return rows.map(o=>({id:o.id,url:o.url,report_path:event.report_path}));
  }
  async function evidence(event){try{return await verifyEvidence(event);}catch(e){if(e.code==='ENOENT')throw error('阅读来源已被移除，停止引用。',409);throw e;}}
  async function projection(s){const wishes=[];
    for(const w of s.wishes){let status=w.status,source=[];try{source=await evidence(w.event);}catch{status='source_unavailable';}
      if(['open','accepted'].includes(status)&&clock()>Date.parse(w.expires_at))status='expired';
      wishes.push(status==='source_unavailable'?{id:w.id,status,created_at:w.created_at}:{id:w.id,item:w.item,text:w.text,why:w.why,status,created_at:w.created_at,expires_at:w.expires_at,source});}
    const moves=[];for(const m of s.moves.slice(-5).reverse()){try{await evidence(m.event);const {event,...value}=m;moves.push(value);}catch{moves.push({id:m.id,created_at:m.created_at,object:m.object,surface:m.surface,why:'这次调整的阅读来源已收起，保留实际布置记录。',source_unavailable:true});}}
    return {revision:s.revision,enabled:s.enabled,mode:s.guard.character?.mode||'auto',character:s.guard.character&&clock()-s.guard.character.at<45000?s.guard.character:null,wishes:wishes.reverse(),moves,pause_reason:!presenceReady?'等应用核对布置草稿，再决定要不要挪':s.guard.draft?'还有未保存的布置，先不自己挪东西':s.guard.editing_until>clock()?'正在布置房间，先不挪':null};
  }
  async function finishPrepared(s){if(!s.prepared)return;const job=s.prepared;
    // Once the exact request is prepared, retries use its ID and original revision.
    // The room owner returns its receipt before version checks, so a crash cannot move twice.
    let result;try{await evidence(job.event);result=await room.move(job.request);}catch(e){if(!Number.isInteger(e.status)||e.status===425||e.status>=500)throw e;result={ok:false,error:e.message};}
    if(result.ok&&result.receipt?.changed!==false){s.moves.push({id:job.event.id,created_at:new Date(clock()).toISOString(),object:job.request.object,surface:job.request.surface,why:job.event.proposal.why,source:job.source,receipt:result.receipt.id,event:job.event});s.moves=s.moves.slice(-60);}
    s.receipts.push({id:job.event.id,status:result.ok?'done':'skipped',reason:result.ok?null:result.error});s.receipts=s.receipts.slice(-500);s.prepared=null;s.revision++;await atomic(file,s);
  }
  async function tick(){const s=await load();if(!s.enabled)return;if(s.prepared){if(!presenceReady||s.guard.draft||s.guard.editing_until>clock()||!await available())return;await finishPrepared(s);}
    const names=(await readdir(folder).catch(e=>{if(e.code==='ENOENT')return[];throw e;})).filter(n=>/^rl-[a-f0-9]{24}\.json$/.test(n)).sort().slice(0,20);
    for(const name of names){const event=await json(path.join(folder,name),null);if(!event||name!==event.id+'.json')continue;
      if(s.receipts.some(r=>r.id===event.id)){await archive(name);continue;}
      const proposal=event.proposal;let source,status='done',reason=null;
      try{source=await evidence(event);const age=clock()-Date.parse(event.created_at);if(!Number.isFinite(age)||age< -60000||age>48*3600000)throw error('这轮生活想法已经过期。');
        if(!clean(proposal?.why,6,200))throw error('生活理由不正确。');
        if(proposal.action==='move'){
          if(!presenceReady||s.guard.draft||s.guard.editing_until>clock()||!await available())continue;
          if(s.moves.some(m=>clock()-Date.parse(m.created_at)<6*3600000)||s.moves.filter(m=>utcDay(new Date(m.created_at))===utcDay(new Date(clock()))).length>=2)throw error('今天先保留现在的布置，等下次再想。');
          if(!Object.hasOwn(objects,proposal.object)||!Object.hasOwn(objects[proposal.object].presets,proposal.surface)||!Number.isSafeInteger(proposal.revision))throw error('这个移动不在允许范围。');
          const operation=hash(event.id).slice(0,32),uuid=[operation.slice(0,8),operation.slice(8,12),operation.slice(12,16),operation.slice(16,20),operation.slice(20)].join('-');
          s.prepared={event,source,request:{object:proposal.object,surface:proposal.surface,revision:proposal.revision,operation_id:uuid}};await atomic(file,s);await finishPrepared(s);await archive(name);return;
        }else if(proposal.action==='wish'){
          if(!clean(proposal.item,2,40)||!clean(proposal.text,6,200))throw error('愿望内容不正确。');
          if(s.wishes.filter(w=>['open','accepted'].includes(w.status)&&Date.parse(w.expires_at)>clock()).length>=5)throw error('先留着已有的小愿望。');
          if(s.wishes.some(w=>w.item===proposal.item&&clock()-Date.parse(w.created_at)<7*86400000))throw error('这个愿望已经说过了。');
          if(s.wishes.some(w=>clock()-Date.parse(w.created_at)<12*3600000))throw error('先不接连提愿望。');
          s.wishes.push({id:event.id,item:proposal.item,text:proposal.text,why:proposal.why,status:'open',event,created_at:new Date(clock()).toISOString(),expires_at:new Date(clock()+7*86400000).toISOString()});s.wishes=s.wishes.slice(-30);
        }else throw error('生活动作不支持。');
      }catch(e){if(s.prepared||!Number.isInteger(e.status))throw e;if(e.status===425||e.status>=500)continue;status='skipped';reason=e.message;}
      s.receipts.push({id:event.id,status,reason});s.receipts=s.receipts.slice(-500);s.revision++;await atomic(file,s);await archive(name);
    }
  }
  async function archive(name){const target=path.join(folder,'handled');await mkdir(target,{recursive:true,mode:0o700});await rename(path.join(folder,name),path.join(target,name)).catch(e=>{if(e.code!=='ENOENT')throw e;});}
  return {tick:()=>locked(tick),snapshot:()=>locked(async()=>projection(await load())),
    presence:data=>locked(async()=>{if(typeof data?.draft!=='boolean'||typeof data?.editing!=='boolean')throw error('布置状态无效。');const s=await load();let character=s.guard.character??null;
      if(data.character){const c=data.character;if(!['walk','sit','sleep','idle'].includes(c.pose)||!['auto','walk','desk','sleep'].includes(c.mode)||!['rug','center','deskDoor','desk','bedDoor','bed','shelf','window'].includes(c.goal))throw error('人物状态无效。');character={pose:c.pose,mode:c.mode,goal:c.goal,at:clock()};}
      s.guard={draft:data.draft,editing_until:data.editing?clock()+45000:0,character};await atomic(file,s);presenceReady=true;return {ok:true};}),
    update:data=>locked(async()=>{const s=await load();if(data?.revision!==s.revision)throw error('小屋生活已更新，请刷新。',409);
      if(data.action==='settings'&&typeof data.enabled==='boolean')s.enabled=data.enabled;
      else if(data.action==='wish'&&['accepted','declined','fulfilled'].includes(data.status)){const w=s.wishes.find(w=>w.id===data.id);if(!w)throw error('愿望不存在。',404);await evidence(w.event);if(Date.parse(w.expires_at)<clock())throw error('这个愿望已过期。',409);w.status=data.status;}
      else throw error('生活设置无效。');s.revision++;await atomic(file,s);return projection(s);}),
  };
}
