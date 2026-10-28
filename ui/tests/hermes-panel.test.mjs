import test from 'node:test';
import assert from 'node:assert/strict';
import {createHermesPanel} from '../server/hermes-panel.mjs';
test('panel projects only selected public fields from Hermes data, including job records',async()=>{
 const panel=createHermesPanel(async route=>route.includes('/runs')?{runs:[{id:'run',started_at:123,end_reason:'cron_complete',model_config:{api_key:'private'}}]}:route.includes('toolsets')?[{name:'web',enabled:true,configured:true,tools:['web_search'],api_key:'private'}]:route.includes('/skills')?[{name:'notes',enabled:true,path:'/private',api_key:'private'}]:route.includes('stats')?{total:8,messages:10,api_key:'private'}:route.includes('jobs')?[{id:'abc',name:'surf',prompt:'private',enabled:true}]:{version:'0.22.5',gateway_running:true,api_key:'private'});
 for(const result of [await panel.summary(),await panel.tools(),await panel.skills(),await panel.runs('abc')])assert.ok(!JSON.stringify(result).includes('private'));
 assert.equal((await panel.runs('abc')).runs[0].status,'已完成');
});
test('capability mutations validate names against Hermes and preserve the requested boolean',async()=>{
 const calls=[];const panel=createHermesPanel(async(route,method,data)=>{calls.push({route,method,data});return method?{ok:true}:[{name:'notes',enabled:true}];});
 await assert.rejects(panel.toggle('skills',{name:'unknown',enabled:false}),e=>e.status===404);assert.ok(!calls.some(c=>c.method));
 await assert.rejects(panel.toggle('tools',{name:'notes',enabled:'false'}),e=>e.status===400);
 await panel.toggle('skills',{name:'notes',enabled:false});assert.deepEqual(calls.at(-1).data,{name:'notes',enabled:false});
});
test('session pages include cron and terminal history, while full-text search uses the native search route',async()=>{
 const calls=[];const panel=createHermesPanel(async route=>{calls.push(route);return route.includes('search')?{results:[{id:'one',title:'found',source:'tui',model_config:'private'}]}:{sessions:[{id:'cron-session',source:'cron',api_key:'private'}],total:51};});
 const page=await panel.sessions(new URLSearchParams('offset=50&source=cron'));assert.equal(page.sessions[0].source,'cron');assert.equal(page.has_more,false);assert.ok(calls[0].includes('offset=50'));assert.ok(!JSON.stringify(page).includes('private'));
 const search=await panel.sessions(new URLSearchParams('q=hello'));assert.ok(calls[1].startsWith('/api/sessions/search?'));assert.equal(search.sessions[0].title,'found');
});
test('history is read without tool payloads or inline images; renaming requires a revision and generation',async()=>{
 const calls=[];const panel=createHermesPanel(async(route,method,data)=>{calls.push({route,method,data});if(route.includes('mutation-snapshot'))return {runtime_revision:4,runtime_generation:2};if(route.includes('messages'))return {messages:[{role:'user',content:'hello'},{role:'tool',content:'private'},{role:'assistant',content:[{type:'image',source:'private'},{type:'text',text:'hi'}]}],pagination:{returned:3}};return {id:'chat',title:'title',api_key:'private'};});
 const detail=await panel.detail('chat');assert.deepEqual(detail.messages,[{role:'user',content:'hello'},{role:'assistant',content:'hi'}]);assert.ok(calls[1].route.includes('inline_images=false'));assert.ok(!JSON.stringify(detail).includes('private'));
 await assert.rejects(panel.rename('chat',{title:'new'}),e=>e.status===409);await assert.rejects(panel.detail('../.env'),e=>e.status===400);
 await panel.rename('chat',{title:'new',revision:4,generation:2});assert.equal(calls.at(-1).method,'PATCH');assert.equal(calls.at(-1).data.expected_revision,4);assert.equal(calls.at(-1).data.expected_generation,2);
});
test('Bigfish history renames use the chat owner only after a typed REST not-found and a fresh revision check',async()=>{
 const renamed=[];const native=async(route,method)=>{if(method)throw Object.assign(new Error('not_found'),{status:404});return route.includes('mutation-snapshot')?{runtime_revision:4,runtime_generation:2}:{id:'chat',source:'bigfish'};};
 const panel=createHermesPanel(native,{renameChat:async(...args)=>renamed.push(args)});await panel.rename('chat',{title:'new',revision:4,generation:2});assert.deepEqual(renamed,[['chat','new']]);
 await assert.rejects(panel.rename('chat',{title:'stale',revision:3,generation:2}),e=>e.status===409);assert.equal(renamed.length,1);
 const uncertain=createHermesPanel(async()=>{throw Object.assign(new Error('timeout'),{status:503})},{renameChat:async()=>renamed.push('bad')});await assert.rejects(uncertain.rename('chat',{title:'new',revision:4,generation:2}),e=>e.status===503);assert.equal(renamed.length,1);
});
