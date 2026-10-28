import {desktopKeyPath} from '../server/desktop-access.mjs';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import assert from 'node:assert/strict';

const BASE='http://127.0.0.1:9120';
const access=(await readFile(desktopKeyPath(),'utf8')).trim();
const page=await fetch(BASE,{headers:{'X-Fish-Desktop':access}});
const cookie=page.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ');
const headers={cookie,'Content-Type':'application/json','X-Fish-Client':'studio'};

test('private data requires a local session cookie',async()=>{
  const response=await fetch(BASE+'/api/documents');assert.equal(response.status,401);
  assert.equal((await fetch(BASE+'/api/companion')).status,401);
  assert.equal((await fetch(BASE+'/api/balance')).status,401);
  assert.equal((await fetch(BASE+'/api/model-settings')).status,401);
});
test('companion publishes only public runtime state',async()=>{
  const response=await fetch(BASE+'/api/companion',{headers});assert.equal(response.status,200);
  const state=await response.json(); assert.deepEqual(Object.keys(state).sort(),['animation','balance','label','notice','state','unread']);
  assert.ok(['idle','thinking','working','greeting'].includes(state.animation));
  assert.ok(!JSON.stringify(state).includes('api_key'));
});
test('cross-origin requests are refused even with an existing cookie',async()=>{
  const response=await fetch(BASE+'/api/documents',{headers:{...headers,Origin:'https://example.org'}});assert.equal(response.status,403);
});
test('mutations require the explicit client marker',async()=>{
  const response=await fetch(BASE+'/api/documents/memory',{method:'PUT',headers:{cookie,'Content-Type':'application/json'},body:'{}'});assert.equal(response.status,403);
});
test('the editable document surface cannot expose credentials',async()=>{
  const response=await fetch(BASE+'/api/documents',{headers});assert.equal(response.status,200);
  assert.deepEqual(Object.keys(await response.json()).sort(),['interests','memory','soul','user']);
  assert.equal((await fetch(BASE+'/api/documents/.env',{headers})).status,404);
});
test('stale memory edits are rejected without overwriting current contents',async()=>{
  const before=await(await fetch(BASE+'/api/documents',{headers})).json();
  const response=await fetch(BASE+'/api/documents/memory',{method:'PUT',headers,body:JSON.stringify({content:'stale edit must not persist',version:'stale-version'})});assert.equal(response.status,409);
  const after=await(await fetch(BASE+'/api/documents',{headers})).json();assert.equal(after.memory.content,before.memory.content);
});
test('overview contains the actual existing reports and native routines',async()=>{
  const response=await fetch(BASE+'/api/overview',{headers});assert.equal(response.status,200);const data=await response.json();
  assert.ok(data.connected);assert.ok(data.jobs.some(j=>j.name==='fish-surf'));assert.ok(data.jobs.some(j=>j.name==='fish-memory'));assert.ok(data.reports.every(r=>typeof r.content==='string'));
});

test('browser chat tickets are authenticated, temporary, and single use',async()=>{
  assert.equal((await fetch(BASE+'/api/chat-ticket')).status,401);
  const {ticket}=await(await fetch(BASE+'/api/chat-ticket',{headers})).json();
  const {WebSocket}=await import('ws');
  const socket=new WebSocket(BASE.replace('http','ws')+'/api/chat?ticket='+ticket,{origin:BASE});
  try {
    await new Promise((resolve,reject)=>{socket.once('open',resolve);socket.once('error',reject)});
    const reply=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Chat handshake timed out')),5000);socket.on('message',data=>{const frame=JSON.parse(data);if(frame.id===801){clearTimeout(timer);resolve(frame)}})});
    socket.send(JSON.stringify({jsonrpc:'2.0',id:801,method:'client.capabilities',params:{server_requests:true}}));
    assert.ok((await reply).result?.server_requests);
  } finally {socket.close()}
  await new Promise((resolve,reject)=>{const replay=new WebSocket(BASE.replace('http','ws')+'/api/chat?ticket='+ticket,{origin:BASE});replay.once('open',()=>{replay.close();reject(new Error('Ticket replay must fail'))});replay.once('error',resolve)});
});

test('model configuration exposes only a presence flag and rejects cross-origin credential requests',async()=>{
 const response=await fetch(BASE+'/api/model-settings',{headers});assert.equal(response.status,200);const cfg=await response.json();assert.equal(typeof cfg.has_key,'boolean');assert.ok(!('api_key' in cfg));assert.ok(!('key' in cfg));
 assert.equal((await fetch(BASE+'/api/model-settings/test',{method:'POST',headers:{...headers,Origin:'https://example.org'},body:'{}'})).status,403);
 assert.equal((await fetch(BASE+'/api/model-settings',{method:'PUT',headers:{cookie,'Content-Type':'application/json'},body:'{}'})).status,403);
});
