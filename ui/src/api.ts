export class ChatError extends Error {
  constructor(message: string, public code?: number) {
    super(/active session limit|MAX_CONCURRENT_SESSIONS/.test(message) ? '另一个窗口正在回复，稍等片刻再发送。聊天记录已保留。' : message)
  }
}
export function friendlyAgentError(message: unknown): string {
  const value = message as any
  const text = typeof message === 'string' ? message : typeof value?.message === 'string' ? value.message : typeof value?.error?.message === 'string' ? value.error.message : message == null ? '' : JSON.stringify(message)
  return /insufficient[_ ]balance|余额不足|(?:HTTP|status(?:_code)?)[\s:'"=]*402\b/i.test(text) || value?.status === 402 || value?.status_code === 402 ? '爹，鱼粮见底了：模型服务提示余额不足。给我补点 token 呗，补好接着唠。' : text
}
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, { ...options, headers: { 'Content-Type': 'application/json', 'X-Fish-Client': 'studio', ...options.headers } })
  const data = await response.json()
  if (!response.ok) throw Object.assign(new Error(data.error || '操作没有成功，请稍后再试。'), {status:response.status})
  return data
}

export class FishGateway {
  private socket?: WebSocket
  private seq = 0
  private pending = new Map<number, { resolve: (data: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  private retry?: ReturnType<typeof setTimeout>
  private closed = false
  private connecting = false
  private heartbeat?: ReturnType<typeof setInterval>
  private checking = false
  onEvent: (frame: any) => void = () => {}
  onStatus: (connected: boolean) => void = () => {}
  async connect() {
    if (this.connecting || this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) return
    this.connecting = true; clearTimeout(this.retry)
    this.closed = false
    let ticket: string
    try { ticket = (await api<{ ticket: string }>('/chat-ticket')).ticket } catch (error) { this.connecting = false; if ((error as any).status === 401) await fetch('/',{cache:'no-store'}).catch(()=>{}); if (!this.closed) this.retry = setTimeout(() => this.connect(), 2500); return }
    this.connecting = false; if (this.closed) return
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/chat?ticket=${encodeURIComponent(ticket)}`)
    this.socket = socket
    socket.onopen = () => { this.onStatus(true); clearInterval(this.heartbeat); this.heartbeat = setInterval(() => this.checkConnection(), 20000) }
    socket.onmessage = event => {
      for (const line of String(event.data).split('\n').filter(Boolean)) {
        let frame: any; try { frame = JSON.parse(line) } catch { continue }
        const request = this.pending.get(frame.id)
        if (request && !frame.method) {
          clearTimeout(request.timer); this.pending.delete(frame.id)
          if (frame.error) request.reject(new ChatError(frame.error.message || '请求没有完成', frame.error.code))
          else request.resolve(frame.result)
        } else this.onEvent(frame)
      }
    }
    socket.onclose = () => {
      if (this.socket !== socket) return
      clearInterval(this.heartbeat); this.checking = false
      this.onStatus(false)
      for (const request of this.pending.values()) { clearTimeout(request.timer); request.reject(new Error('连接已断开，已发送的消息不会自动重复提交。')) }
      this.pending.clear()
      if (!this.closed) this.retry = setTimeout(() => this.connect(), 2500)
    }
    socket.onerror = () => socket.close()
  }
  async checkConnection() {
    if (this.closed || this.checking) return
    if (this.socket?.readyState !== WebSocket.OPEN) { void this.connect(); return }
    this.checking = true; const socket = this.socket
    try { await this.request('gateway.ping', {}, 8000) } catch { if (this.socket === socket) socket.close() }
    finally { this.checking = false }
  }
  request<T = any>(method: string, params: any = {}, timeout = 90000): Promise<T> {
    if (this.socket?.readyState !== WebSocket.OPEN) return Promise.reject(new Error('正在连接大肥鱼，请稍等一下。'))
    const id = ++this.seq
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('响应时间较长，请检查后台状态。')) }, timeout)
      this.pending.set(id, { resolve, reject, timer }); this.socket!.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }))
    })
  }
  answer(id: string | number, result: any) { this.socket?.send(JSON.stringify({ jsonrpc: '2.0', id, result })) }
  reject(id: string | number, message: string) { this.socket?.send(JSON.stringify({ jsonrpc: '2.0', id, error: { code: -32601, message } })) }
  dispose() { this.closed = true; clearTimeout(this.retry); clearInterval(this.heartbeat); this.socket?.close() }
}
