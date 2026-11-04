import test from 'node:test';import assert from 'node:assert/strict';
import {createResourceRefresh} from '../src/refresh.mjs';
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};};
test('idle chat only refreshes requested resources and coalesces in-flight refreshes',async()=>{
 let clock=0;const calls=[],applied=[],pending=deferred();const pool=createResourceRefresh({now:()=>clock,load:async name=>{calls.push(name);if(name==='inbox'&&clock===0)await pending.promise;return name;},apply:(...args)=>applied.push(args)});
 const initial=pool.refresh(['overview','sessions','inbox']),duplicate=pool.refresh(['overview','sessions','inbox']);pending.resolve();await Promise.all([initial,duplicate]);assert.equal(calls.length,3);
 for(clock=15_000;clock<=150_000;clock+=15_000)await pool.refresh(['overview','sessions','inbox']);
 assert.equal(calls.filter(n=>n==='inbox').length,11);assert.equal(calls.filter(n=>n==='overview').length,3);assert.equal(calls.filter(n=>n==='sessions').length,3);assert.equal(calls.length,17);assert.ok(!calls.includes('documents'));assert.ok(!calls.includes('stickers'));assert.ok(!calls.includes('curiosity'));
 await pool.refresh(['stickers','documents']);await pool.refresh(['stickers','documents']);assert.equal(calls.filter(n=>n==='stickers').length,1);assert.equal(calls.filter(n=>n==='documents').length,1);
});
test('mutation refresh wins over a late response and does not clear its pending request',async()=>{
 const old=deferred(),fresh=deferred(),applied=[];let n=0;const pool=createResourceRefresh({load:()=>++n===1?old.promise:fresh.promise,apply:(_,v)=>applied.push(v)});
 const a=pool.get('documents'),b=pool.get('documents',{force:true});old.resolve('obsolete');await a;const c=pool.get('documents');fresh.resolve('saved');await Promise.all([b,c]);assert.equal(n,2);assert.deepEqual(applied,['saved']);assert.equal(await pool.get('documents'),'saved');
});
test('one failed resource does not block independent data or poison the retry cache',async()=>{
 const calls=[],applied=[];let fail=true;const pool=createResourceRefresh({load:async n=>{calls.push(n);if(n==='inbox'&&fail)throw Error('offline');return n;},apply:n=>applied.push(n)});
 await assert.rejects(pool.refresh(['overview','inbox']),/offline/);assert.deepEqual(applied,['overview']);fail=false;await pool.refresh(['overview','inbox']);assert.deepEqual(calls,['overview','inbox','inbox']);
});
test('invalidating on completion loads fresh data without waking unrelated resources',async()=>{
 const calls=[];const pool=createResourceRefresh({load:async n=>{calls.push(n);return n;},apply:()=>{}});await pool.refresh(['overview','sessions']);pool.invalidate();await pool.refresh(['sessions']);assert.deepEqual(calls,['overview','sessions','sessions']);
});
