import test from 'node:test';
import assert from 'node:assert/strict';
import { companionState } from '../server/companion.mjs';
import { ChatSessions } from '../server/chat.mjs';

test('activity wins over unread mail, then returns to idle or a new letter', () => {
  assert.equal(companionState({activities:['thinking'],unread:2}).state,'thinking');
  assert.equal(companionState({activities:['surfing'],unread:2}).animation,'working');
  assert.equal(companionState({jobs:[{name:'fish-surf',latest_execution:{status:'running'}}]}).state,'thinking');
  assert.equal(companionState({jobs:[{name:'fish-surf',latest_execution:{status:'running'}}],outingStarted:true}).state,'surfing');
  assert.equal(companionState({unread:2}).state,'letter');
  assert.equal(companionState().state,'idle');
  assert.equal(companionState({connected:false,unread:2}).state,'offline');
});
test('runtime activity is removed after completion or disconnect', () => {
  const sessions = new ChatSessions(), peer = { rpc() {} };
  sessions.attach(peer,{session_id:'live'}); sessions.begin(peer);
  assert.deepEqual(sessions.snapshot(),['thinking']);
  sessions.activity({session_id:'unrelated',type:'tool.start',payload:{name:'browser_exec'}});
  assert.deepEqual(sessions.snapshot(),['thinking']);
  sessions.activity({session_id:'live',type:'tool.start',payload:{name:'browser_exec'}});
  assert.deepEqual(sessions.snapshot(),['surfing']);
  sessions.complete('live'); assert.deepEqual(sessions.snapshot(),[]);
  sessions.begin(peer); sessions.detach(peer); assert.deepEqual(sessions.snapshot(),[]);
});
