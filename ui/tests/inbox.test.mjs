import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { deliveryDecision, SOCIAL_DEFAULTS, createInbox } from '../server/inbox.mjs';

const noon = Date.parse('2026-10-27T12:00:00+08:00');
const candidate = { created_at: new Date(noon - 60000).toISOString(), source_url: 'https://example.org/interesting' };
test('quiet hours, cooldown, daily cap, recent conversation and duplicates prevent interruptions', () => {
  const decide = (history = [], settings = SOCIAL_DEFAULTS, now = noon, active = 0) => deliveryDecision(candidate, history, settings, now, active);
  assert.equal(decide(), 'send');
  assert.equal(decide([], { ...SOCIAL_DEFAULTS, enabled: false }), 'wait');
  assert.equal(decide([], SOCIAL_DEFAULTS, Date.parse('2026-10-27T23:00:00+08:00')), 'wait');
  assert.equal(decide([], SOCIAL_DEFAULTS, noon, noon - 1000), 'wait');
  assert.equal(decide([{ source_url: 'https://example.org/other', sent_at: new Date(noon - 3600000).toISOString() }]), 'wait');
  assert.equal(decide([{ source_url: candidate.source_url, sent_at: new Date(noon - 6 * 3600000).toISOString() }]), 'duplicate');
  const later = Date.parse('2026-10-27T21:00:00+08:00');
  assert.equal(decide([9, 14].map(hour => ({ source_url: 'other' + hour, sent_at: `2026-10-27T${String(hour).padStart(2, '0')}:00:00+08:00` })), SOCIAL_DEFAULTS, later), 'wait');
  assert.equal(decide([], SOCIAL_DEFAULTS, noon + 25 * 3600000), 'expired');
});
test('a long running reply still defers delivery, then completion starts a full activity cooldown',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-long-reply-'));t.after(()=>rm(root,{recursive:true,force:true}));
 let now=noon,busy=true;const inbox=createInbox(root,()=>now,{isBusy:()=>busy});inbox.activity();
 await inbox.queueLocal({kind:'balance',text:'虚构余额提醒，只供本机测试。',dedupe_key:'fixture-balance'});
 now+=30*60000;await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,0);assert.equal((await inbox.snapshot()).can_interrupt,false);
 busy=false;inbox.activity();now+=9*60000;await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,0);
 now+=60000;await inbox.tick();const snapshot=await inbox.snapshot();assert.equal(snapshot.messages.length,1);assert.equal(snapshot.can_interrupt,true);assert.deepEqual(snapshot.alert_ids,[snapshot.messages[0].id]);
});
test('old, read, expired and already alerted messages stay in the inbox without another automatic alert',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-alert-age-'));t.after(()=>rm(root,{recursive:true,force:true}));await mkdir(path.join(root,'data'));
 const base={kind:'study',text:'虚构学习搭子的消息。',read_at:null,notified_at:null,pet_notified_at:null,sent_at:new Date(noon-60000).toISOString()};
 const messages=[{...base,id:'fresh'},{...base,id:'old',sent_at:new Date(noon-16*60000).toISOString()},{...base,id:'read',read_at:new Date(noon).toISOString()},{...base,id:'notified',notified_at:new Date(noon).toISOString()},{...base,id:'pet',pet_notified_at:new Date(noon).toISOString()},{...base,id:'expired',expires_at:new Date(noon-1).toISOString()}];
 await writeFile(path.join(root,'data/inbox.json'),JSON.stringify({messages,processed:[]}));let busy=false;
 const inbox=createInbox(root,()=>noon,{isBusy:()=>busy});let result=await inbox.snapshot();assert.deepEqual(result.alert_ids,['fresh']);assert.equal(result.messages.length,6);
 busy=true;result=await inbox.snapshot();assert.equal(result.can_interrupt,false);assert.deepEqual(result.alert_ids,['fresh']);
});
test('an unavailable busy signal cannot allow a proactive message',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-busy-unavailable-'));t.after(()=>rm(root,{recursive:true,force:true}));
 const inbox=createInbox(root,()=>noon,{isBusy(){throw Error('fixture offline')}});await inbox.queueLocal({kind:'balance',text:'虚构测试提醒。',dedupe_key:'fixture'});await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,0);
});
test('verified discoveries persist once; unverified links and low-value candidates never become messages', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'bigfish-inbox-'));
  try {
    await mkdir(path.join(root, 'data/outbox'), { recursive: true });
    await mkdir(path.join(root, 'reports/2026-10-27'), { recursive: true });
    await writeFile(path.join(root, 'reports/2026-10-27/1200-surf.md'), candidate.source_url);
    await writeFile(path.join(root, 'data/surf-state.json'), JSON.stringify({ visited: [{ url: candidate.source_url }] }));
    const entry = { ...candidate, created_at: new Date(noon).toISOString(), worth_sharing: true, why_share: '具体的新发现，确实值得和你聊', text: '这个设计居然把问题绕过去了，有点东西。', report_path: 'reports/2026-10-27/1200-surf.md' };
    await writeFile(path.join(root, 'data/outbox/valid.json'), JSON.stringify(entry));
    await writeFile(path.join(root, 'data/outbox/unverified.json'), JSON.stringify({ ...entry, source_url: 'https://example.org/made-up' }));
    await writeFile(path.join(root, 'data/outbox/boring.json'), JSON.stringify({ ...entry, worth_sharing: false }));
    const inbox = createInbox(root, () => noon); await inbox.tick(); await inbox.tick();
    const snapshot = await inbox.snapshot();
    assert.equal(snapshot.messages.length, 1);
    await inbox.update(snapshot.messages[0].id, {read:true});
    assert.equal((await createInbox(root).snapshot()).unread, 0);
    assert.ok(snapshot.messages.every(m => m.source_url === candidate.source_url));
    await inbox.settings(false); assert.equal((await inbox.snapshot()).settings.enabled, false);
  } finally { await rm(root, { recursive: true, force: true }); }
});
test('followup labels require a real completed run, current thread and matching read receipt',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-followup-'));t.after(()=>rm(root,{recursive:true,force:true}));
 await mkdir(path.join(root,'data/outbox'),{recursive:true});await mkdir(path.join(root,'data/curiosity'),{recursive:true});await mkdir(path.join(root,'reports/2026-10-27'),{recursive:true});
 const report='reports/2026-10-27/1200-surf.md',thread='cur-123456789abc',run='browse-1234567890abcdef';
 await writeFile(path.join(root,report),candidate.source_url);
 await writeFile(path.join(root,'data/surf-state.json'),JSON.stringify({visited:[{url:candidate.source_url,report,read_at:new Date(noon-60000).toISOString()}]}));
 await writeFile(path.join(root,'data/curiosity/state.json'),JSON.stringify({threads:[{id:thread,question:'折叠机关是怎么收起来的？',status:'open',expires_at:'2026-11-01T00:00:00+08:00'}],runs:[{id:run,thread_id:thread,status:'finished',report_path:report,started_at:new Date(noon-300000).toISOString()}]}));
 const entry={...candidate,worth_sharing:true,why_share:'这次确实看到了上次还没弄懂的结构。',text:'这回终于看到抽屉底下的转轴了，原来藏在这里。',report_path:report,thread_id:thread,browse_run_id:run};
 await writeFile(path.join(root,'data/outbox/valid.json'),JSON.stringify(entry));await writeFile(path.join(root,'data/outbox/forged.json'),JSON.stringify({...entry,browse_run_id:'made-up'}));
 const inbox=createInbox(root,()=>noon);await inbox.tick();const data=await inbox.snapshot();assert.equal(data.messages.length,1);assert.equal(data.messages[0].thread_id,thread);assert.equal(data.messages[0].thread_question,'折叠机关是怎么收起来的？');
});
test('followup with an invalid expiry is rejected rather than bypassing the date guard',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-invalid-followup-'));t.after(()=>rm(root,{recursive:true,force:true}));
 const report='reports/2026-10-27/1200-surf.md',thread='cur-123456789abc',run='browse-1234567890abcdef';
 await mkdir(path.join(root,'data/outbox'),{recursive:true});await mkdir(path.join(root,'data/curiosity'),{recursive:true});await mkdir(path.join(root,'reports/2026-10-27'),{recursive:true});
 await writeFile(path.join(root,report),candidate.source_url);await writeFile(path.join(root,'data/surf-state.json'),JSON.stringify({visited:[{url:candidate.source_url,report,read_at:new Date(noon-60000).toISOString()}]}));
 await writeFile(path.join(root,'data/curiosity/state.json'),JSON.stringify({threads:[{id:thread,status:'open',expires_at:'bad date'}],runs:[{id:run,thread_id:thread,status:'finished',report_path:report,started_at:new Date(noon-300000).toISOString()}]}));
 await writeFile(path.join(root,'data/outbox/invalid.json'),JSON.stringify({...candidate,worth_sharing:true,why_share:'新内容的说明够长。',text:'这次看到了不同的结构，有一个新想法。',report_path:report,thread_id:thread,browse_run_id:run}));
 const inbox=createInbox(root,()=>noon);await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,0);
});
