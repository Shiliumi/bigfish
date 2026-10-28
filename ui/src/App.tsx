import HermesPanel from './HermesPanel'
const MemoryTimeline = lazy(() => import('./MemoryTimeline'))
const PreferencePanel = lazy(() => import('./PreferencePanel'))
import ModelSettings from './ModelSettings'
import { Component, lazy, Suspense, memo, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ArrowDown, ArrowRight, ArrowUp, BookOpen, Brain, Check, CheckCheck, ChevronDown, ChevronLeft, ChevronRight, Clock3, Compass, Copy, ExternalLink, FileText, Globe2, Heart, Mail, Smile, Menu, MessageCircle, MoreHorizontal, Pause, Pencil, Play, Plus, RefreshCw, Search, Send, Settings2, Sparkles, Square, Waves, X, Zap } from 'lucide-react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, ChatError, FishGateway, friendlyAgentError } from './api'
import { Whale } from './Whale'
import { Companion } from './Companion'
import { publishPetChat } from './petChat'

type Page = 'chat' | 'explore' | 'memory' | 'routines' | 'inbox' | 'stickers' | 'hermes'
interface Report { id: string; title: string; type: string; date: string; preview: string; content: string; modified: string }
interface Job { id: string; name: string; enabled: boolean; next_run_at: string; last_status?: string; last_run_at?: string; schedule: { expr: string }; latest_execution?: { status: string } }
interface Overview { connected: boolean; model: string; jobs: Job[]; reports: Report[]; visited: { url: string; title: string; read_at: string }[]; memories: number }
interface Message { id: string; role: 'user' | 'assistant'; text: string; error?: boolean }
interface Session { id: string; title: string; preview?: string; message_count: number; source?: string }
interface Letter { id: string; text: string; source_url?: string; source_title: string; kind?: 'surf' | 'greeting' | 'balance' | 'study'; sent_at: string; read_at: string | null; session_id?: string; sticker_id?: string }
interface Sticker { id: string; name: string; emotion: string; tags: string[]; use: string; source: string; author: string; image_url: string }
interface Inbox { messages: Letter[]; unread: number; settings: { enabled: boolean; dailyLimit: number; minGapHours: number; quietStart: number; quietEnd: number; greetings: boolean; morning: string; night: string } }
interface Curiosity {threads:{id:string;question:string;why:string;source_urls:string[];cooling_down:boolean}[];used_today:number;daily_limit:number;last_outing:{question:string;status:string;outcome:string|null;reason:string|null}|null}
interface Document { content: string; version: string }
const pages = [{ id: 'chat', label: '和鱼聊聊', icon: MessageCircle }, { id: 'explore', label: '探索日志', icon: Compass }, { id: 'memory', label: '记忆空间', icon: Brain }, { id: 'inbox', label: '鱼的来信', icon: Mail }, { id: 'stickers', label: '她的表情', icon: Smile }, { id: 'routines', label: '日常安排', icon: Clock3 }, { id: 'hermes', label: '鱼塘控制室', icon: Zap }] as const
const dateLabel = (value?: string, timeOnly = false) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', ...(timeOnly ? {} : { month: '2-digit', day: '2-digit' }), hour: '2-digit', minute: '2-digit', hour12: false }) : '还没有安排'
const textContent = (value: any): string => typeof value === 'string' ? value : Array.isArray(value) ? value.map(v => v.text || '').join('') : ''
const mapMessages = (items: any[] = []): Message[] => items.filter(m => ['user', 'assistant'].includes(m.role) && textContent(m.content ?? m.text).trim()).map((m, i) => ({ id: String(m.id || i), role: m.role, text: textContent(m.content ?? m.text) }))
const scheduleLabel = (expression: string) => {
  const parts = expression.trim().split(/\s+/)
  if (parts.length === 5 && parts.slice(2).every(p => p === '*') && /^\d{1,2}$/.test(parts[0]) && /^\d{1,2}(,\d{1,2})*$/.test(parts[1]) && Number(parts[0]) < 60 && parts[1].split(',').every(h => Number(h) < 24)) return parts[1].split(',').map(h => h.padStart(2, '0') + ':' + parts[0].padStart(2, '0')).join('  /  ')
  return expression
}
const activityLabel: Record<string, string> = { browser_exec: '正在浏览网页', web_search: '正在寻找线索', web_extract: '正在阅读内容', memory: '正在整理记忆', read_file: '正在翻阅笔记', write_file: '正在记录发现', terminal: '正在处理任务', session_search: '正在回想我们的对话' }
const markdownComponents: Components = {
  table: ({ node, ...props }) => <div className="table-scroll"><table {...props} /></div>,
  img: ({ src, alt }) => <img src={src} alt={alt || '图片'} className={/^\/api\/stickers\/[a-f0-9]{16}$/.test(src || '') ? 'chat-sticker' : 'message-image'} loading="lazy" />,
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
}
const Markdown = memo(function Markdown({ children }: { children: string }) { return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{children}</ReactMarkdown></div> })
function Modal({ title, subtitle, children, close, wide = false }: { title: string; subtitle?: string; children: ReactNode; close: () => void; wide?: boolean }) {
  const container = useRef<HTMLDivElement>(null)
  useEffect(() => { const previous = document.activeElement as HTMLElement; container.current?.focus(); const key = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); if (e.key === 'Tab') { const focusable = container.current?.querySelectorAll<HTMLElement>('button,textarea,input,select,a[href]'); if (!focusable?.length) return; const first = focusable[0], last = focusable[focusable.length - 1]; if (e.shiftKey && (document.activeElement === first || document.activeElement === container.current)) { e.preventDefault(); last.focus() } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() } } }; window.addEventListener('keydown', key); return () => { window.removeEventListener('keydown', key); previous?.focus() } }, [])
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && close()}><div ref={container} tabIndex={-1} className={'modal ' + (wide ? 'wide' : '')} role="dialog" aria-modal="true" aria-label={title}><header><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label="关闭弹窗" onClick={close}><X size={20} /></button></header>{children}</div></div>
}

