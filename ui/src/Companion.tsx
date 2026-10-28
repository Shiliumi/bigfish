import { useEffect, useRef, useState, type FormEvent } from 'react'
import { X, RotateCcw, MessageCircle, ArrowUp } from 'lucide-react'
import { api } from './api'
import type { PetChatStatus } from './petChat'

interface State { animation: string; label: string; state: string; unread: number; balance?: {status:string} }
interface Clip { label: string; duration: number; poster: string; preview: string; mov: string; webm: string; width: number; height: number; fps: number }
interface Manifest { version: number; animations: Record<string, Clip> }
let assets: Promise<Manifest> | undefined
const loadAssets = () => assets ||= fetch('/pet/manifest.json').then(r => { if (!r.ok) throw Error('动画没有载入'); return r.json() })
const nativeBridge = (value: Record<string, string>) => (window as any).webkit?.messageHandlers.fish.postMessage(value)
const actions = [{ id: 'tickle', label: '摸摸头', symbol: '♡' }, { id: 'shy', label: '戳一下', symbol: '✧' }, { id: 'rice', label: '喂口白饭', symbol: '◡' }, { id: 'stretch', label: '伸懒腰', symbol: '↟' }, { id: 'tail', label: '尾巴拍拍', symbol: '〜' }, { id: 'sleep', label: '打个瞌睡', symbol: '☾' }]

export function PetVideo({ animation, replay = 0, manifest }: { animation: string; replay?: number; manifest: Manifest | null }) {
  const video = useRef<HTMLVideoElement>(null)
  const [reduced, setReduced] = useState(matchMedia('(prefers-reduced-motion: reduce)').matches), [failed, setFailed] = useState(false)
  const clip = manifest?.animations[animation] || manifest?.animations.idle
  useEffect(() => { const media = matchMedia('(prefers-reduced-motion: reduce)'); const change = () => setReduced(media.matches); media.addEventListener('change', change); return () => media.removeEventListener('change', change) }, [])
  useEffect(() => { setFailed(false); const element = video.current; const visibility = () => { if (!element) return; if (document.hidden) element.pause(); else void element.play().catch(() => {}) }; document.addEventListener('visibilitychange', visibility); return () => document.removeEventListener('visibilitychange', visibility) }, [animation, replay, reduced])
  if (!clip) return <div className="pet-loading">小鲸鱼正在过来…</div>
  if (reduced || failed) return <img className="pet-movie" src={'/pet/' + clip.poster} alt="大肥鱼" />
  return <video key={animation + replay} ref={video} className="pet-movie" src={'/pet/' + clip.mov} poster={'/pet/' + clip.poster} muted autoPlay loop playsInline preload="auto" onCanPlay={() => { void video.current?.play().catch(() => {}) }} onError={() => setFailed(true)} aria-label={'小鲸鱼 · ' + clip.label} />
}

