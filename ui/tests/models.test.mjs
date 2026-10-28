import test from 'node:test';
import assert from 'node:assert/strict';
import {createModelSettings,normalizeBase,resolveConnection,parseEnv} from '../server/models.mjs';
const original={provider:'deepseek',base_url:'https://api.deepseek.com/v1',model:'deepseek-flash',key:'fixture-secret',name:'DeepSeek',api_mode:'chat_completions'};
const manager=options=>createModelSettings('',{readConnection:async()=>({...original}),...options});
const data={base_url:original.base_url,model:original.model};
test('model snapshots never contain credentials; addresses must be explicit safe base URLs',async()=>{
 const state=await manager().snapshot();assert.equal(state.has_key,true);assert.ok(!JSON.stringify(state).includes(original.key));assert.ok(!('api_key' in state));
 assert.equal(normalizeBase(' https://example.org/v1/ '),'https://example.org/v1');
 for(const address of ['ftp://example.org','https://user:pass@example.org/v1','https://example.org/v1?key=secret','http://remote.example/v1','https://example.org/v1/chat/completions'])assert.throws(()=>normalizeBase(address));
 assert.equal(normalizeBase('http://127.0.0.1:11434/v1'),'http://127.0.0.1:11434/v1');
});
test('Hermes environment references and named provider keys resolve privately',()=>{
 const env=parseEnv('DEEPSEEK_API_KEY="one"\nCUSTOM_KEY=two # private\nOTHER=three\n');
 assert.equal(resolveConnection({model:{provider:'deepseek',default:'d'}},env).key,'one');
 assert.equal(resolveConnection({model:{provider:'fish',default:'x'},providers:{fish:{base_url:'https://example.org/v1',key_env:'CUSTOM_KEY'}}},env).key,'two');
 assert.equal(resolveConnection({model:{provider:'fish',default:'x',base_url:'https://example.org/v1',api_key:'${OTHER}'}},env).key,'three');
});
test('saved key is reused only for the same endpoint; a new host never receives it',async()=>{
 const calls=[];const m=manager({fetcher:async(url,opts)=>{calls.push([url,opts]);return Response.json({data:[{id:'b'},{id:'a'},{id:'b'}]});}});
 assert.deepEqual(await m.list(data),{models:['a','b']});assert.equal(calls[0][1].headers.Authorization,'Bearer fixture-secret');
 await m.list({...data,base_url:'https://other.example/v1'});assert.ok(!calls[1][1].headers.Authorization);assert.equal(calls[1][1].redirect,'error');
 await m.list({...data,api_key:'replacement'});assert.equal(calls[2][1].headers.Authorization,'Bearer replacement');
 await m.list({...data,clear_key:true});assert.ok(!calls[3][1].headers.Authorization);
});
test('connectivity means a real generation from the requested model, not a successful model list',async()=>{
 let request;const m=manager({fetcher:async(url,opts)=>{request={url,body:JSON.parse(opts.body)};return Response.json({choices:[{message:{content:'OK'}}]});}});
 const result=await m.test({...data,model:'chosen-id'});assert.equal(result.ok,true);assert.equal(request.url,original.base_url+'/chat/completions');assert.equal(request.body.model,'chosen-id');assert.equal(request.body.stream,false);
 await assert.rejects(manager({fetcher:async()=>Response.json({data:[]})}).test(data),/有效的模型回复/);
});
test('provider errors and network failures do not echo secrets or untrusted response text',async()=>{
 for(const status of [401,402,404,429,500])await assert.rejects(manager({fetcher:async()=>new Response('fixture-secret',{status})}).test(data),e=>e.status===502&&!e.message.includes('fixture-secret'));
 await assert.rejects(manager({fetcher:async()=>{throw new Error('fixture-secret')}}).list(data),e=>!e.message.includes('fixture-secret'));
});
test('saving uses native Hermes configuration, is conflict-safe, and refuses active replies',async()=>{
 let call;const m=manager({native:async(...args)=>{call=args;return {ok:true};}});const state=await m.snapshot();
 await assert.rejects(m.save({...data,version:'stale'}),e=>e.status===409);assert.equal(call,undefined);
 const saved=await m.save({...data,version:state.version});assert.equal(saved.ok,true);assert.equal(call[0],'/api/providers/custom-endpoints?profile=default');assert.equal(call[2].api_key,original.key);assert.equal(call[2].make_default,true);assert.equal(call[2].api_mode,'chat_completions');assert.ok(!JSON.stringify(saved).includes(original.key));
 const busy=manager({isBusy:()=>true});await assert.rejects(busy.save(data),e=>e.status===409);
});
test('non-DeepSeek endpoints do not query or claim a DeepSeek account balance',async()=>{
 assert.ok(await manager().balanceConnection());assert.equal(await manager({readConnection:async()=>({...original,base_url:'https://other.example/v1'})}).balanceConnection(),null);
});