function readEditorDraft(): {key:string;content:string;version:string} | null {
  try { const value = JSON.parse(localStorage.getItem('fish.editorDraft') || 'null'); return value && ['memory','user','interests','soul'].includes(value.key) && typeof value.content === 'string' && typeof value.version === 'string' ? value : null } catch { return null }
}
class MemoryBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = {failed:false}
  static getDerivedStateFromError() { return {failed:true} }
  render() { return this.state.failed ? <div role="alert" className="learning-error"><p>回忆页面暂时没打开，聊天草稿已留在本机。</p><button className="secondary-button" onClick={()=>window.location.reload()}>重新打开鱼塘</button></div> : this.props.children }
}
export default function App() {
  const [bootEditor] = useState(readEditorDraft), editorVersion = useRef(bootEditor?.version || '')
  const [page, setPage] = useState<Page>(() => { const saved = localStorage.getItem('fish.page'); return pages.some(p => p.id === saved) ? saved as Page : 'chat' }), [overview, setOverview] = useState<Overview | null>(null), [sessions, setSessions] = useState<Session[]>([])
  const [connected, setConnected] = useState(false), [messages, setMessages] = useState<Message[]>([]), [input, setInput] = useState(() => localStorage.getItem('fish.draft') || ''), [busy, setBusy] = useState(false), [restoring, setRestoring] = useState(false)
  const [curiosity,setCuriosity] = useState<Curiosity|null>(null)
  const [sessionModel, setSessionModel] = useState('')
  const [activity, setActivity] = useState(''), [toast, setToast] = useState(''), [mobileNav, setMobileNav] = useState(false), [report, setReport] = useState<Report | null>(null)
  const [docs, setDocs] = useState<Record<string, Document>>({}), [editor, setEditor] = useState<string | null>(bootEditor?.key || null), [draft, setDraft] = useState(bootEditor?.content || ''), [saving, setSaving] = useState(false)
  const [search, setSearch] = useState(''), [filter, setFilter] = useState('all'), [workingJob, setWorkingJob] = useState<string | null>(null), [approval, setApproval] = useState<any>(null)
  const [stickers, setStickers] = useState<Sticker[]>([]), [sticker, setSticker] = useState<Sticker | null>(null)
  const [inbox, setInbox] = useState<Inbox | null>(null), [pendingLetter, setPendingLetter] = useState(new URLSearchParams(location.search).get('letter')), [settings, setSettings] = useState(false), [about, setAbout] = useState(false), [notificationPermission, setNotificationPermission] = useState<number | null>(null)
  const inboxLoaded = useRef(false)
  const petTurn = useRef(false), petResponse = useRef(''), petLastUpdate = useRef(0)
  const gateway = useRef(new FishGateway()), sid = useRef(''), storedId = useRef(''), replyId = useRef(''), chatScroll = useRef<HTMLDivElement>(null), followChat = useRef(true), inputRef = useRef<HTMLTextAreaElement>(null), busyRef = useRef(false), didRestore = useRef(false), switching = useRef(false)
  const notify = (message: string) => setToast(message)
  useEffect(() => { localStorage.setItem('fish.page', page) }, [page])
  useEffect(() => { if (editor) localStorage.setItem('fish.editorDraft', JSON.stringify({key:editor,content:draft,version:editorVersion.current})); else localStorage.removeItem('fish.editorDraft') }, [editor,draft])
  useEffect(() => { (window as any).__FISH_UI_READY__ = true; (window as any).webkit?.messageHandlers.fish.postMessage({type:'ui.ready'}); return () => { (window as any).__FISH_UI_READY__ = false } }, [])
  useEffect(() => { if (input) localStorage.setItem('fish.draft', input); else localStorage.removeItem('fish.draft') }, [input])
  async function refresh() {
    const [ov, recent, documents, letters, collection, interests] = await Promise.all([api<Overview>('/overview'), api<any>('/sessions'), api<Record<string, Document>>('/documents'), api<Inbox>('/inbox'), api<{items:Sticker[]}>('/stickers'), api<Curiosity>('/curiosity')])
    setStickers(collection.items); setCuriosity(interests)
    setInbox(current => { if (inboxLoaded.current && current && letters.messages.some(m => !current.messages.some(old => old.id === m.id)) && !busyRef.current) notify('大肥鱼刚带回来一条发现，放在「鱼的来信」了。'); return letters }); inboxLoaded.current = true
    setOverview(ov); setSessions((Array.isArray(recent) ? recent : recent.sessions || []).filter((s: Session) => s.source === 'bigfish')); setDocs(documents)
  }
  const refreshRef = useRef(refresh); refreshRef.current = refresh
  async function releaseCurrent() {
    await gateway.current.request('session.release')
    sid.current = ''; setApproval(null)
  }
  async function connectConversation(text: string) {
    const result = storedId.current
      ? await gateway.current.request('session.resume', {session_id:storedId.current,source:'bigfish',inline_images:false})
      : await gateway.current.request('session.create', {title:text.slice(0,35),idempotency_key:crypto.randomUUID()})
    setSessionModel(result.info?.model || ''); sid.current = result.session_id; storedId.current = result.stored_session_id || storedId.current; localStorage.setItem('fish.session', storedId.current)
  }
  async function restore(id: string, show = true) {
    if (busyRef.current) return notify('等本鲸说完这句，再切换对话吧。')
    if (switching.current) return; switching.current = true; setRestoring(true)
    try { await releaseCurrent(); const result = await gateway.current.request('session.resume', { session_id: id, source: 'bigfish', inline_images: false }); setSessionModel(result.info?.model || ''); sid.current = result.session_id; storedId.current = result.stored_session_id || id; localStorage.setItem('fish.session', storedId.current); followChat.current = true; setMessages(mapMessages(result.messages)); busyRef.current = Boolean(result.running); setBusy(Boolean(result.running)); replyId.current = ''; if (result.running) { setActivity('正在继续处理'); if (result.inflight?.assistant) { replyId.current = crypto.randomUUID(); const id = replyId.current; setMessages(current => [...current, { id, role: 'assistant', text: result.inflight.assistant }]) } } for (const request of result.open_requests || []) { if (request.method === 'approval') setApproval(request) } if (result.pending_approval && !result.open_requests?.length) setApproval({ event: result.pending_approval }); if (show) setPage('chat'); setMobileNav(false) }
    catch (e) { notify((e as Error).message); if (e instanceof ChatError && e.code === 4007) localStorage.removeItem('fish.session') }
    finally { switching.current = false; setRestoring(false) }
  }
  const restoreRef = useRef(restore); restoreRef.current = restore
  useEffect(() => {
    refreshRef.current().catch(e => notify(e.message))
    const timer = setInterval(() => refreshRef.current().catch(() => {}), 15000)
    const client = gateway.current
    client.onStatus = value => { setConnected(value); if (!value) { if (petTurn.current) { publishPetChat('error', '连接断开了，这句没有自动重发。请连接恢复后再试。'); petTurn.current = false }; busyRef.current = false; setBusy(false); setActivity(''); setApproval(null); replyId.current = '' } if (value && !didRestore.current) { didRestore.current = true; const id = localStorage.getItem('fish.session'); if (id) void restoreRef.current(id, false) } else if (value && storedId.current) void restoreRef.current(storedId.current, false) }
    client.onEvent = frame => {
      if (frame.id && frame.method && frame.method !== 'event') { if (frame.method === 'approval') { if (petTurn.current) publishPetChat('approval', '这一步需要你确认，请打开完整聊天。'); setApproval(frame) } else { gateway.current.reject(frame.id, '应用暂不支持这类交互，这次请求已取消。'); notify('这类交互尚未接入应用，请换一种方式描述需求。') } return }
      const event = frame.params; if (!event?.type) return
      if (event.session_id && sid.current && event.session_id !== sid.current) return
      const payload = event.payload || {}
      if (event.type === 'fish.session.released') { sid.current = ''; setApproval(null); return }
      if (event.type === 'session.info' && typeof payload.model === 'string') setSessionModel(payload.model)
      if (event.type === 'gateway.ready') void gateway.current.request('client.capabilities', { server_requests: true }).catch(() => {})
      if (event.type === 'request.cancel') setApproval((current: any) => current?.id === payload.id ? null : current)
      if (event.type === 'message.delta' && payload.text) {
        if (petTurn.current) { petResponse.current += payload.text; if (Date.now() - petLastUpdate.current > 120) { petLastUpdate.current = Date.now(); publishPetChat('streaming', petResponse.current) } }
        if (!replyId.current) replyId.current = crypto.randomUUID()
        const id = replyId.current
        setMessages(current => current.some(m => m.id === id) ? current.map(m => m.id === id ? { ...m, text: m.text + payload.text } : m) : [...current, { id, role: 'assistant', text: payload.text }])
      }
      if (event.type === 'tool.start') setActivity(activityLabel[payload.name] || '正在动手处理')
      if (event.type === 'tool.complete') setActivity('正在组织回复')
      if (event.type === 'message.complete') {
        if (payload.error) payload.error = friendlyAgentError(payload.error)
        const id = replyId.current || crypto.randomUUID(), final = textContent(payload.text)
        if (petTurn.current) { publishPetChat(payload.error ? 'error' : 'complete', final || petResponse.current || payload.error || '这次没有生成回复，可以再试一次。'); petTurn.current = false }
        setMessages(current => { const found = current.some(m => m.id === id); const text = final || payload.error || (payload.status === 'interrupted' ? '已停止这次回复。' : '这次暂时没有生成回复，可以再试一次。'); return found ? current.map(m => m.id === id ? { ...m, text, error: Boolean(payload.error) } : m) : [...current, { id, role: 'assistant', text, error: Boolean(payload.error) }] })
        busyRef.current = false; setBusy(false); setActivity(''); replyId.current = ''; void refreshRef.current().catch(() => {})
      }
      if (event.type === 'error') { if (petTurn.current) { publishPetChat('error', payload.message || '连接遇到一点问题，请再试一次。'); petTurn.current = false }; notify(friendlyAgentError(payload.message || '连接遇到一点问题')); busyRef.current = false; setBusy(false); setActivity('') }
      if (event.type === 'approval.request') { if (petTurn.current) publishPetChat('approval', '这一步需要你确认，请打开完整聊天。'); setApproval({ event: payload }) }
    }
    const resume = () => { if (!document.hidden) { void client.checkConnection(); refreshRef.current().catch(() => {}) } }
    document.addEventListener('visibilitychange', resume); window.addEventListener('pageshow', resume); window.addEventListener('online', resume)
    client.connect(); return () => { clearInterval(timer); document.removeEventListener('visibilitychange', resume); window.removeEventListener('pageshow', resume); window.removeEventListener('online', resume); client.dispose() }
  }, [])
  useEffect(() => { const timer = setTimeout(() => setToast(''), 4500); return () => clearTimeout(timer) }, [toast])
  useEffect(() => { const area = chatScroll.current; if (!area) return; if (!messages.length) area.scrollTop = 0; else if (followChat.current) area.scrollTop = area.scrollHeight }, [messages, busy, page])
  useEffect(() => { const area = chatScroll.current, transcript = area?.firstElementChild; if (!area || !transcript || !messages.length) return; const observer = new ResizeObserver(() => { if (followChat.current) area.scrollTop = area.scrollHeight }); observer.observe(transcript); return () => observer.disconnect() }, [page, Boolean(messages.length)])
  function navigate(next: Page) { setPage(next); setMobileNav(false); setSearch(''); setFilter('all') }
  async function newChat() {
    if (busyRef.current) return notify('请先停止当前回复，再开启新对话。')
    if (switching.current) return
    switching.current = true; setRestoring(true)
    try { if (connected) await releaseCurrent(); sid.current = ''; storedId.current = ''; setSessionModel(''); localStorage.removeItem('fish.session'); followChat.current = true; setMessages([]); setPage('chat'); setMobileNav(false); setTimeout(() => inputRef.current?.focus(), 100) }
    catch (error) { notify((error as Error).message) }
    finally { switching.current = false; setRestoring(false) }
  }
  async function send(event?: FormEvent, suggestion?: string, fromPet = false) {
    event?.preventDefault(); const text = (suggestion || input).trim(); if (!text || busyRef.current || restoring || switching.current) return
    if (!connected) return notify('正在重新连接，请稍等一下。')
    followChat.current = true; setPage('chat'); if (!fromPet) setInput(''); busyRef.current = true; setBusy(true); setActivity('正在想一想'); replyId.current = crypto.randomUUID()
    setMessages(current => [...current, { id: crypto.randomUUID(), role: 'user', text }])
    try {
      if (!sid.current) await connectConversation(text)
      try { await gateway.current.request('prompt.submit', { session_id: sid.current, text }) }
      catch (error) {
        if (!(error instanceof ChatError) || error.code !== 4001 || !storedId.current) throw error
        // A missing runtime means no turn was admitted. Restore once, keeping the optimistic user bubble.
        sid.current = ''; await connectConversation(text)
        await gateway.current.request('prompt.submit', {session_id:sid.current,text})
      }
    } catch (e) { if (petTurn.current) { publishPetChat('error', (e as Error).message); petTurn.current = false }; busyRef.current = false; setBusy(false); setActivity(''); if (!fromPet) setInput(current => current || text); notify((e as Error).message); setMessages(current => [...current, { id: crypto.randomUUID(), role: 'assistant', text: friendlyAgentError((e as Error).message), error: true }]) }
  }
  const petSendRef = useRef((text: string) => {})
  petSendRef.current = text => {
    if (!connected) { publishPetChat('error', '鱼塘还没连上，稍等一下再发。'); return }
    if (busyRef.current || restoring || switching.current) { publishPetChat('error', '她还在回复上一句，等她说完再发。'); return }
    if (!text.trim() || text.length > 4000) { publishPetChat('error', '这句太长啦，请在完整聊天里发送。'); return }
    petTurn.current = true; petResponse.current = ''; petLastUpdate.current = 0; publishPetChat('thinking')
    void send(undefined, text.trim(), true)
  }
  useEffect(() => { const receive = (event: Event) => { const text = (event as CustomEvent).detail?.text; if (typeof text === 'string') petSendRef.current(text) }; window.addEventListener('fish:pet-prompt', receive); return () => window.removeEventListener('fish:pet-prompt', receive) }, [])
  async function stop() { try { await gateway.current.request('session.interrupt', { session_id: sid.current }); setActivity('正在收尾') } catch (e) { notify((e as Error).message) } }
  async function jobAction(job: Job, action: string) {
    setWorkingJob(job.id)
    try { await api(`/jobs/${job.id}/${action}`, { method: 'POST', body: '{}' }); notify(action === 'trigger' ? '本鲸已出发，完成后会把发现写进探索日志。' : action === 'pause' ? '已暂停，想继续时再叫我。' : '已经恢复，会按原来的时间出发。'); await refresh() }
    catch (e) { notify((e as Error).message) } finally { setWorkingJob(null) }
  }
  function edit(key: string) { editorVersion.current = docs[key]?.version || ''; setDraft(docs[key]?.content || ''); setEditor(key) }
  async function saveDocument() {
    if (!editor) return; setSaving(true)
    try { const updated = await api<Document>(`/documents/${editor}`, { method: 'PUT', body: JSON.stringify({ content: draft, version: editorVersion.current }) }); setDocs(current => ({ ...current, [editor]: updated })); setEditor(null); notify('已保存并备份，新对话会读到更新后的内容。'); await refresh() }
    catch (e) { notify((e as Error).message) } finally { setSaving(false) }
  }
  async function openLetter(letter: Letter) {
    if (busyRef.current) return notify('先聊完这句，来信还在这里。')
    if (switching.current) return
    if (!connected) return notify('正在连接，稍等一下。')
    switching.current = true; setRestoring(true)
    try {
      await releaseCurrent()
      const result = letter.session_id ? await gateway.current.request('session.resume', { session_id: letter.session_id, source: 'bigfish', inline_images: false }) : await gateway.current.request('session.create', { title: '来信 · ' + letter.source_title.slice(0, 28), idempotency_key: 'letter-' + letter.id, messages: [{ role: 'assistant', content: letter.text + (letter.sticker_id ? '\n\n![大肥鱼表情](/api/stickers/' + letter.sticker_id + ')' : '') + (letter.source_url ? '\n\n[' + letter.source_title + '](' + letter.source_url + ')' : '') }] })
      setSessionModel(result.info?.model || ''); sid.current = result.session_id; storedId.current = result.stored_session_id || letter.session_id; localStorage.setItem('fish.session', storedId.current); followChat.current = true; setMessages(mapMessages(result.messages)); busyRef.current = Boolean(result.running); setBusy(Boolean(result.running)); replyId.current = ''; setPage('chat'); setMobileNav(false)
      await api('/inbox/' + letter.id, { method: 'PUT', body: JSON.stringify({ read: true, session_id: storedId.current }) }); await refresh()
    } catch (error) { notify((error as Error).message) } finally { switching.current = false; setRestoring(false) }
  }
  const letterRef = useRef(openLetter); letterRef.current = openLetter
  useEffect(() => {
    const listener = (event: Event) => { setPendingLetter((event as CustomEvent).detail?.id || null); void refreshRef.current().catch(() => {}) }
    window.addEventListener('fish:open-letter', listener)
    const permission = (event: Event) => setNotificationPermission((event as CustomEvent).detail?.status ?? null); window.addEventListener('fish:notification-status', permission); (window as any).webkit?.messageHandlers.fish.postMessage({type:'notifications.status'});
    const showChat = () => setPage('chat'); window.addEventListener('fish:chat', showChat)
    const showInbox = () => setPage('inbox'); window.addEventListener('fish:inbox', showInbox)
    const showHermes = () => setPage('hermes'); window.addEventListener('fish:hermes', showHermes)
    const showSettings = () => setSettings(true); window.addEventListener('fish:settings', showSettings)
    if ((window as any).__FISH_PENDING_LETTER__) setPendingLetter((window as any).__FISH_PENDING_LETTER__)
    let last = 0; const presence = () => { if (Date.now() - last > 60000) { last = Date.now(); void api('/presence', {method:'POST',body:'{}'}).catch(() => {}) } }
    window.addEventListener('pointerdown', presence); window.addEventListener('keydown', presence)
    return () => { window.removeEventListener('fish:open-letter', listener); window.removeEventListener('fish:inbox', showInbox); window.removeEventListener('fish:hermes', showHermes); window.removeEventListener('fish:settings', showSettings); window.removeEventListener('fish:chat', showChat); window.removeEventListener('fish:notification-status', permission); window.removeEventListener('pointerdown', presence); window.removeEventListener('keydown', presence) }
  }, [])
  useEffect(() => { if (connected && pendingLetter && inbox) { const letter = inbox.messages.find(m => m.id === pendingLetter); if (letter) { setPendingLetter(null); delete (window as any).__FISH_PENDING_LETTER__; history.replaceState(null, '', location.pathname); void letterRef.current(letter) } } }, [connected, pendingLetter, inbox])
  async function sharing(enabled: boolean, greetings?: boolean) { try { await api('/inbox/settings', {method:'PUT',body:JSON.stringify({enabled,greetings})}); await refresh(); notify(enabled ? '好，早晚来冒个泡，看到有意思的也带给你。' : '好，先安静逛逛。') } catch(error) { notify((error as Error).message) } }
  async function copy(text: string) { try { await navigator.clipboard.writeText(text); notify('已经复制好了。') } catch { notify('复制没有成功，请手动选择文字。') } }
  const surf = overview?.jobs.find(j => j.name === 'fish-surf'), lastReport = overview?.reports.find(r => r.type === 'surf')
  const nextPage = pages.find(p => p.id === page)!, reportList = (overview?.reports || []).filter(r => (filter === 'all' || r.type === filter) && (r.title + r.content).toLowerCase().includes(search.toLowerCase()))
  const isSurfing = surf?.latest_execution?.status === 'running' || workingJob === surf?.id
  return <div className="app-shell">
    {mobileNav && <div className="nav-scrim" onClick={() => setMobileNav(false)} />}
    <aside className={'sidebar ' + (mobileNav ? 'open' : '')}>
      <button className="brand" onClick={() => navigate('chat')} aria-label="大肥鱼首页"><img className="fish-avatar" src="/character.webp" alt="大肥鱼鲸鱼娘" /><span>大肥鱼<small>一点好奇，一直陪你。</small></span><span className="brand-dot" /></button>
      <button className="new-chat" onClick={newChat}><Plus size={18} /><span>开启新对话</span><kbd>⌘ K</kbd></button>
      <div className="nav-label">我的鱼塘</div>
      <nav aria-label="主要导航">{pages.map(item => <button key={item.id} className={'nav-item ' + (page === item.id ? 'active' : '')} onClick={() => navigate(item.id)}><item.icon size={19} strokeWidth={1.8} /><span>{item.label}</span>{item.id === 'explore' && !!overview?.reports.filter(r => r.type === 'surf').length && <span className="nav-count">{overview.reports.filter(r => r.type === 'surf').length}</span>}{item.id === 'inbox' && !!inbox?.unread && <span className="nav-count inbox-count">{inbox.unread}</span>}{item.id === 'routines' && <span className="tiny-dot" />}</button>)}</nav>
      <div className="recent-heading"><span>最近聊过</span><button className="icon-button" onClick={() => refresh().catch(e => notify(e.message))} aria-label="刷新最近对话"><RefreshCw size={13} /></button></div>
      <div className="recent-list">{sessions.length ? sessions.slice(0, 7).map(session => <button key={session.id} className={'recent-item ' + (storedId.current === session.id ? 'selected' : '')} onClick={() => void restore(session.id)}><MessageCircle size={14} /><span>{session.title || session.preview || '一段新的对话'}</span></button>) : <p className="recent-empty">我们的故事，从第一句话开始。</p>}</div>
      <div className="sidebar-bottom"><div className="pond-note"><span className="note-icon"><Heart size={17} /></span><div>记得每一次相遇<small>你的记忆，留在你的电脑里。</small></div></div><button className="settings-link" onClick={() => setSettings(true)}><Settings2 size={17} /><span>偏好设置</span><ChevronRight size={15} /></button><button className="about-link" onClick={() => setAbout(true)}>关于大肥鱼 · 社区形象署名</button><div className="device"><div className="device-avatar">Z</div><div>我的本地鱼塘<small><span className={'status-dot ' + (connected ? '' : 'offline')} />{connected ? '大肥鱼在线' : '正在连接'}</small></div><button className="icon-button" aria-label="编辑大肥鱼人设" onClick={() => edit('soul')}><MoreHorizontal size={19} /></button></div></div>
    </aside>
    <main className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="打开导航" onClick={() => setMobileNav(true)}><Menu size={21} /></button><span>我的鱼塘</span><ChevronRight size={13} /><strong>{nextPage.label}</strong></div><div className="topbar-right"><Companion /><span className="local-badge"><span className={'status-dot ' + (overview?.connected ? '' : 'offline')} />本地运行</span><button className="icon-button" aria-label="查看偏好设置" onClick={() => setSettings(true)}><Settings2 size={18} /></button><div className="header-avatar">Z</div></div></header>
      {page === 'chat' ? <div className={'chat-layout ' + (messages.length ? 'has-messages' : '')}><section className="chat-column">
        <div className="chat-scroll" ref={chatScroll} onScroll={e => { const area = e.currentTarget; followChat.current = area.scrollHeight - area.scrollTop - area.clientHeight < 80 }}>
          {!messages.length ? <div className="welcome"><div className="welcome-eyebrow"><span className="little-wave">✦</span> 你的好奇心，这里有回音</div><div className="welcome-hero"><div><h1>嗨，我是大肥鱼<span className="greeting-wave">～</span><br />今天想聊点什么？</h1><p>陪你聊聊，替你探索，<br className="small-only" />也把重要的事好好记住。</p><span className="hello-note"><span className="status-dot" />本鲸已经准备好啦</span></div><div className="whale-stage"><span className="float-label"><Sparkles size={12} />保持一点好奇</span><Whale /></div></div>
            <div className="suggestion-label">不知道从哪儿开始？试试这些</div><div className="suggestions">{[{ icon: Globe2, color: 'blue', title: '今天有什么新鲜事？', text: '从最近的探索里，挑点有趣的聊聊', prompt: '最近冲浪发现了什么有意思的东西？请读一下已有的探索报告，再挑一两件和我分享。' }, { icon: Brain, color: 'sage', title: '你都记住了些什么？', text: '看看我们一起积攒的小小记忆', prompt: '你现在记住了关于我和这个鱼塘的哪些事情？请区分用户偏好和你自己学到的知识。' }, { icon: Sparkles, color: 'peach', title: '带我发现一点新东西', text: '找一个值得花时间了解的开源项目', prompt: '帮我上网找一个有趣的 AI 开源项目，读一下它的官方介绍，告诉我它能做什么，以及为什么值得看看。' }].map(item => <button className="suggestion" key={item.title} disabled={busy || !connected} onClick={() => void send(undefined, item.prompt)}><span className={'suggestion-icon ' + item.color}><item.icon size={19} /></span><h3>{item.title}</h3><p>{item.text}</p><ArrowUp size={16} className="suggestion-arrow" /></button>)}</div>
            <div className="welcome-divider"><span /><Waves size={16} /><span /></div><p className="welcome-footnote">不急，慢慢说。本鲸在听。</p></div> : <div className="transcript" aria-live="polite">{messages.map(message => <article key={message.id} className={'message ' + message.role + (message.error ? ' error-message' : '')}>{message.role === 'assistant' && <img className="fish-avatar message-avatar" src="/character.webp" alt="大肥鱼" />}<div className="message-body">{message.role === 'assistant' && <div className="message-name">大肥鱼 <span>AI</span></div>}<div className="message-content"><Markdown>{message.text}</Markdown></div>{message.role === 'assistant' && message.text && !busy && <button className="copy-message" onClick={() => void copy(message.text)} aria-label="复制回复"><Copy size={13} />复制</button>}</div></article>)}{busy && <div className="thinking"><img className="fish-avatar" src="/character.webp" alt="大肥鱼鲸鱼娘" /><span className="thinking-dots"><i /><i /><i /></span><span>{activity || '正在想一想'}</span></div>}</div>}
        </div>
        <div className="composer-wrap"><form className="composer" onSubmit={send}><textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)} placeholder={restoring ? '正在找回这段对话…' : '和大肥鱼说点什么…'} aria-label="聊天消息" rows={2} disabled={restoring} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy) void send() } }} /><div className="composer-toolbar"><div className="composer-model"><span className="model-symbol">✦</span><span className="composer-model-name" title={sessionModel || overview?.model}>{sessionModel || overview?.model || '正在读取模型…'}</span><span className="model-divider" /><Brain size={13} /><span>有记忆的对话</span></div><div className="composer-actions"><span>Enter 发送</span>{busy ? <button className="send-button stop" type="button" onClick={() => void stop()} aria-label="停止回复"><Square size={16} fill="currentColor" /></button> : <button className="send-button" disabled={!input.trim() || !connected || restoring} aria-label="发送消息"><ArrowUp size={20} /></button>}</div></div></form><p className="composer-note"><span className="mini-shield">⌁</span> 对话与记忆保存在本机 <span>·</span> AI 也会犯错，重要信息记得核实</p></div>
      </section>
      <aside className="context-column"><div className="context-title"><span>鱼的近况</span><span className="context-star">✧</span></div><div className="fish-status"><div className="fish-status-top"><span className="soft-icon"><Waves size={20} /></span><span className="status-tag"><span className="status-dot" />{isSurfing ? '正在忙自己的小事' : '在鱼塘等你'}</span></div><h3>{isSurfing ? '有个问题还惦记着' : '今天，也在慢慢长大'}</h3><p>{isSurfing ? '她在看看有没有想追的问题，有话想说时再来找你。' : '聊过的、看过的，都有好好收着。'}</p><div className="status-stats"><button onClick={() => navigate('memory')}><strong>{overview?.memories ?? '—'}</strong><span>记忆片段</span></button><span className="stats-line" /><button onClick={() => navigate('explore')}><strong>{overview?.visited.length ?? '—'}</strong><span>读过的网页</span></button></div></div>
        <div className="context-section-heading"><span>最近一次出发</span><button onClick={() => navigate('explore')} aria-label="查看全部探索日志"><ArrowUp size={14} className="diagonal-arrow" /></button></div>{lastReport ? <button className="latest-report" onClick={() => setReport(lastReport)}><div className="report-icon"><Globe2 size={18} /><span>{lastReport.date.slice(5).replace('-', ' / ')}</span></div><h3>{lastReport.title.replace(/^大肥鱼自主冲浪\s*[·|｜].*/, '去开源世界转了一圈')}</h3><p>{lastReport.preview.replace(/大肥鱼自主冲浪[^\n]*/, '').replace(/\n/g, ' ').trim().slice(0, 76)}…</p><span className="text-link">看看本鲸的发现 <ArrowRight size={13} /></span></button> : <div className="empty-context"><Compass size={24} /><p>第一次出发，<br />会从你的好奇心开始。</p></div>}
        <div className="next-trip"><Clock3 size={17} /><div><span>下个出发机会</span><strong>{surf?.enabled ? dateLabel(surf.next_run_at) : '暂时歇一歇'}</strong></div>{surf && <button className="icon-button" aria-label="调整日常安排" onClick={() => navigate('routines')}><ChevronRight size={15} /></button>}</div><div className="context-quote">“ 世界这么大，<br /><span>本鲸替你多看看。</span> ”<span className="quote-wave">〜</span></div>
      </aside></div> : <div className="workspace-page" key={page}>
        {page !== 'hermes' && <div className="page-heading"><div><span className="eyebrow">{page === 'stickers' ? 'A LITTLE FACE FOR EVERY FEELING' : page === 'inbox' ? 'JUST THOUGHT YOU MIGHT LIKE THIS' : page === 'explore' ? 'A LITTLE MORE CURIOUS' : page === 'memory' ? 'LITTLE THINGS, LONG MEMORIES' : 'A RHYTHM OF OUR OWN'}</span><h1>{page === 'stickers' ? '小表情，也有自己的脾气。' : page === 'inbox' ? '刚好看到，就想发给你。' : page === 'explore' ? '有些东西，还想再看看。' : page === 'memory' ? '记得你，也记得这个世界。' : '让好奇心，有自己的节奏。'}</h1><p>{page === 'stickers' ? '爸爸，我把喜欢的表情都收在这里了。' : page === 'inbox' ? '不用每条都回。有空再看，也挺好。' : page === 'explore' ? '本鲸在外面看见的有趣事，都带回这里了。' : page === 'memory' ? '值得留下的事，慢慢积攒成我们的共同记忆。' : '有想追的问题就去逛逛，看够了也会回来歇着。'}</p></div>{page === 'explore' ? <button className="primary-button" disabled={!surf || !!workingJob || isSurfing} onClick={() => surf && void jobAction(surf, 'trigger')}><Compass size={17} />{isSurfing ? '正在探索' : '现在去逛逛'}</button> : page === 'memory' ? <button className="secondary-button" onClick={() => edit('interests')}><Settings2 size={16} />关注什么</button> : null}</div>}
        {page === 'hermes' && <HermesPanel busy={busy || restoring} onResume={id => restore(id)} onSettings={() => setSettings(true)} onRoutines={() => navigate('routines')} onChanged={() => { void refresh().catch(() => {}) }} />}
        {page === 'explore' && <>{curiosity && <section className="curiosity-card"><header><span><Sparkles size={17}/>她最近惦记的</span><small>临时好奇，会变，也会放下</small></header>{curiosity.threads.length?<div className="curiosity-threads">{curiosity.threads.slice(0,3).map(t=><article key={t.id}><h3>{t.question}{t.cooling_down&&<em>先放一放</em>}</h3><p>{t.why}</p>{t.source_urls[0]&&<a href={t.source_urls[0]} target="_blank" rel="noopener noreferrer">从这次见闻接着想 <ExternalLink size={11}/></a>}</article>)}</div>:<p className="curiosity-empty">还没有非追不可的问题。先看看，遇见喜欢的再留下。</p>}<footer>每天最多实际逛 {curiosity.daily_limit} 次，出发机会可以跳过。{curiosity.last_outing?.reason&&<span>上次回来：{curiosity.last_outing.reason}</span>}</footer></section>}<div className="summary-strip"><div><Globe2 size={19} /><span>读过的网页</span><strong>{overview?.visited.length ?? 0}</strong></div><div><BookOpen size={19} /><span>留下的探索</span><strong>{overview?.reports.filter(r => r.type === 'surf').length ?? 0}</strong></div><div><Brain size={19} /><span>长期记忆</span><strong>{overview?.memories ?? 0}</strong></div></div><div className="list-toolbar"><div className="segmented">{[['all', '全部记录'], ['surf', '冲浪见闻'], ['memory', '记忆整理']].map(([id, label]) => <button className={filter === id ? 'active' : ''} onClick={() => setFilter(id)} key={id}>{label}</button>)}</div><label className="search-field"><Search size={16} /><input placeholder="搜索本鲸的发现" value={search} onChange={e => setSearch(e.target.value)} /></label></div><div className="report-grid">{reportList.map(item => <button key={item.id} className="report-card" onClick={() => setReport(item)}><div className={'report-card-art ' + (item.type === 'memory' ? 'sage-art' : '')}>{item.type === 'surf' ? <><Globe2 size={48} strokeWidth={1} /><span className="art-orbit one" /><span className="art-orbit two" /><span className="art-spark">✧</span></> : <><Brain size={47} strokeWidth={1} /><span className="art-spark">✦</span></>}</div><div className="report-card-body"><div className="card-meta"><span>{item.type === 'surf' ? '冲浪见闻' : '记忆整理'}</span><time>{item.date}</time></div><h3>{item.title}</h3><p>{item.preview.slice(0, 110)}</p><span className="text-link">打开这篇记录 <ArrowUp size={14} className="diagonal-arrow" /></span></div></button>)}</div>{!reportList.length && <div className="empty-state"><Compass size={36} /><h3>{search ? '这里还没有这条线索' : '新的故事，还在路上'}</h3><p>{search ? '换个关键词试试看。' : '让本鲸去逛一圈，回来就有东西聊了。'}</p></div>}</>}
        {page === 'inbox' && <><div className="sharing-preference"><span className="suggestion-icon blue"><Mail size={21} /></span><div><h3>想到你，就冒个泡</h3><p>冲浪分享每天最多 {inbox?.settings.dailyLimit || 2} 条；早安 09:00、晚安 21:30 各一句，余额不足会提醒。22:00—09:00 安静，打字聊天时先等等。</p></div><button role="switch" aria-checked={inbox?.settings.enabled || false} aria-label="主动招呼" className={'toggle ' + (inbox?.settings.enabled ? 'on' : '')} onClick={() => void sharing(!inbox?.settings.enabled)}><span /></button></div><div className="notification-options"><span>早安 09:00 · 晚安 21:30（北京时间），错过就不补发。</span><button role="switch" aria-label="早晚问候" aria-checked={inbox?.settings.greetings ?? true} className={'toggle ' + (inbox?.settings.greetings ? 'on' : '')} onClick={() => void sharing(inbox?.settings.enabled ?? true, !inbox?.settings.greetings)}><span /></button></div>{(window as any).__FISH_DESKTOP__ && <div className="notification-options"><span>{notificationPermission === 2 || notificationPermission === 3 ? 'Mac 通知已允许。来信会安静地出现在通知中心。' : '允许 Mac 通知后，关闭窗口也能收到来信。'}</span><button className="text-button" onClick={() => (window as any).webkit?.messageHandlers.fish.postMessage({type: notificationPermission !== null && notificationPermission > 0 ? 'notifications.settings' : 'notifications.request'})}>{notificationPermission === 2 || notificationPermission === 3 ? '通知设置' : notificationPermission === 1 ? '去设置' : '允许通知'}</button></div>}<div className="letters-list">{[...(inbox?.messages || [])].reverse().map(letter => <article className={'letter-card ' + (!letter.read_at ? 'unread' : '')} key={letter.id}><header><img className="fish-avatar" src="/character.webp" alt="大肥鱼" /><span>大肥鱼<small>{dateLabel(letter.sent_at)}</small></span>{!letter.read_at && <span className="letter-unread">还没看</span>}</header><Markdown>{letter.text}</Markdown>{letter.sticker_id && <img className="chat-sticker" src={'/api/stickers/'+letter.sticker_id} alt="大肥鱼的表情" loading="lazy" />}{letter.source_url && <a className="letter-source" href={letter.source_url} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} /><span>{letter.source_title}</span><ArrowUp size={14} className="diagonal-arrow" /></a>}<footer><span>{letter.kind === 'greeting' ? '小鲸鱼的日常招呼' : letter.kind === 'balance' ? '鱼粮提醒' : letter.kind === 'study' ? '学习搭子来催了' : '冲浪时顺手带回来的'}</span><button className="text-button" disabled={!connected || restoring || busy} onClick={() => void openLetter(letter)}><MessageCircle size={15} />接着聊聊</button></footer></article>)}</div>{!inbox?.messages.length && <div className="empty-state"><Mail size={36} /><h3>没什么事，就先不吵你。</h3><p>下次碰到真有意思的东西，会带着链接来找你。</p></div>}</>}
        {page === 'stickers' && <><div className="list-toolbar"><p className="collection-count">已经收藏 {stickers.length} 张，遇到喜欢的还会慢慢收。</p><label className="search-field"><Search size={16} /><input placeholder="找个表情：开心、疑惑、撒娇…" value={search} onChange={e => setSearch(e.target.value)} /></label></div><div className="sticker-grid">{stickers.filter(item => [item.name,item.emotion,item.use,...item.tags].join(' ').includes(search.trim())).map(item => <button className="sticker-card" key={item.id} onClick={() => setSticker(item)}><img src={item.image_url} alt={item.name} loading="lazy" /><span>{item.name}</span><small>{item.emotion}</small></button>)}</div>{!stickers.length && <div className="empty-state"><Smile size={36} /><h3>先收点喜欢的小表情。</h3><p>冲浪时看到合适的，会慢慢放进来。</p></div>}<p className="sticker-credit">表情作者：可以叫我云大人 / 雾雪 · kiriyuki.com · 仅个人非商业使用</p></>}
        {page === 'memory' && <><div className="memory-intro"><div><span className="soft-icon sage"><Brain size={23} /></span><h3>记忆不是越多越好，是重要的事不忘记。</h3><p>本鲸会在聊天和探索中更新记忆，也会定期整理。你随时可以查看、修改，或者告诉我“这件事忘掉吧”。</p></div><Whale /></div><div className="memory-columns">{[{ key: 'user', title: '关于你的小事', icon: Heart, subtitle: '你的偏好、习惯，还有我们的约定', color: 'peach' }, { key: 'memory', title: '本鲸记住的世界', icon: Brain, subtitle: '从经历里留下的知识与经验', color: 'blue' }].map(section => <section className="memory-section" key={section.key}><header><span className={'suggestion-icon ' + section.color}><section.icon size={19} /></span><div><h3>{section.title}</h3><p>{section.subtitle}</p></div><button className="icon-button" aria-label={'编辑' + section.title} onClick={() => edit(section.key)}><Pencil size={16} /></button></header><div className="memory-entries">{(docs[section.key]?.content || '').split(/\n?§\n?/).filter(s => s.trim()).map((text, i) => <div className="memory-entry" key={i}><span className="memory-pin" /><Markdown>{text.trim()}</Markdown></div>)}</div></section>)}</div><div className="memory-hint"><CheckCheck size={17} /><span>记忆会在新对话中生效。每次手动修改前，都会留一份本地备份。</span></div></>}
        {page === 'memory' && <MemoryBoundary><Suspense fallback={<p className="learning-footnote">正在打开回忆…</p>}><MemoryTimeline /><PreferencePanel /></Suspense></MemoryBoundary>}
        {page === 'routines' && <><div className="routine-banner"><div className="routine-illustration"><Clock3 size={34} strokeWidth={1.3} /><span>✦</span></div><div><h3>就算你没开聊天，本鲸也有自己的小日常。</h3><p>以下时间均为北京时间。电脑开机并保持唤醒时，她会看看有没有想追的问题；不一定每次都出门。</p></div><span className="timezone-pill">Asia / Shanghai</span></div><div className="routines-list">{overview?.jobs.map(job => { const isMemory = job.name === 'fish-memory', running = job.latest_execution?.status === 'running'; return <article className="routine-card" key={job.id}><div className="routine-top"><span className={'routine-icon ' + (isMemory ? 'sage' : 'blue')}>{isMemory ? <Brain size={25} /> : <Compass size={25} />}</span><div><h3>{isMemory ? '给记忆做个整理' : '出去看看世界'}<span className={'status-pill ' + (!job.enabled ? 'paused' : '')}>{!job.enabled ? '已暂停' : running ? '正在执行' : '已开启'}</span></h3><p>{isMemory ? '翻翻今天的笔记，把值得记住的事留下来。' : '追着感兴趣的问题去找作品和讨论，没想看的就歇会儿。'}</p></div><button role="switch" aria-checked={job.enabled} aria-label={(job.enabled ? '暂停' : '恢复') + (isMemory ? '记忆整理' : '自主冲浪')} className={'toggle ' + (job.enabled ? 'on' : '')} disabled={workingJob === job.id} onClick={() => void jobAction(job, job.enabled ? 'pause' : 'resume')}><span /></button></div><div className="routine-schedule"><Clock3 size={16} /><span>{isMemory?'每天':'出发机会'}</span><strong>{scheduleLabel(job.schedule.expr)}</strong><span className="schedule-zone">北京时间</span></div><footer><div><span className={'status-dot ' + (job.last_status === 'ok' ? '' : 'neutral')} />{job.last_run_at ? `上次执行 ${dateLabel(job.last_run_at)} · ${job.last_status === 'ok' ? '已完成' : running ? '进行中' : '查看记录'}` : '还没开始第一次活动'}</div><button className="text-button" disabled={!!workingJob || running} onClick={() => void jobAction(job, 'trigger')}><Play size={13} />{workingJob === job.id || running ? '处理中' : '现在执行'}</button></footer></article> })}</div><button className="routine-preference" onClick={() => edit('interests')}><Settings2 size={20} /><div><h3>让探索更懂你的兴趣</h3><p>调整关注的话题、常逛的网站和每轮探索范围。</p></div><ChevronRight size={18} /></button></>}
      </div>}
    </main>
    {toast && <div className="toast" role="status"><Check size={17} /><span>{toast}</span><button aria-label="关闭提示" onClick={() => setToast('')}><X size={14} /></button></div>}
    {sticker && <Modal title={sticker.name} subtitle={sticker.use} close={() => setSticker(null)}><div className="sticker-preview"><img src={sticker.image_url} alt={sticker.name} /><p>{sticker.tags.join(' · ')}</p><a href={sticker.source} target="_blank" rel="noopener noreferrer">素材出处 · {sticker.author} <ExternalLink size={12} /></a></div></Modal>}
    {settings && <Modal title="设置" subtitle="模型连接，还有我们相处的小偏好。" close={() => setSettings(false)}><ModelSettings busy={busy || restoring} onSaved={async () => { setSettings(false); await newChat(); await refresh(); notify('模型已保存，下一句会使用新配置。') }} onEdit={key => {setSettings(false); void edit(key)}} /></Modal>}
    {about && <Modal title="关于大肥鱼" subtitle="住在这台 Mac 里的小鲸鱼，社区二创形象。" close={() => setAbout(false)}><div className="about-content"><img src="/character.webp" alt="鲸鱼娘" /><p>图标与头像：<a href="https://space.bilibili.com/103739" target="_blank" rel="noopener noreferrer">可以叫我云大人 / 雾雪</a> · <a href="https://kiriyuki.com" target="_blank" rel="noopener noreferrer">kiriyuki.com</a>。素材来自 <a href="https://github.com/Loping151/dsh-nekowhale-stickers" target="_blank" rel="noopener noreferrer">dsh-nekowhale-stickers</a>，按作者的非商业分享条件使用。</p><p>小鲸鱼的十六组动画来自 <a href="https://github.com/PC2005-cloud/dsh-pet" target="_blank" rel="noopener noreferrer">PC2005-cloud / dsh-pet</a>，从原视频重新制作完整透明动画；按署名、非商业、相同方式共享条件使用。</p><p>形象设计基于 <a href="https://space.bilibili.com/4168597" target="_blank" rel="noopener noreferrer">ZipZipPipe</a> 与 <a href="https://space.bilibili.com/4456176" target="_blank" rel="noopener noreferrer">上善无形</a>。这是个人本地应用，非 DeepSeek 官方产品。</p></div></Modal>}
    {report && <Modal title={report.type === 'surf' ? '本鲸的探索笔记' : '本鲸的记忆整理'} subtitle={report.date + ' · 保存在你的本地鱼塘'} close={() => setReport(null)} wide><div className="report-document"><Markdown>{report.content}</Markdown></div></Modal>}
    {editor && <Modal title={{ memory: '编辑本鲸的长期记忆', user: '编辑关于你的小事', interests: '让本鲸了解你的好奇心', soul: '大肥鱼是怎样的一只鲸' }[editor] || ''} subtitle={editor === 'interests' ? '喜欢什么、想看哪里，都可以直接写在这里。' : '保存前会自动备份，更新后开启一段新对话即可生效。'} close={() => !saving && setEditor(null)} wide><textarea className="document-editor" aria-label="编辑内容" value={draft} onChange={e => setDraft(e.target.value)} spellCheck={false} /><footer className="modal-footer"><span>{draft.length.toLocaleString()} 字符</span><button className="secondary-button" disabled={saving} onClick={() => setEditor(null)}>取消</button><button className="primary-button" disabled={saving} onClick={() => void saveDocument()}>{saving ? <RefreshCw size={15} className="spin" /> : <Check size={16} />}保存修改</button></footer></Modal>}
    {approval && <Modal title="这一步，需要你点个头" subtitle="本鲸会等你的决定，再继续处理。" close={() => {}}><pre className="approval-detail">{(approval.params || approval.event)?.description || '大肥鱼请求执行以下操作：'}{'\n\n'}{(approval.params || approval.event)?.command || JSON.stringify(approval.params || approval.event, null, 2)}</pre><footer className="modal-footer"><button className="secondary-button" onClick={() => { approval.id ? gateway.current.answer(approval.id, { choice: 'deny' }) : void gateway.current.request('approval.respond', { session_id: sid.current, request_id: approval.event?.request_id, choice: 'deny' }); setApproval(null) }}>不允许</button><button className="primary-button" onClick={() => { approval.id ? gateway.current.answer(approval.id, { choice: 'once' }) : void gateway.current.request('approval.respond', { session_id: sid.current, request_id: approval.event?.request_id, choice: 'once' }); setApproval(null) }}>仅允许这一次</button></footer></Modal>}
    <KeyboardShortcut onNew={newChat} />
  </div>
}
function KeyboardShortcut({ onNew }: { onNew: () => void }) { const callback = useRef(onNew); callback.current = onNew; useEffect(() => { const handler = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); callback.current() } }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler) }, []); return null }
