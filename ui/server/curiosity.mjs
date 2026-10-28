import{readFile,readdir}from'node:fs/promises';
import path from'node:path';
import {normalizeSettings} from './usage.mjs';
export async function curiositySnapshot(root,now=Date.now()){
 let data={threads:[],runs:[]};try{data=JSON.parse(await readFile(path.join(root,'data/curiosity/state.json'),'utf8'))}catch(e){if(e.code!=='ENOENT')throw e;}
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const day=value=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
 const counted=new Set(data.runs.map(r=>r.report_path)),files=await readdir(path.join(root,'reports',today)).catch(()=>[]);
 const used_today=data.runs.filter(r=>day(r.started_at)===today).length+files.filter(f=>f.includes('surf')&&f.endsWith('.md')&&!counted.has('reports/'+today+'/'+f)).length;
 const threads=data.threads.filter(v=>v.status==='open'&&Date.parse(v.expires_at)>now).map(v=>({id:v.id,question:v.question,why:v.why,source_urls:(v.source_urls||[]).filter(u=>{try{return['http:','https:'].includes(new URL(u).protocol)}catch{return false}}),updated_at:v.updated_at,last_outcome:v.last_outcome||null,cooling_down:Boolean(v.snoozed_until&&Date.parse(v.snoozed_until)>now)}));
 let settings={paused:false,max_outings:3};try{settings=normalizeSettings(JSON.parse(await readFile(path.join(root,'data/automation/settings.json'),'utf8')))}catch(e){if(e.code!=='ENOENT')throw e;}
 const last=data.runs.at(-1);return{threads,used_today,daily_limit:settings.max_outings,paused:settings.paused,last_outing:last?{question:last.question,status:last.status,outcome:last.outcome||null,reason:last.reason||null,started_at:last.started_at}:null};
}
