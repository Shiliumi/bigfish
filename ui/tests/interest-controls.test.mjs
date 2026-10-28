import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readInterestControls,interestBlocked} from '../server/interest-controls.mjs';
import {createInbox} from '../server/inbox.mjs';
import {curiositySnapshot} from '../server/curiosity.mjs';

const now=Date.parse('2026-10-28T12:00:00+08:00'),id='cur-123456789abc',url='https://example.org/folding';
const controls=(choice='paused')=>({version:1,revision:1,items:[{id,question:'折叠凳的转轴如何锁住？',choice,source_urls:[url],changed_at:new Date(now).toISOString(),until:choice==='paused'?new Date(now+3*86400000).toISOString():null}]});
async function fixture(t){const root=await mkdtemp(path.join(os.tmpdir(),'fish-interest-'));t.after(()=>rm(root,{recursive:true,force:true}));await mkdir(path.join(root,'data/curiosity'),{recursive:true});return root;}
const store=(root,value)=>writeFile(path.join(root,'data/curiosity/controls.json'),typeof value==='string'?value:JSON.stringify(value));

test('Python and Node agree on id, source and exact three-day boundary',async t=>{
 const root=await fixture(t);await store(root,controls());const value=await readInterestControls(root);
 const probes=[{id,urls:[],at:now},{id:'cur-abcdef123456',urls:[url],at:now},{id,urls:[],at:now+3*86400000},{id:null,urls:['https://example.org/other'],at:now}];
 const expected=probes.map(p=>interestBlocked(value,p.id,p.urls[0],p.at));assert.deepEqual(expected,[true,true,false,false]);
 const scripts=fileURLToPath(new URL('../../scripts/',import.meta.url));
 const result=JSON.parse(execFileSync('python3',['-c','import sys,json;from datetime import datetime,timezone;sys.path.insert(0,sys.argv[1]);from fish_interest import load_controls,blocked;v=load_controls(sys.argv[2]);print(json.dumps([blocked(v,p["id"],p["urls"],datetime.fromtimestamp(p["at"]/1000,timezone.utc))for p in json.loads(sys.argv[3])]))',scripts,root,JSON.stringify(probes)],{encoding:'utf8'}));assert.deepEqual(result,expected);
});
test('invalid controls fail closed and the application does not show paused interests as active',async t=>{
 const root=await fixture(t);await store(root,controls());await writeFile(path.join(root,'data/curiosity/state.json'),JSON.stringify({threads:[{id,question:'折叠凳的转轴如何锁住？',why:'实际看过作品，想继续了解。',status:'open',expires_at:'2026-11-10T00:00:00Z',source_urls:[url]}],runs:[]}));
 const snapshot=await curiositySnapshot(root,now);assert.equal(snapshot.threads.length,0);assert.equal(snapshot.controls.items[0].active,true);assert.ok(!JSON.stringify(snapshot.controls).includes(url));
 await store(root,'{broken');await assert.rejects(()=>readInterestControls(root));await assert.rejects(()=>curiositySnapshot(root,now));
 const bad=controls();bad.items[0].until='2026-10-31T12:00:00';await store(root,bad);await assert.rejects(()=>readInterestControls(root));
});
test('queued and new discoveries obey choices but old messages and greetings remain',async t=>{
 const root=await fixture(t);await store(root,controls('retired'));await mkdir(path.join(root,'data/outbox'),{recursive:true});await mkdir(path.join(root,'reports/2026-10-28'),{recursive:true});
 const report='reports/2026-10-28/1200-surf.md';await writeFile(path.join(root,report),url);await writeFile(path.join(root,'data/surf-state.json'),JSON.stringify({visited:[{url}]}));
 const entry={kind:'surf',created_at:new Date(now).toISOString(),source_url:url,text:'上次的折叠机关这回看到了原理。',worth_sharing:true,why_share:'实际看到了具体的新结构。',report_path:report};
 await writeFile(path.join(root,'data/outbox/read.json'),JSON.stringify(entry));
 await writeFile(path.join(root,'data/inbox.json'),JSON.stringify({settings:{greetings:true},messages:[{id:'previous',kind:'surf',source_url:'https://example.org/old',sent_at:new Date(now-2*86400000).toISOString()}],processed:[],pending:[{...entry,source_url:'https://example.org/new-followup',interest_id:id},{kind:'greeting',dedupe_key:'fixture-greeting',created_at:new Date(now).toISOString(),text:'午安，来冒个泡。'}]}));
 const inbox=createInbox(root,()=>now);await inbox.tick();const snapshot=await inbox.snapshot();assert.equal(snapshot.messages.length,2);assert.ok(snapshot.messages.some(m=>m.id==='previous'));assert.ok(snapshot.messages.some(m=>m.kind==='greeting'));assert.ok(snapshot.messages.every(m=>m.source_url!==url));
 const saved=JSON.parse(await readFile(path.join(root,'data/inbox.json'),'utf8'));assert.equal(saved.pending.length,0);assert.ok(saved.processed.includes('read.json'));
});
test('corrupt choices hold discoveries for retry and never consume the queued message',async t=>{
 const root=await fixture(t);await store(root,'{broken');const pending={kind:'surf',created_at:new Date(now).toISOString(),source_url:url,text:'这个机关的新发现。'};
 await writeFile(path.join(root,'data/inbox.json'),JSON.stringify({settings:{greetings:false},messages:[],processed:[],pending:[pending]}));
 const inbox=createInbox(root,()=>now);await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,0);
 const saved=JSON.parse(await readFile(path.join(root,'data/inbox.json'),'utf8'));assert.equal(saved.pending.length,1);
 await store(root,{version:1,revision:0,items:[]});await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,1);
});
test('acknowledged choice updates serialize before subsequent delivery checks',async t=>{
 const root=await fixture(t);const entry={kind:'surf',created_at:new Date(now).toISOString(),source_url:url,text:'关于折叠凳的新发现。'};
 await writeFile(path.join(root,'data/inbox.json'),JSON.stringify({settings:{greetings:false},messages:[],processed:[],pending:[entry]}));
 const inbox=createInbox(root,()=>now);await Promise.all([inbox.updateInterest(()=>store(root,controls('retired'))),inbox.tick()]);assert.equal((await inbox.snapshot()).messages.length,0);
});