export function Companion() {
  const [open, setOpen] = useState(false), [manifest, setManifest] = useState<Manifest | null>(null)
  const [state, setState] = useState<State>({ animation: 'idle', label: '在鱼塘待着呢', state: 'idle', unread: 0 })
  const [visible, setVisible] = useState(true), [peeked,setPeeked] = useState(false), [peekEdge,setPeekEdge] = useState('right'), [autoDock,setAutoDock] = useState(true), [size, setSize] = useState('medium'), [action, setAction] = useState(''), [replay, setReplay] = useState(0)
  const [caption, setCaption] = useState(''), [draft, setDraft] = useState(''), [reply, setReply] = useState(''), [chatStatus, setChatStatus] = useState<PetChatStatus | ''>('')
  const lastSent = useRef('')
  const container = useRef<HTMLDivElement>(null), stage = useRef<HTMLButtonElement>(null), actionTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const busy = ['thinking', 'streaming', 'approval'].includes(chatStatus)
  const bridge = (type: string) => nativeBridge({ type })
  function perform(name: string, text = '') {
    clearTimeout(actionTimer.current); setAction(name); setCaption(text); setReplay(value => value + 1)
    actionTimer.current = setTimeout(() => { setAction(''); setCaption('') }, (manifest?.animations[name]?.duration || 10) * 1000)
    nativeBridge({ type: 'pet.action', name })
  }
  useEffect(() => {
    const status = (e: Event) => { const detail = (e as CustomEvent).detail; setVisible(Boolean(detail?.visible)); setPeeked(Boolean(detail?.peeked)); if (['left','right','top','bottom'].includes(detail?.edge)) setPeekEdge(detail.edge); if (typeof detail?.autoDock === 'boolean') setAutoDock(detail.autoDock); if (detail?.size) setSize(detail.size) }
    const chat = (e: Event) => { const data = (e as CustomEvent).detail; setChatStatus(data.status); if (data.status === 'error' && lastSent.current) setDraft(value => value || lastSent.current); if (data.status === 'complete') lastSent.current = ''; if (data.status === 'thinking') { setDraft(''); setReply('') }; if (data.text) setReply(data.text); if (data.status === 'complete') { setAction('happy'); setReplay(v => v + 1); clearTimeout(actionTimer.current); actionTimer.current = setTimeout(() => setAction(''), 10000) } }
    window.addEventListener('fish:pet-status', status); window.addEventListener('fish:pet-chat', chat); bridge('pet.status')
    return () => { window.removeEventListener('fish:pet-status', status); window.removeEventListener('fish:pet-chat', chat); clearTimeout(actionTimer.current) }
  }, [])
  useEffect(() => {
    if (!open) return
    let alive = true
    void loadAssets().then(value => { if (alive) setManifest(value) }).catch(() => { if (alive) setCaption('动画没能载入，刷新后再看看。') })
    const load = () => api<State>('/companion').then(value => { if (alive) setState(value) }).catch(() => { if (alive) setState({ animation: 'idle', state: 'offline', label: '鱼塘暂时离线', unread: 0 }) })
    void load(); const timer = setInterval(() => { if (!document.hidden) void load() }, 3000)
    const dismiss = (e: PointerEvent) => { if (!container.current?.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', dismiss); window.addEventListener('keydown', key)
    return () => { alive = false; clearInterval(timer); document.removeEventListener('pointerdown', dismiss); window.removeEventListener('keydown', key) }
  }, [open])
  useEffect(() => {
    if (!open || action || state.state !== 'idle' || busy) return
    const choices = ['look', 'stretch', 'yawn', 'rice', 'tail']
    const timer = setTimeout(() => perform(choices[Math.floor(Math.random() * choices.length)]), 28000 + Math.random() * 18000)
    return () => clearTimeout(timer)
  }, [open, action, state.state, busy, manifest])
  function send(event: FormEvent) { event.preventDefault(); if (!draft.trim() || busy) return; lastSent.current = draft.trim(); window.dispatchEvent(new CustomEvent('fish:pet-prompt', { detail: { text: draft.trim() } })) }
  const animation = action || (busy ? 'thinking' : state.animation)
  return <div className="companion" ref={container}>
    <button className={'companion-trigger ' + (open ? 'active' : '')} aria-label="小鲸鱼" aria-expanded={open} onClick={() => setOpen(!open)}><img src="/character.webp" alt="" /><span>小鲸鱼</span></button>
    {open && <section className="companion-popover pet-home" aria-label="小鲸鱼的家"><header><div><strong>小鲸鱼</strong><span>戳戳、摸摸，或者聊两句。</span></div><button className="icon-button" aria-label="收起小鲸鱼" onClick={() => setOpen(false)}><X size={17} /></button></header>
      <div className="pet-stage"><span className="pet-ambient a" /><span className="pet-ambient b" /><span className="pet-ground" /><button ref={stage} className="pet-touch" aria-label="摸摸小鲸鱼" onClick={e => { if (peeked) bridge('pet.peek.toggle'); const rect = e.currentTarget.getBoundingClientRect(); const head = !e.clientY || e.clientY - rect.top < rect.height * .5; perform(head ? 'tickle' : 'happy', head ? '嘿嘿，爹。' : '在呢，怎么啦？') }} onPointerMove={e => { const rect = e.currentTarget.getBoundingClientRect(); e.currentTarget.style.setProperty('--pet-lean', ((e.clientX - rect.left) / rect.width - .5) * 2 + 'deg') }} onPointerLeave={e => e.currentTarget.style.setProperty('--pet-lean', '0deg')}>{peeked?<div className="peek-appearance-preview"><img src={'/pet/peek-'+(peekEdge==='left'?'right':peekEdge)+'-v2.png'} style={{transform:peekEdge==='left'?'scaleX(-1)':undefined}} alt="新绘制的探头姿态"/><span>探头中</span></div>:<PetVideo animation={animation} replay={replay} manifest={manifest} />}</button><span className="pet-quality">点她试试</span></div>
      <div className="pet-state"><span className={'status-dot ' + (state.state === 'offline' ? 'offline' : '')} />{caption || (busy ? '正在想怎么回你…' : state.label)}</div>
      <div className="pet-action-grid">{actions.map(item => <button key={item.id} className={action === item.id ? 'selected' : ''} onClick={() => perform(item.id)}><span>{item.symbol}</span>{item.label}</button>)}</div>
      {reply && <div className={'pet-chat-reply ' + (chatStatus === 'error' ? 'error' : '')} role="log" aria-live="polite">{reply.replace(/!\[[^\]]*\]\([^)]*\)/g, '[表情包在完整聊天里]').replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1（$2）')}{chatStatus === 'streaming' && <i className="pet-cursor" />}</div>}
      {busy && !reply && <div className="pet-chat-waiting">她在想怎么说<span>···</span></div>}
      <form className="pet-chat-form" onSubmit={send}><input value={draft} maxLength={4000} onChange={e => setDraft(e.target.value)} placeholder="和她说点什么…" aria-label="小鲸鱼聊天消息" /><button aria-label="发送给小鲸鱼" disabled={!draft.trim() || busy}><ArrowUp size={18} /></button></form>
      <footer className="pet-home-footer">{<><button onClick={() => bridge('pet.quick-chat')}><MessageCircle size={13} />桌面气泡聊</button><div><button onClick={() => bridge('pet.toggle')}>{visible ? '收起桌宠' : '显示桌宠'}</button><button aria-label="恢复小鲸鱼位置" onClick={() => bridge('pet.reset')}><RotateCcw size={13} /></button></div></>}</footer>
      {<div className="pet-dock-options"><button role="switch" aria-checked={autoDock} onClick={() => bridge('pet.dock.toggle')}>靠边自动探头 {autoDock ? '开' : '关'}</button><button onClick={() => bridge('pet.peek.toggle')}>{peeked ? '出来晃晃' : '回边边'}</button><button onClick={() => bridge('pet.greeting.preview')}>预览招呼</button></div>}
      <div className="pet-food"><button onClick={() => { void api('/balance/refresh',{method:'POST',body:'{}'}).then(balance => setState(value => ({...value,balance}))).catch(()=>{}) }}>{state.balance?.status === 'empty' ? '鱼粮见底了' : state.balance?.status === 'low' ? '鱼粮快见底了' : state.balance?.status === 'ready' ? '鱼粮正常' : state.balance?.status === 'unsupported' ? '此服务暂不支持余额查询' : '查一下鱼粮'}</button>{['empty','low'].includes(state.balance?.status || '') && <a href="https://platform.deepseek.com" target="_blank" rel="noopener noreferrer">去补点鱼粮 ↗</a>}</div>
      {<div className="pet-size-options" aria-label="桌宠大小">{[{id:'small',label:'小只'},{id:'medium',label:'正常'},{id:'large',label:'大只'}].map(item=><button key={item.id} aria-pressed={size===item.id} onClick={()=>nativeBridge({type:'pet.size',size:item.id})}>{item.label}</button>)}</div>}
    </section>}
  </div>
}
