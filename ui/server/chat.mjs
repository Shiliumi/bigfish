import { WebSocket } from 'ws';
import { insufficientBalance } from './balance.mjs';

const rpcError = (message, code = 4001) => Object.assign(new Error(message), { code });
export class ChatSessions {
  sessions = new Map();
  constructor({ idleMs = 300000, now = Date.now } = {}) { this.idleMs = idleMs; this.now = now; }
  attach(peer, result) {
    const id = result.session_id;
    let state = this.sessions.get(id);
    if (!state) { state = { id, peers: new Set(), busy: false, used: this.now(), rpc: peer.rpc }; this.sessions.set(id, state); }
    state.peers.add(peer); state.busy = Boolean(result.running) || state.busy; state.used = this.now();
    peer.session = id;
  }
  begin(peer) {
    const state = this.sessions.get(peer.session);
    if (!state || state.closing) throw rpcError('会话已暂存，请重新连接这段对话。');
    state.busy = true; state.activity = 'thinking'; state.used = this.now();
  }
  complete(id) { const state = this.sessions.get(id); if (state) { state.busy = false; state.used = this.now(); } }
  activity(event) {
    const state = this.sessions.get(event?.session_id);
    if (!state?.busy) return;
    if (event.type === 'tool.start') state.activity = /browser|web_search|web_extract/.test(event.payload?.name || '') ? 'surfing' : 'working';
    if (event.type === 'tool.complete' || event.type === 'message.delta') state.activity = 'thinking';
  }
  snapshot() { return [...this.sessions.values()].filter(s => s.busy).map(s => s.activity || 'thinking'); }
  async close(state) {
    if (state.busy) return false;
    if (state.closing) return state.closing;
    state.closing = (async () => {
      try {
        await state.rpc('session.close', { session_id: state.id, profile: 'default' });
        this.sessions.delete(state.id);
        for (const peer of state.peers) {
          if (peer.session === state.id) peer.session = '';
          peer.emit({ jsonrpc: '2.0', method: 'event', params: { type: 'fish.session.released', session_id: state.id, payload: {} } });
        }
        return true;
      } catch (error) { state.closing = null; throw error; }
    })();
    return state.closing;
  }
  async release(peer) {
    const state = this.sessions.get(peer.session);
    if (!state) { peer.session = ''; return; }
    if (state.busy) throw rpcError('请先停止当前回复，再切换对话。', 4009);
    if (state.peers.size === 1) { await this.close(state); return; }
    state.peers.delete(peer); state.rpc = [...state.peers][0].rpc; peer.session = '';
  }
  detach(peer) {
    const state = this.sessions.get(peer.session);
    if (state) { state.peers.delete(peer); if (state.peers.size) state.rpc = [...state.peers][0].rpc; else this.sessions.delete(state.id); }
    peer.session = '';
  }
  async reclaim(except = '', expiredOnly = false) {
    const candidates = [...this.sessions.values()].filter(state => state.id !== except && !state.busy && !state.closing && (!expiredOnly || this.now() - state.used >= this.idleMs)).sort((a, b) => a.used - b.used);
    for (const state of candidates) {
      if (await this.close(state)) { if (!expiredOnly) return true; }
    }
    return false;
  }
}

const sessions = new ChatSessions();
export const chatActivity = () => sessions.snapshot();
const reap = setInterval(() => sessions.reclaim('', true).catch(() => {}), 30000); reap.unref();
const capacity = error => /active session limit|MAX_CONCURRENT_SESSIONS/.test(error.message || '');
const allowed = new Set(['client.capabilities', 'session.create', 'session.resume', 'session.list', 'session.title', 'session.interrupt', 'session.close', 'session.release', 'prompt.submit', 'approval.respond', 'approval.received', 'approval.pending', 'request.answer', 'gateway.ping']);

