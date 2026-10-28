import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeUsage,normalizeSettings,createUsage} from '../server/usage.mjs';
import {mkdtemp,rm} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
test('main/auxiliary usage stay separate; cached input and reasoning never double-count',()=>{
 const row={id:'one',source:'cron',started_at:100,input_tokens:100,output_tokens:30,cache_read_tokens:900,reasoning_tokens:20,api_call_count:2};
 const value=summarizeUsage([row,row,{...row,id:'old',started_at:1}],[{task:'background_review',api_calls:1,input_tokens:10,output_tokens:5}],50);
 assert.equal(value.main.calls,2);assert.equal(value.main.input,100);assert.equal(value.main.output,30);assert.equal(value.cache_hit_ratio,.9);assert.equal(value.auxiliary[0].calls,1);assert.equal(value.sources[0].source,'cron');
});
test('unknown input stays visible and zero-input cache rate is unknown',()=>{const value=summarizeUsage([{id:'x',source:'bigfish',started_at:1,message_count:2}]);assert.equal(value.main.unknown_sessions,1);assert.equal(value.cache_hit_ratio,null)});
test('settings reject invalid daily activity counts',()=>{for(const value of [0,4,'2',true])assert.throws(()=>normalizeSettings({paused:false,max_outings:value}));assert.deepEqual(normalizeSettings({paused:true,max_outings:1}),{paused:true,max_outings:1})});
test('native usage never exposes titles, endpoints, origins or raw history',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-usage-'));t.after(()=>rm(root,{recursive:true,force:true}));let calls=0;
 const native=async route=>{calls++;return route.includes('/sessions?')?{sessions:[{id:'one',source:'bigfish',started_at:100,input_tokens:5,title:'private title',billing_base_url:'private endpoint',origin_json:'private origin'}],total:1}:{by_task:[]}};
 const usage=createUsage(root,native,{now:()=>100000});const value=await usage.snapshot('7');const encoded=JSON.stringify(value);assert.doesNotMatch(encoded,/private title|private endpoint|private origin/);await usage.snapshot('7');assert.equal(calls,2);
 await usage.saveSettings({paused:true,max_outings:1});assert.equal((await usage.snapshot('7')).settings.paused,true);
});
test('official totals retain consumption from sessions omitted by visible session lists',async()=>{
 const {alignUsageTotals}=await import('../server/usage.mjs');const value=summarizeUsage([{id:'visible',source:'bigfish',started_at:100,input_tokens:10,output_tokens:4,cache_read_tokens:90,api_call_count:1}]);
 alignUsageTotals(value,{total_api_calls:3,total_input:30,total_output:12,total_cache_read:270,total_reasoning:2});
 assert.equal(value.main.calls,3);assert.equal(value.sources.find(v=>v.source==='other').calls,2);assert.equal(value.main.input,30);assert.equal(value.cache_hit_ratio,.9);
});
test('offline analytics remain unknown while local automation controls stay usable',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-offline-'));t.after(()=>rm(root,{recursive:true,force:true}));const usage=createUsage(root,async()=>{throw new Error('offline')});
 await usage.saveSettings({paused:true,max_outings:1});const value=await usage.snapshot('7');assert.equal(value.available,false);assert.equal(value.settings.paused,true);assert.equal(value.cache_hit_ratio,null);
});
