import test from 'node:test';
import assert from 'node:assert/strict';
import { ChatSessions } from '../server/chat.mjs';

function peer() {
  const calls = [], events = [];
  return { session: '', calls, events, rpc: async (method, params) => { calls.push({ method, params }); return { closed: true }; }, emit: event => events.push(event) };
}
test('switching through many conversations releases runtimes without deleting stored history', async () => {
  const pool = new ChatSessions(), viewer = peer();
  for (let i = 0; i < 8; i++) {
    pool.attach(viewer, { session_id: 'runtime-' + i, stored_session_id: 'history-' + i });
    pool.begin(viewer); pool.complete(viewer.session); await pool.release(viewer);
    assert.equal(pool.sessions.size, 0); assert.equal(viewer.session, '');
  }
  assert.equal(viewer.calls.length, 8);
  assert.ok(viewer.calls.every(call => call.method === 'session.close' && call.params.session_id.startsWith('runtime-')));
});
test('capacity recovery reclaims idle peers but never a running reply', async () => {
  let time = 0; const pool = new ChatSessions({ now: () => time }), idle = peer(), busy = peer(), current = peer();
  pool.attach(idle, { session_id: 'idle' }); time++;
  pool.attach(busy, { session_id: 'busy' }); pool.begin(busy); time++;
  pool.attach(current, { session_id: 'current' }); pool.begin(current);
  assert.equal(await pool.reclaim('current'), true);
  assert.equal(idle.calls.length, 1); assert.equal(busy.calls.length, 0);
  assert.equal(idle.events[0].params.type, 'fish.session.released');
  assert.equal(await pool.reclaim('current'), false);
  await assert.rejects(() => pool.release(busy), /停止当前回复/);
});
test('a viewer switching away does not tear down a conversation still open in another window', async () => {
  const pool = new ChatSessions(), first = peer(), second = peer();
  pool.attach(first, { session_id: 'shared' }); pool.attach(second, { session_id: 'shared' });
  await pool.release(first); assert.equal(first.calls.length, 0); assert.equal(second.session, 'shared');
  await pool.release(second); assert.equal(second.calls.length, 1); assert.equal(pool.sessions.size, 0);
});
test('idle eviction waits for its timeout and preserves busy sessions', async () => {
  let now = 0; const pool = new ChatSessions({ idleMs: 100, now: () => now }), idle = peer(), busy = peer();
  pool.attach(idle, { session_id: 'idle' }); pool.attach(busy, { session_id: 'busy' }); pool.begin(busy);
  now = 99; await pool.reclaim('', true); assert.equal(idle.calls.length, 0);
  now = 101; await pool.reclaim('', true); assert.equal(idle.calls.length, 1); assert.equal(busy.calls.length, 0);
});
test('failed cleanup retains ownership so the next attempt can recover', async () => {
  const pool = new ChatSessions(), viewer = peer(); pool.attach(viewer, { session_id: 'retry' });
  viewer.rpc = async () => { throw new Error('offline'); }; pool.sessions.get('retry').rpc = viewer.rpc;
  await assert.rejects(() => pool.release(viewer), /offline/); assert.equal(viewer.session, 'retry');
  pool.sessions.get('retry').rpc = async () => ({ closed: true }); await pool.release(viewer);
  assert.equal(pool.sessions.size, 0);
});
