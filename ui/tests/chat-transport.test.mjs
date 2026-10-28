import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { WebSocket, WebSocketServer } from 'ws';
import { attachChatClient } from '../server/chat.mjs';

test('switching windows releases only unused chats and routes events to the current conversation', async () => {
  const native = new WebSocketServer({ port: 0, host: '127.0.0.1' }); await once(native, 'listening');
  const requests = [], closed = []; let serial = 0;
  native.on('connection', socket => socket.on('message', raw => {
    const frame = JSON.parse(raw); requests.push(frame);
    let result = {};
    if (frame.method === 'session.create') { const id = 'fixture-' + ++serial; result = { session_id: id, stored_session_id: 'stored-' + id, messages: [] }; }
    if (frame.method === 'session.resume') result = { session_id: frame.params.session_id, stored_session_id: 'stored-' + frame.params.session_id, messages: [] };
    if (frame.method === 'session.close') { closed.push(frame.params.session_id); result = { closed: true }; }
    const reply = JSON.stringify({ jsonrpc: '2.0', id: frame.id, result });
    if (frame.method === 'session.resume') socket.send(reply + '\n' + JSON.stringify({jsonrpc:'2.0',method:'event',params:{type:'message.delta',session_id:result.session_id,payload:{text:'resume-buffered-delta'}}}));
    else socket.send(reply);
  }));
  const server = http.createServer(), bridge = new WebSocketServer({ server });
  bridge.on('connection', client => attachChatClient(client, { nativeUrl: `ws://127.0.0.1:${native.address().port}`, root: '/test-fixture', onPrompt() {} }));
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const viewers = [];
  function viewer() {
    const socket = new WebSocket(`ws://127.0.0.1:${server.address().port}`), pending = new Map(), events = [], frames = []; let seq = 0;
    const opened = once(socket, 'open'); viewers.push(socket);
    socket.on('message', data => { const frame = JSON.parse(data); frames.push(frame); if (pending.has(frame.id)) { const p = pending.get(frame.id); pending.delete(frame.id); frame.error ? p.reject(new Error(frame.error.message)) : p.resolve(frame.result); } else events.push(frame); });
    return { events, frames, async rpc(method, params = {}) { await opened; const id = ++seq; return new Promise((resolve, reject) => { pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ jsonrpc: '2.0', id, method, params })); }); } };
  }
  try {
    const a = viewer(), b = viewer();
    const shared = await a.rpc('session.create'); await b.rpc('session.resume', { session_id: shared.session_id });
    await b.rpc('gateway.ping');
    assert.ok(b.frames.findIndex(f => f.id === 1) < b.frames.findIndex(f => f.params?.payload?.text === 'resume-buffered-delta'));
    assert.ok(b.events.some(f => f.params?.payload?.text === 'resume-buffered-delta'));
    const other = await a.rpc('session.create');
    assert.notEqual(shared.session_id, other.session_id); assert.ok(!closed.includes(shared.session_id));
    for (const socket of native.clients) socket.send(JSON.stringify({ jsonrpc: '2.0', method: 'event', params: { type: 'message.delta', session_id: shared.session_id, payload: { text: 'only the current viewer should see this' } } }));
    await a.rpc('gateway.ping'); await b.rpc('gateway.ping');
    assert.ok(!a.events.some(f => f.params?.type === 'message.delta'));
    assert.ok(b.events.some(f => f.params?.type === 'message.delta'));
    await b.rpc('session.release'); assert.ok(closed.includes(shared.session_id)); await a.rpc('session.release');
    assert.ok(requests.filter(r => ['session.create', 'session.resume'].includes(r.method)).every(r => r.params.close_on_disconnect === true));
  } finally {
    for (const socket of viewers) socket.close();
    for (const socket of bridge.clients) socket.terminate(); for (const socket of native.clients) socket.terminate();
    await new Promise(resolve => bridge.close(resolve)); await new Promise(resolve => server.close(resolve)); await new Promise(resolve => native.close(resolve));
  }
});
