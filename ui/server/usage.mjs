import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const count=v=>Number.isFinite(v)&&v>=0?v:0;
const read=async(file,fallback)=>{try{return JSON.parse(await readFile(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw new Error('后台活动状态暂时无法读取，请检查本机数据。');}};
export function normalizeSettings(value){
 if(!value||typeof value.paused!=='boolean'||!Number.isInteger(value.max_outings)||value.max_outings<1||value.max_outings>3)throw Object.assign(new Error('请设置后台开关及每天 1–3 次出发机会。'),{status:400});
 return {paused:value.paused,max_outings:value.max_outings};
}
export function summarizeUsage(rows,auxiliary=[],cutoff=0){
 const groups=new Map(),seen=new Set();
 for(const row of rows){
  if(!row.id||seen.has(row.id)||count(row.started_at)<cutoff)continue;seen.add(row.id);
  const source=['bigfish','cron','tui','oneshot'].includes(row.source)?row.source:'other';
  const value=groups.get(source)||{source,sessions:0,calls:0,input:0,output:0,cached:0,cache_write:0,reasoning:0,unknown_sessions:0};
  value.sessions++;value.calls+=count(row.api_call_count);value.input+=count(row.input_tokens);value.output+=count(row.output_tokens);value.cached+=count(row.cache_read_tokens);value.cache_write+=count(row.cache_write_tokens);value.reasoning+=count(row.reasoning_tokens);
  if(row.message_count>0&&!Number.isFinite(row.input_tokens))value.unknown_sessions++;
  groups.set(source,value);
 }
 const sources=[...groups.values()];
 const main={calls:0,input:0,output:0,cached:0,cache_write:0,reasoning:0,unknown_sessions:0};
 for(const source of sources)for(const key of Object.keys(main))main[key]+=source[key];
 const denominator=main.input+main.cached+main.cache_write;
 return {main,cache_hit_ratio:denominator?main.cached/denominator:null,sources,auxiliary:auxiliary.map(row=>({task:String(row.task||'other').slice(0,80),calls:count(row.api_calls),input:count(row.input_tokens),output:count(row.output_tokens)}))};
}
export function alignUsageTotals(value,totals){
 const mapping={calls:'total_api_calls',input:'total_input',output:'total_output',cached:'total_cache_read',reasoning:'total_reasoning'};
 const difference={source:'other',sessions:0,calls:0,input:0,output:0,cached:0,cache_write:0,reasoning:0,unknown_sessions:0};
 for(const [key,field] of Object.entries(mapping)){
  if(Number.isFinite(totals?.[field])&&totals[field]>=value.main[key]){difference[key]=totals[field]-value.main[key];value.main[key]=totals[field];}
 }
 if(Object.keys(mapping).some(key=>difference[key]>0)){
  const existing=value.sources.find(row=>row.source==='other');
  if(existing)for(const key of Object.keys(mapping))existing[key]+=difference[key];else value.sources.push(difference);
 }
 const denominator=value.main.input+value.main.cached+value.main.cache_write;
 value.cache_hit_ratio=denominator?value.main.cached/denominator:null;
 return value;
}
export function createUsage(root,native,{now=Date.now}={}){
 const directory=path.join(root,'data/automation');let cache=new Map();
 async function settings(){return normalizeSettings(await read(path.join(directory,'settings.json'),{paused:false,max_outings:3}));}
 return {
  settings,
  async saveSettings(data){const value=normalizeSettings(data);await mkdir(directory,{recursive:true,mode:0o700});const temporary=path.join(directory,'.settings-'+randomUUID());await writeFile(temporary,JSON.stringify(value)+'\n',{mode:0o600});await rename(temporary,path.join(directory,'settings.json'));return value;},
  async snapshot(input){
   const days=Number(input||7);if(![7,30,90].includes(days))throw Object.assign(new Error('请选择 7、30 或 90 天。'),{status:400});
   const cutoff=now()/1000-days*86400;let value=cache.get(days);
   if(!value||now()-value.at>30000){
    try{
    const rows=[];let offset=0,partial=false;
    do{const data=await native(`/api/sessions?profile=default&limit=100&offset=${offset}&order=recent&min_messages=0`);const page=data.sessions||[];rows.push(...page);offset+=page.length;if(page.length<100||offset>=Number(data.total||0))break;if(offset>=3000){partial=true;break;}}while(true);
    const analytics=await native(`/api/analytics/usage?profile=default&days=${days}`);
    value={at:now(),data:{...alignUsageTotals(summarizeUsage(rows,analytics.by_task||[],cutoff),analytics.totals),available:true,partial,days,generated_at:new Date(now()).toISOString()}};
    }catch{
     value={at:now()-25000,data:{...summarizeUsage([]),available:false,partial:true,days,generated_at:new Date(now()).toISOString()}};
    }
    cache.set(days,value);
   }
   const decisions=await read(path.join(directory,'gates.json'),{});
   const gates=['surf','memory'].map(kind=>({kind,wake:decisions[kind]?.wakeAgent===true,checked_at:decisions[kind]?.checked_at||null,reason:String(decisions[kind]?.reason||'还没有预检记录。').slice(0,180),error:Boolean(decisions[kind]?.error),skipped_ticks:count(decisions[kind]?.skipped_ticks)}));
   return {...value.data,settings:await settings(),gates};
  }
 };
}