export function attachChatClient(client, { nativeUrl, root, onPrompt, onBalanceFailure = () => {} }) {
  const upstream = new WebSocket(nativeUrl, { origin: 'http://127.0.0.1:9119' });
  const pending = new Map(); let sequence = 0, work = Promise.resolve(), gone = false, mounting = false;
  let buffered = [];
  const ready = new Promise((resolve, reject) => { upstream.once('open', resolve); upstream.once('error', reject); upstream.once('close', () => reject(new Error('Hermes 连接已断开。'))); });
  ready.catch(() => {});
  const peer = {
    session: '',
    emit(frame) { if (client.readyState === WebSocket.OPEN) client.send(JSON.stringify(frame)); },
    async rpc(method, params) {
      await ready;
      if (upstream.readyState !== WebSocket.OPEN) throw new Error('Hermes 连接已断开。');
      const id = 'fish-rpc-' + ++sequence;
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => { pending.delete(id); reject(new Error('会话整理响应超时，请重试。')); }, 30000);
        pending.set(id, { resolve, reject, timer, method }); upstream.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }));
      });
    },
  };
  const forward = frame => {
    if (frame.method && frame.params?.session_id && frame.params.session_id !== peer.session) {
      if (frame.id && upstream.readyState === WebSocket.OPEN) upstream.send(JSON.stringify({jsonrpc:'2.0',id:frame.id,error:{code:4404,message:'此窗口当前没有显示这段对话。'}}));
      return;
    }
    peer.emit(frame);
  };
  const finishMount = () => { mounting = false; const events = buffered; buffered = []; for (const frame of events) forward(frame); };
  upstream.on('message', buffer => {
    for (const line of buffer.toString().split('\n').filter(Boolean)) {
      let frame; try { frame = JSON.parse(line); } catch { continue; }
      const request = pending.get(frame.id);
      if (request && !frame.method) {
        clearTimeout(request.timer); pending.delete(frame.id);
        if (frame.error) { if(insufficientBalance(frame.error.message))onBalanceFailure(); request.reject(Object.assign(new Error(frame.error.message), { code: frame.error.code, data: frame.error.data })); }
        else { if (['session.create','session.resume'].includes(request.method)) sessions.attach(peer,frame.result); request.resolve(frame.result); }
      } else {
        if(insufficientBalance(frame.params?.payload?.error||frame.params?.payload?.message))onBalanceFailure();
        sessions.activity(frame.params);
        if (frame.params?.type === 'message.complete') sessions.complete(frame.params.session_id);
        if (mounting && frame.method && frame.params?.session_id) buffered.push(frame);
        else forward(frame);
      }
    }
  });
  client.on('message', buffer => {
    let message; try { message = JSON.parse(buffer.toString()); } catch { return; }
    if (!message.method) { if (upstream.readyState === WebSocket.OPEN) upstream.send(JSON.stringify(message)); return; }
    work = work.then(async () => {
      if (gone) return;
      const { method, id } = message;
      try {
        if (!allowed.has(method)) throw rpcError('此界面暂不支持这个操作。', -32601);
        let params = method === 'client.capabilities' ? { ...message.params } : { ...message.params, profile: 'default' };
        if (method === 'session.release' || method === 'session.close') { await sessions.release(peer); peer.emit({ jsonrpc: '2.0', id, result: { closed: true } }); return; }
        if (method === 'session.create' || method === 'session.resume') {
          mounting = true;
          if (peer.session) await sessions.release(peer);
          params.close_on_disconnect = true;
          if (method === 'session.create') Object.assign(params, { cwd: root, cwd_explicit: true, source: 'bigfish' });
        }
        if (method === 'prompt.submit') {
          if (params.session_id !== peer.session) throw rpcError('会话已暂存，请重新连接这段对话。');
          sessions.begin(peer); onPrompt();
        }
        let result;
        try { result = await peer.rpc(method, params); }
        catch (error) {
          if (method === 'prompt.submit') sessions.complete(peer.session);
          // This typed admission refusal happens before a turn is accepted. Never retry an uncertain/network failure.
          if (method === 'prompt.submit' && capacity(error) && await sessions.reclaim(peer.session)) { sessions.begin(peer); try { result = await peer.rpc(method, params); } catch (retryError) { sessions.complete(peer.session); throw retryError; } }
          else throw error;
        }
        peer.emit({ jsonrpc: '2.0', id, result });
        if (method === 'session.create' || method === 'session.resume') finishMount();
      } catch (error) { peer.emit({ jsonrpc: '2.0', id, error: { code: error.code || -32000, message: error.message, ...(error.data ? { data: error.data } : {}) } }); if (method === 'session.create' || method === 'session.resume') finishMount(); }
    }).catch(() => {});
  });
  upstream.on('close', () => {
    for (const request of pending.values()) { clearTimeout(request.timer); request.reject(new Error('Hermes 连接已断开。')); }
    pending.clear(); sessions.detach(peer);
    if (client.readyState === WebSocket.OPEN) client.close(1012, '连接已更新，请重新连接。');
  });
  upstream.on('error', () => { if (client.readyState === WebSocket.OPEN) client.close(1011, 'Hermes 连接暂时不可用。'); });
  const disconnect = () => {
    if (gone) return; gone = true;
    // Give a refreshing/reconnecting client time to attach. Native close_on_disconnect then releases only the last viewer.
    const grace = sessions.sessions.get(peer.session)?.busy ? 5000 : 0;
    setTimeout(() => { sessions.detach(peer); upstream.close(); }, grace).unref();
  };
  client.on('close', disconnect); client.on('error', disconnect);
}
