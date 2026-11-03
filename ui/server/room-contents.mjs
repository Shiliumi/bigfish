import {readFile,stat,realpath,mkdir,writeFile,rename,unlink,open} from 'node:fs/promises';
import path from 'node:path';import {createHash,randomUUID} from 'node:crypto';
import {createReadStream} from 'node:fs';import {createInterface} from 'node:readline';
const error=(message,status=400)=>Object.assign(new Error(message),{status});
const digest=value=>createHash('sha256').update(value).digest('hex').slice(0,24);
const url=value=>{try{const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)return null;u.hash='';return u.href;}catch{return null;}};
const text=(value,max)=>typeof value==='string'?value.replace(/\s+/g,' ').slice(0,max):'';
async function json(file,fallback){try{return JSON.parse(await readFile(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
async function tail(file){let handle;try{handle=await open(file,'r');const info=await handle.stat(),start=Math.max(0,info.size-1024*1024),buffer=Buffer.alloc(info.size-start);await handle.read(buffer,0,buffer.length,start);const lines=buffer.toString('utf8').split('\n');if(start)lines.shift();return lines.slice(-2000).flatMap(line=>{try{return [JSON.parse(line)];}catch{return [];}});}catch(e){if(e.code==='ENOENT')return [];throw e;}finally{await handle?.close();}}
export function createRoomContents(root,{readMemories}={}){
  const file=path.join(root,'data/room/collection.json');let pending=Promise.resolve();
  let favoriteCache=null;
  const locked=fn=>{const task=pending.then(fn);pending=task.catch(()=>{});return task;};
  async function collection(){const s=await json(file,{schema:1,revision:0,refs:[]});if(s.schema!==1||!Number.isSafeInteger(s.revision)||!Array.isArray(s.refs)||s.refs.length>50||s.revision<0||s.refs.some(r=>!/^rr-[a-f0-9]{24}$/.test(r.id)))throw error('收藏暂时无法读取，原文件已保留。',503);return s;}
  async function readings(refs=[]){
    const [observations,visited,reportRoot]=await Promise.all([tail(path.join(root,'data/personality/observations.jsonl')),json(path.join(root,'data/surf-state.json'),{visited:[]}),realpath(path.join(root,'reports')).catch(()=>null)]);
    if(!Array.isArray(visited.visited)||!reportRoot)return [];
    // Older bookmarks must not become "unavailable" just because they left the recent tail.
    // Stream only their matching rows into memory; reuse the index until the source changes.
    const wanted=new Set(refs.map(r=>url(r.url)).filter(Boolean)),missing=[...wanted].filter(u=>!observations.some(r=>url(r.url)===u));
    if(missing.length){const source=path.join(root,'data/personality/observations.jsonl'),info=await stat(source).catch(()=>null),key=JSON.stringify([info?.mtimeMs,info?.size,[...wanted].sort()]);
      if(!favoriteCache||favoriteCache.key!==key){const found=new Map();if(info){const stream=createReadStream(source,{encoding:'utf8'}),lines=createInterface({input:stream,crlfDelay:Infinity});try{for await(const line of lines){let row;try{row=JSON.parse(line);}catch{continue;}const link=url(row.url);if(wanted.has(link)&&['body','comments'].includes(row.read_depth))found.set(link,row);}}finally{lines.close();stream.destroy();}}favoriteCache={key,rows:[...found.values()]};}
      observations.push(...favoriteCache.rows);
    }
    const result=[],seen=new Set();
    for(const row of observations.slice().sort((a,b)=>Number(wanted.has(url(b.url)))-Number(wanted.has(url(a.url)))||(Date.parse(b.seen_at)||0)-(Date.parse(a.seen_at)||0))){
      const link=url(row.url),report=row.report_path;if(!link||!['body','comments'].includes(row.read_depth)||typeof row.id!=='string'||!Number.isFinite(Date.parse(row.seen_at))||typeof report!=='string'||!/^reports\/\d{4}-\d{2}-\d{2}\/[\w.-]+\.md$/.test(report))continue;
      const visit=visited.visited.find(v=>url(v.url)===link&&v.report===report);if(!visit||seen.has(link))continue;
      const target=await realpath(path.resolve(root,report)).catch(()=>null);if(!target||!target.startsWith(reportRoot+path.sep))continue;const info=await stat(target);if(!info.isFile()||info.size>512000)continue;
      const reportText=await readFile(target,'utf8');if(!reportText.includes(row.url)&&!reportText.includes(link))continue;
      seen.add(link);result.push({id:'rr-'+digest(link),title:text(visit.title||row.title||new URL(link).hostname,100),url:link,read_at:row.seen_at,excerpt:text(row.observation,180),read_depth:row.read_depth,source:{observation_id:row.id,report_path:report}});if(result.length>=100)break;
    }return result.sort((a,b)=>Date.parse(b.read_at)-Date.parse(a.read_at));
  }
  async function snapshot(){
    const s=await collection(),results=await Promise.allSettled([readings(s.refs),readMemories?readMemories():Promise.resolve({items:[]})]);
    const rows=results[0].status==='fulfilled'?results[0].value:[],byId=new Map(rows.map(r=>[r.id,r]));
    const memories=results[1].status==='fulfilled'&&Array.isArray(results[1].value.items)?results[1].value.items.filter(r=>r.effective_status==='active'&&/^ep-[a-f0-9]{24}$/.test(r.id)).slice(0,3).map(r=>({id:r.id,summary:text(r.summary,250),recorded_at:r.recorded_at,revision:r.revision,pinned:!!r.pinned,kind:r.kind})):[];
    return {revision:s.revision,readings:rows.slice(0,6).map(r=>({...r,saved:s.refs.some(v=>v.id===r.id)})),favorites:s.refs.map(ref=>byId.has(ref.id)?{...byId.get(ref.id),saved:true}:{id:ref.id,unavailable:true}),memories,reading_status:results[0].status==='fulfilled'?'ready':'unavailable',memory_status:results[1].status==='fulfilled'?'ready':'unavailable'};
  }
  return {snapshot:()=>locked(snapshot),
    collect:data=>locked(async()=>{if(!data||!/^rr-[a-f0-9]{24}$/.test(data.id)||typeof data.saved!=='boolean'||!Number.isSafeInteger(data.revision))throw error('收藏请求不正确。');const s=await collection();if(s.revision!==data.revision)throw error('收藏已更新，请重新读取。',409);
      if(data.saved){const row=(await readings(s.refs)).find(r=>r.id===data.id);if(!row)throw error('这条阅读来源已不可核对，未加入收藏。',409);if(!s.refs.some(v=>v.id===data.id)){if(s.refs.length>=50)throw error('先整理一下收藏吧，最多保留 50 条。',409);s.refs.push({id:row.id,url:row.url,...row.source});}}
      else s.refs=s.refs.filter(v=>v.id!==data.id);s.revision++;await mkdir(path.dirname(file),{recursive:true,mode:0o700});const temp=file+'.'+randomUUID()+'.tmp';try{await writeFile(temp,JSON.stringify(s),{mode:0o600});await rename(temp,file);}finally{await unlink(temp).catch(()=>{});}return snapshot();}),
  };
}
