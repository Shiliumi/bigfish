import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {greetingCandidates,deliveryDecision,SOCIAL_DEFAULTS} from '../server/social.mjs';
import {createInbox} from '../server/inbox.mjs';
import {classifyBalance,createBalance,balanceNotice,insufficientBalance} from '../server/balance.mjs';
const at = time => Date.parse('2026-10-27T'+time+':00+08:00');
test('Beijing greetings have short windows, no missed catch-up, and no source fabrication',()=>{
  assert.equal(greetingCandidates(at('08:59')).length,0);
  assert.equal(greetingCandidates(at('09:05'))[0].kind,'greeting');
  assert.equal(greetingCandidates(at('09:05'))[0].source_url,undefined);
  assert.equal(greetingCandidates(at('12:00')).length,0);
  assert.equal(greetingCandidates(at('21:31'))[0].source_title,'晚安，明天再唠');
  assert.equal(greetingCandidates(at('22:00')).length,0);
  assert.equal(greetingCandidates(at('09:05'),{...SOCIAL_DEFAULTS,greetings:false}).length,0);
});
test('greetings and credit notices have their own once-only caps; typing and quiet hours still defer',()=>{
  const now=at('09:05'), greeting=greetingCandidates(now)[0];
  assert.equal(deliveryDecision(greeting,[],SOCIAL_DEFAULTS,now),'send');
  assert.equal(deliveryDecision(greeting,[],SOCIAL_DEFAULTS,now,now-1000),'wait');
  assert.equal(deliveryDecision(greeting,[{...greeting,sent_at:new Date(now).toISOString()}],SOCIAL_DEFAULTS,now),'duplicate');
  const credit={...balanceNotice({status:'empty'},now),created_at:new Date(now).toISOString()};
  assert.equal(deliveryDecision(credit,[],SOCIAL_DEFAULTS,at('23:00')),'wait');
  assert.equal(deliveryDecision(credit,[{kind:'balance',sent_at:new Date(now-60000).toISOString()}],SOCIAL_DEFAULTS,now),'duplicate');
  assert.equal(deliveryDecision(greeting,[],{...SOCIAL_DEFAULTS,enabled:false},now),'wait');
});
test('routine greetings persist once across restart and can be acknowledged separately by the pet',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'fish-social-'));let clock=at('09:05');
  try{
    let inbox=createInbox(root,()=>clock);await inbox.tick();await inbox.tick();
    let data=await inbox.snapshot();assert.equal(data.messages.length,1);assert.equal(data.messages[0].source_url,undefined);
    const id=data.messages[0].id;await inbox.update(id,{pet_notified:true});assert.ok((await inbox.snapshot()).messages[0].pet_notified_at);
    inbox=createInbox(root,()=>clock);await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,1);
    clock=at('21:31');await inbox.tick();data=await inbox.snapshot();assert.equal(data.messages.length,2);
    await inbox.settings(false);clock=Date.parse('2026-10-28T09:05:00+08:00');await inbox.tick();assert.equal((await inbox.snapshot()).messages.length,2);
  }finally{await rm(root,{recursive:true,force:true});}
});
test('credit classification uses provider evidence and never confuses rate/session limits with balance',()=>{
  assert.equal(classifyBalance({is_available:false,balance_infos:[]}).status,'empty');
  assert.equal(classifyBalance({is_available:true,balance_infos:[{currency:'CNY',total_balance:'0.50'}]}).status,'low');
  assert.equal(classifyBalance({is_available:true,balance_infos:[{currency:'CNY',total_balance:'5.50'}]}).status,'ready');
  assert.equal(classifyBalance({}).status,'unknown');assert.equal(balanceNotice({status:'unknown'},at('12:00')),null);
  assert.ok(insufficientBalance('HTTP 402 Insufficient Balance'));
  assert.ok(insufficientBalance({status_code:402}));assert.ok(insufficientBalance({error:{message:'Insufficient Balance'}}));
  assert.ok(!insufficientBalance('429 rate limit'));assert.ok(!insufficientBalance('active session limit (2/2)'));
});
test('balance fetch is cached, private, and targets only the official read-only endpoint',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'fish-balance-'));let calls=0;const states=[];
  try{
    await mkdir(path.join(root,'.hermes'));await writeFile(path.join(root,'.hermes/.env'),'DEEPSEEK_API_KEY="fixture-key"\n');
    const reader=createBalance(root,{clock:()=>at('12:00'),fetcher:async(url,options)=>{calls++;assert.equal(url,'https://api.deepseek.com/user/balance');assert.equal(options.headers.Authorization,'Bearer fixture-key');return {ok:true,json:async()=>({is_available:false,balance_infos:[{currency:'CNY',total_balance:'0.00'}]})};},onState:async s=>states.push(s.status)});
    await Promise.all([reader.refresh(),reader.refresh()]);await reader.refresh();assert.equal(calls,1);assert.equal(reader.snapshot().status,'empty');assert.ok(!JSON.stringify(reader.snapshot()).includes('fixture-key'));
    await reader.refresh(true);assert.equal(calls,2);assert.deepEqual(states,['empty','empty']);
  }finally{await rm(root,{recursive:true,force:true});}
});
