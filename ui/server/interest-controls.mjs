import {readFile,stat} from 'node:fs/promises';
import path from 'node:path';

// Same bounded format as fish_interest.py. A broken file never silently clears a choice.
export async function readInterestControls(root){
 const file=path.join(root,'data/curiosity/controls.json');let value;
 try{if((await stat(file)).size>200000)throw Error('兴趣设置过大。');value=JSON.parse(await readFile(file,'utf8'));}
 catch(error){if(error.code==='ENOENT')return {version:1,revision:0,items:[]};throw error;}
 if(value?.version!==1||!Number.isSafeInteger(value.revision)||value.revision<0||value.revision>=Number.MAX_SAFE_INTEGER||!Array.isArray(value.items)||value.items.length>80)throw Error('兴趣设置格式无效。');
 const ids=new Set();
 const time=v=>typeof v==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
 for(const row of value.items){
  if(!row||!/^cur-[a-f0-9]{12}$/.test(row.id)||ids.has(row.id)||!['paused','retired'].includes(row.choice)||typeof row.question!=='string'||!row.question.length||[...row.question].length>160||!Array.isArray(row.source_urls)||row.source_urls.length>8||row.source_urls.some(u=>typeof u!=='string'||[...u].length>2000)||!time(row.changed_at)||(row.choice==='paused'&&!time(row.until)))throw Error('兴趣设置条目无效。');
  ids.add(row.id);
 }
 return value;
}
export function interestBlocked(controls,ident,url,now=Date.now()){
 return controls.unavailable||controls.items.some(row=>(row.choice==='retired'||Date.parse(row.until)>now)&&(ident===row.id||Boolean(url&&row.source_urls.includes(url))));
}
