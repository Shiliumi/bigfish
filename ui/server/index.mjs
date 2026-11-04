import http from 'node:http';
import { readFile, writeFile, rename, mkdir, readdir, stat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes, createHash } from 'node:crypto';
import { WebSocketServer, WebSocket } from 'ws';
import { createInbox } from './inbox.mjs';
import { attachChatClient, chatActivity } from './chat.mjs';
import { companionState } from './companion.mjs';
import { mediaRange } from './media.mjs';
import { createBalance, balanceNotice } from './balance.mjs';
import { createModelSettings } from './models.mjs';
import { createDesktopAccess, desktopKeyPath } from './desktop-access.mjs';
import { createHermesPanel } from './hermes-panel.mjs';
import { renameStoredChat } from './session-title.mjs';
import { curiositySnapshot } from './curiosity.mjs';
import { createUsage } from './usage.mjs';
import { journal, learningScript } from './journal.mjs';
import {createRoomStore} from './room.mjs';
import {createRoomCapture} from './room-capture.mjs';
import {createRoomContents} from './room-contents.mjs';
import {createRoomLife} from './room-life.mjs';
import {roomIntent} from '../src/room/life-motion.mjs';

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = path.dirname(UI), HOME = path.join(ROOT, '.hermes');
const PORT = Number(process.env.FISH_UI_PORT || 9120), NATIVE = 'http://127.0.0.1:9119';
const SESSION = randomBytes(32).toString('hex');
const desktopAccess = await createDesktopAccess(ROOT,{keyPath:desktopKeyPath()});
const hermesPanel = createHermesPanel(native,{renameChat:async(id,title)=>renameStoredChat(`ws://127.0.0.1:9119/api/ws?token=${encodeURIComponent(await getToken())}`,id,title)});
const usage = createUsage(ROOT,native);
const room = createRoomStore(ROOT);
const roomLife=createRoomLife(ROOT,{room,requirePresence:true,available:async()=>{const c=await companion(),letters=await inbox.snapshot(),hour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',hourCycle:'h23'}).format(new Date())),{quietStart:a,quietEnd:b}=letters.settings;return !['thinking','working','surfing','offline'].includes(c.state)&&(a<b?hour<a||hour>=b:hour>=b&&hour<a)}});
const roomCapture=createRoomCapture(room,{intent:async()=>{const c=await companion(),life=await roomLife.snapshot();return roomIntent(c.state,life.mode||'auto')}});
const roomContents=createRoomContents(ROOT,{readMemories:()=>journal(ROOT,{q:'',scope:'current',limit:3})});
const roomProject=createHash('sha256').update(await realpath(ROOT)).digest('hex');
const documents = { memory: path.join(HOME,'memories/MEMORY.md'), user: path.join(HOME,'memories/USER.md'), interests: path.join(ROOT,'INTERESTS.md'), soul: path.join(HOME,'SOUL.md') };
let nativeToken = '', tokenTime = 0, vite;
const chatTickets = new Map();
let companionCache = null, companionPending;
async function companion() {
  // Shared across app and preview polling, including concurrent requests.
  if (!companionCache || Date.now() - companionCache.time > 15000) {
    companionPending ||= native('/api/cron/jobs?profile=default').then(data => ({ connected: true, jobs: Array.isArray(data) ? data : data.jobs || [] })).catch(() => ({ connected: false, jobs: [] })).then(value => { companionCache = { ...value, time: Date.now() }; companionPending = null; });
    await companionPending;
  }
  const letters = await inbox.snapshot(), curiosity = await curiositySnapshot(ROOT).catch(()=>({last_outing:null}));
  const outingStarted = curiosity.last_outing?.status==='started' && Date.now()-Date.parse(curiosity.last_outing.started_at)<15*60000;
  const notice = letters.can_interrupt?letters.messages.find(m=>letters.alert_ids.includes(m.id)&&!m.pet_notified_at&&!m.notified_at):null;
  return {...companionState({ ...companionCache, activities: chatActivity(), unread: letters.unread, outingStarted }),can_interrupt:letters.can_interrupt,activity_minutes:letters.settings.activityMinutes,alert_ids:letters.alert_ids,notice:notice?{id:notice.id,text:notice.text,kind:notice.kind||'surf',sent_at:notice.sent_at,expires_at:notice.expires_at,source_url:notice.source_url,source_title:notice.source_title}:null,balance:balance.snapshot()};
}
const inbox = createInbox(ROOT,Date.now,{isBusy:()=>chatActivity().length>0});
const models = createModelSettings(ROOT,{native,isBusy:()=>chatActivity().length>0});
const balance = createBalance(ROOT,{connection:()=>models.balanceConnection(),onState:async state=>{const notice=balanceNotice(state,Date.now());if(notice)await inbox.queueLocal(notice);else if(['ready','unsupported'].includes(state.status))await inbox.cancelPending('balance');}});
const balanceTimer=setInterval(()=>balance.refresh().catch(()=>{}),15*60000);balanceTimer.unref();void balance.refresh().catch(()=>{});
const inboxTimer = setInterval(() => {void inbox.tick().catch(() => console.warn('来信检查失败，将在下一轮重试。'));void roomLife.tick().catch(()=>console.warn('小屋生活检查等待下一轮。'));}, 15000);
inboxTimer.unref();
void inbox.tick().catch(() => {});
const json = (res, code, data) => { res.writeHead(code, {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}); res.end(JSON.stringify(data)); };
const digest = text => createHash('sha256').update(text).digest('hex');
const textFile = async file => { try { return await readFile(file,'utf8'); } catch(e) { if(e.code==='ENOENT') return ''; throw e; } };
function fail(message, status=400) { const error=new Error(message); error.status=status; throw error; }
function local(req) { return ['127.0.0.1','localhost'].includes((req.headers.host||'').split(':')[0]); }
function authorize(req, ticketValid=false) {
  if (!local(req)) fail('不支持此访问地址。',403);
  if (!ticketValid && !desktopAccess.allowed(req)) fail('请从 macOS「大肥鱼」应用访问。',401);
  if (!ticketValid && !desktopAccess.header(req) && !(req.headers.cookie||'').split(';').some(c=>c.trim()===`fish_session=${SESSION}`)) fail('请重新连接应用。',401);
  const origin=req.headers.origin;
  if (origin && ![`http://127.0.0.1:${PORT}`,`http://localhost:${PORT}`].includes(origin)) fail('不允许跨站访问。',403);
  if (!['GET','HEAD'].includes(req.method) && req.headers['x-fish-client']!=='studio') fail('请求缺少客户端标识。',403);
}
async function body(req,limit=1024*1024) {
  let data=''; for await(const chunk of req) { data+=chunk; if(Buffer.byteLength(data)>limit) fail('内容过长。',413); }
  try { return JSON.parse(data||'{}'); } catch { fail('请求格式不正确。'); }
}
async function getToken(force=false) {
  if(nativeToken && !force && Date.now()-tokenTime<60000) return nativeToken;
  nativeToken=(await textFile(path.join(ROOT,'.setup/hermes-api.key'))).trim();
  if(!/^[a-f0-9]{64}$/.test(nativeToken)) fail('Hermes 内部接口尚未就绪，请重新打开大肥鱼。',503);
  tokenTime=Date.now(); return nativeToken;
}
async function native(route,method='GET',data, retry=true) {
  const token=await getToken();
  const response=await fetch(NATIVE+route,{method,headers:{'X-Hermes-Session-Token':token,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(20000)});
  if(response.status===401 && retry) { await getToken(true);return native(route,method,data,false); }
  const result=await response.json();
  if(!response.ok) fail(typeof result.detail==='string'?result.detail:'操作暂时没有成功，请重试。',response.status);
  return result;
}
async function reports() {
  const root=path.join(ROOT,'reports'), files=[];
  async function walk(dir) {
    for(const entry of await readdir(dir,{withFileTypes:true}).catch(()=>[])) {
      const full=path.join(dir,entry.name);
      if(entry.isDirectory()) await walk(full);
      else if(entry.isFile() && entry.name.endsWith('.md')) {
        const info=await stat(full);if(info.size>512000) continue;
        const content=await readFile(full,'utf8'), relative=path.relative(root,full);
        const title=content.match(/^#\s+(.+)$/m)?.[1]||entry.name;
        files.push({id:Buffer.from(relative).toString('base64url'),title,type:entry.name.includes('surf')?'surf':'memory',date:relative.split(path.sep)[0],modified:info.mtime.toISOString(),preview:content.replace(/^#+\s*/gm,'').slice(0,240),content});
      }
    }
  }
  await walk(root);return files.sort((a,b)=>b.modified.localeCompare(a.modified));
}
async function overview() {
  const results=await Promise.allSettled([native('/api/status?profile=default'),native('/api/cron/jobs?profile=default'),reports()]);
  const value=(i,fallback)=>results[i].status==='fulfilled'?results[i].value:fallback;
  const status=value(0,{}), jobs=value(1,[]), records=value(2,[]);
  const {model}=await models.snapshot();
  return {connected:results[0].status==='fulfilled' && Boolean(status.gateway_running),model,jobs:Array.isArray(jobs)?jobs:jobs.jobs||[],reports:records,service:status.gateway_state||null};
}
async function handleAPI(req,res,url) {
  authorize(req);const name=url.pathname;
  if(name.startsWith('/api/room')&&req.headers['x-fish-room-project']&&req.headers['x-fish-room-project']!==roomProject)fail('小屋不属于当前项目。',403);
  if(name==='/api/room'&&req.method==='GET')return json(res,200,await room.snapshot());
  if(name==='/api/room/life'&&req.method==='GET')return json(res,200,await roomLife.snapshot());
  if(name==='/api/room/life'&&req.method==='PUT')return json(res,200,await roomLife.update(await body(req)));
  if(name==='/api/room/life/presence'&&req.method==='POST')return json(res,200,await roomLife.presence(await body(req)));
  if(name==='/api/room/life/briefing'&&req.method==='GET'){const state=await room.snapshot(),life=await roomLife.snapshot();return json(res,200,{available:true,enabled:life.enabled,revision:state.revision,pause_reason:life.pause_reason,locks:state.locks,movable_items:(await room.context()).movable_items,wishes:life.wishes.filter(w=>['open','accepted'].includes(w.status)).map(w=>({item:w.item,text:w.text}))});}
  if(name==='/api/room/context'&&req.method==='GET'){const context=await room.context();try{const life=await roomLife.snapshot();context.representation='大肥鱼住在自己的小屋里，会沿房间路线走动、坐在电脑前、到床上侧卧休息。'+(life.character?'当前宿主姿态：'+({walk:'正在走动',sit:'坐在电脑前',sleep:'在床上休息',idle:'在小屋里待着'}[life.character.pose])+'。':'当前人物位置暂未由画面报告，不猜测正在浏览或睡觉。')+' 最近的小打算：'+JSON.stringify(life.wishes.filter(w=>['open','accepted'].includes(w.status)).slice(0,2).map(w=>({item:w.item,text:w.text})));context.life=life;}catch{}return json(res,200,context);}
  if(name==='/api/room/contents'&&req.method==='GET')return json(res,200,await roomContents.snapshot());
  if(name==='/api/room/collection'&&req.method==='PUT')return json(res,200,await roomContents.collect(await body(req)));
  if(name==='/api/room/library'&&req.method==='GET')return json(res,200,await room.library(url.searchParams.get('scope')||'active',Number(url.searchParams.get('offset')||0)));
  if(name==='/api/room/library'&&req.method==='PUT')return json(res,200,await room.managePhoto(await body(req)));
  if(name==='/api/room/environment'&&req.method==='GET')return json(res,200,await room.atmosphere());
  if(name==='/api/room/environment'&&req.method==='PUT')return json(res,200,await room.setAtmosphere(await body(req)));
  if(name==='/api/room/capture'&&req.method==='POST'){if(req.headers['x-fish-room-project']!==roomProject)fail('房间拍照需要当前项目标识。',403);return json(res,200,await roomCapture.request(await body(req)));}
  if(name==='/api/room/render/claim'&&req.method==='POST'){const data=await body(req),abort=new AbortController(),cancel=()=>abort.abort();res.on('close',cancel);try{return json(res,200,{job:await roomCapture.claim(data.worker,abort.signal)});}finally{res.off('close',cancel);}}
  if(name==='/api/room/render/complete'&&req.method==='POST')return json(res,200,await roomCapture.complete(await body(req,3*1024*1024)));
  if(name==='/api/room'&&req.method==='PUT')return json(res,200,await room.update(await body(req)));
  if(name==='/api/room/actions'&&req.method==='POST'){if(req.headers['x-fish-room-project']!==roomProject)fail('房间动作需要当前项目标识。',403);return json(res,200,await room.move(await body(req)));}
  if(name==='/api/room/photos'&&req.method==='POST')return json(res,201,await room.photo(await body(req,3*1024*1024)));
  const roomPhoto=name.match(/^\/api\/room\/photos\/(ph-[a-f0-9]{24})(\/image|\/download)?$/);
  if(roomPhoto&&req.method==='GET'){
    if(!roomPhoto[2])return json(res,200,await room.detail(roomPhoto[1]));
    const bytes=await room.image(roomPhoto[1]);res.writeHead(200,{'Content-Type':'image/png','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',...(roomPhoto[2]==='/download'?{'Content-Disposition':'attachment; filename="bigfish-'+roomPhoto[1]+'.png"'}:{})});return res.end(bytes);
  }
  if(name==='/api/usage' && req.method==='GET') return json(res,200,await usage.snapshot(url.searchParams.get('days')));
  if(name==='/api/budget' && req.method==='GET') return json(res,200,await learningScript(ROOT,'fish_budget.py',{action:'snapshot'}));
  if(name==='/api/budget' && req.method==='PUT') {const data=await body(req);return json(res,200,await learningScript(ROOT,'fish_budget.py',{action:'settings',enabled:data.enabled,daily_tokens:data.daily_tokens,revision:data.revision}));}
  if(name==='/api/automation/settings' && req.method==='PUT') return json(res,200,await usage.saveSettings(await body(req)));
  if(name==='/api/memory-graph' && req.method==='GET') {
    const p=url.searchParams;
    if(p.has('pinned')&&!['true','false'].includes(p.get('pinned')))fail('固定筛选无效。');
    return json(res,200,await journal(ROOT,{action:'graph',q:p.get('q')||'',scope:p.get('scope')||'current',kind:p.get('kind')||'all',pinned:p.get('pinned')==='true',from:p.get('from')||'',to:p.get('to')||''}));
  }
  if(name==='/api/episodes' && req.method==='GET') return json(res,200,await journal(ROOT,{q:(url.searchParams.get('q')||'').slice(0,200),scope:url.searchParams.get('scope')||'current',limit:30}));
  if(name==='/api/matters' && req.method==='GET') return json(res,200,await learningScript(ROOT,'fish_matters.py',{action:'list',query:(url.searchParams.get('q')||'').slice(0,200)}));
  if(name==='/api/matters' && req.method==='POST') {const data=await body(req);return json(res,200,await learningScript(ROOT,'fish_matters.py',{action:'remember',title:data.title,kind:data.kind}));}
  const matter=name.match(/^\/api\/matters\/(mt-[a-f0-9]{24})$/);
  if(matter && req.method==='GET') {const value=await learningScript(ROOT,'fish_matters.py',{action:'detail',id:matter[1]});if(!value)fail('事项不存在或已遗忘。',404);return json(res,200,value);}
  if(matter && req.method==='PATCH') {const data=await body(req);return json(res,200,await learningScript(ROOT,'fish_matters.py',{action:'update',id:matter[1],revision:data.revision,status:data.status,quote:data.quote,renew:data.renew??false,forget:data.forget??false}));}
  if(name==='/api/personality' && req.method==='GET') return json(res,200,await learningScript(ROOT,'personality.py',{action:'snapshot'}));
  const preference=name.match(/^\/api\/personality\/([a-z][a-z0-9-]{1,39})$/);
  if(preference && req.method==='PATCH') {const data=await body(req);return json(res,200,await learningScript(ROOT,'personality.py',{action:'retire',id:preference[1],revision:data.revision}));}
  const episode=name.match(/^\/api\/episodes\/(ep-[a-f0-9]{24})$/);
  if(episode && req.method==='GET') {const value=await journal(ROOT,{action:'detail',id:episode[1]});if(!value)fail('这段回忆不存在或已遗忘。',404);return json(res,200,value);}
  if(episode && req.method==='PATCH') {const data=await body(req);return json(res,200,await journal(ROOT,{action:'update',id:episode[1],revision:data.revision,summary:data.summary,pinned:data.pinned,forget:data.forget??false,kind:data.kind,invalidate:data.invalidate??false,...(Object.hasOwn(data,'valid_until')?{valid_until:data.valid_until}:{}),...(Object.hasOwn(data,'aliases')?{aliases:data.aliases}:{})}));}
  if(name==='/api/curiosity' && req.method==='GET') return json(res,200,await curiositySnapshot(ROOT));
  const interest=name.match(/^\/api\/curiosity\/(cur-[a-f0-9]{12})$/);
  if(interest && req.method==='PATCH') {const data=await body(req);return json(res,200,await inbox.updateInterest(()=>learningScript(ROOT,'fish_interest.py',{id:interest[1],choice:data.choice,revision:data.revision})));}
  if(name==='/api/hermes/summary' && req.method==='GET') return json(res,200,await hermesPanel.summary());
  if(name==='/api/hermes/tools' && req.method==='GET') return json(res,200,await hermesPanel.tools());
  if(name==='/api/hermes/skills' && req.method==='GET') return json(res,200,await hermesPanel.skills());
  if(name==='/api/hermes/skill' && req.method==='GET') return json(res,200,await hermesPanel.skill(url.searchParams.get('name')));
  if(['/api/hermes/tools','/api/hermes/skills'].includes(name) && req.method==='PUT') return json(res,200,await hermesPanel.toggle(name.endsWith('tools')?'tools':'skills',await body(req)));
  if(name==='/api/hermes/sessions' && req.method==='GET') return json(res,200,await hermesPanel.sessions(url.searchParams));
  const panelSession=name.match(/^\/api\/hermes\/sessions\/([A-Za-z0-9_-]+)$/);
  if(panelSession && req.method==='GET') return json(res,200,await hermesPanel.detail(panelSession[1],url.searchParams.get('offset')));
  if(panelSession && req.method==='PATCH') return json(res,200,await hermesPanel.rename(panelSession[1],await body(req)));
  const panelRuns=name.match(/^\/api\/hermes\/jobs\/([a-f0-9]+)\/runs$/);
  if(panelRuns && req.method==='GET') return json(res,200,await hermesPanel.runs(panelRuns[1]));
  if(name==='/api/model-settings' && req.method==='GET') return json(res,200,await models.snapshot());
  if(name==='/api/model-settings' && req.method==='PUT') {const result=await models.save(await body(req));void balance.refresh(true).catch(()=>{});return json(res,200,result);}
  if(name==='/api/model-settings/models' && req.method==='POST') return json(res,200,await models.list(await body(req)));
  if(name==='/api/model-settings/test' && req.method==='POST') return json(res,200,await models.test(await body(req)));
  if(name==='/api/companion' && req.method==='GET') return json(res,200,await companion());
  if(name==='/api/balance' && req.method==='GET') return json(res,200,balance.snapshot());
  if(name==='/api/balance/refresh' && req.method==='POST') return json(res,200,await balance.refresh(true));
  if(name==='/api/stickers' && req.method==='GET') {
    const library=JSON.parse(await textFile(path.join(ROOT,'data/stickers/library.json'))||'{"items":[]}');
    const catalog=JSON.parse(await textFile(path.join(ROOT,'data/stickers/catalog.json'))||'{"items":[]}');
    return json(res,200,{total:catalog.items.length,items:library.items.map(({id,name,emotion,tags,use,source,author,collected_at})=>({id,name,emotion,tags,use,source,author,collected_at,image_url:'/api/stickers/'+id}))});
  }
  const sticker=name.match(/^\/api\/stickers\/([a-f0-9]{16})$/);
  if(sticker && req.method==='GET') {
    const assets=path.join(ROOT,'data/stickers/assets'), file=path.join(assets,sticker[1]+'.gif');
    const actual=await realpath(file).catch(()=>null);if(!actual||!actual.startsWith(assets+path.sep)) fail('这张表情还没收藏。',404);
    res.writeHead(200,{'Content-Type':'image/gif','Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'});return res.end(await readFile(actual));
  }
  if(name==='/api/inbox' && req.method==='GET') return json(res,200,await inbox.snapshot());
  if(name==='/api/presence' && req.method==='POST') {inbox.activity();return json(res,200,{ok:true});}
  if(name==='/api/inbox/settings' && req.method==='PUT') { const data=await body(req); if(typeof data.enabled!=='boolean'||(data.greetings!==undefined&&typeof data.greetings!=='boolean')) fail('设置格式不正确。');return json(res,200,await inbox.settings(data.enabled,data.greetings)); }
  const letter=name.match(/^\/api\/inbox\/([a-f0-9-]{36})$/);
  if(letter && req.method==='PUT') {const data=await body(req); const updated=await inbox.update(letter[1],data);if(!updated) fail('这封来信不存在。',404);return json(res,200,updated);}
  if(name==='/api/chat-ticket' && req.method==='GET') {
    for(const [key, expires] of chatTickets) if(expires<Date.now()) chatTickets.delete(key);
    if(chatTickets.size>500) fail('连接请求过多，请稍后再试。',429);
    const ticket=randomBytes(24).toString('hex');chatTickets.set(ticket,Date.now()+30000);return json(res,200,{ticket});
  }
  if(name==='/api/overview' && req.method==='GET') return json(res,200,await overview());
  if(name==='/api/sessions' && req.method==='GET') return json(res,200,await native('/api/sessions?profile=default&limit=50&min_messages=1&order=recent&exclude_sources=cron'));
  if(name==='/api/documents' && req.method==='GET') {
    const entries=await Promise.all(Object.entries(documents).map(async([key,file])=>{const content=await textFile(file);return [key,{content,version:digest(content)}];}));
    return json(res,200,Object.fromEntries(entries));
  }
  const doc=name.match(/^\/api\/documents\/(memory|user|interests|soul)$/);
  if(doc && req.method==='PUT') {
    const data=await body(req), file=documents[doc[1]], previous=await textFile(file);
    if(typeof data.content!=='string'||data.content.length>50000) fail('内容格式不正确或超过 50,000 字符。');
    if(doc[1]==='memory' && data.content.length>6000) fail('核心记忆最多 6,000 字符，请精简后保存。');
    if(doc[1]==='user' && data.content.length>3000) fail('用户画像最多 3,000 字符，请精简后保存。');
    if(data.version!==digest(previous)) fail('内容刚刚被更新了，请刷新后再编辑。',409);
    const backup=path.join(ROOT,'backups','ui-'+new Date().toISOString().replace(/[:.]/g,'-'));
    await mkdir(backup,{recursive:true});await writeFile(path.join(backup,path.basename(file)),previous,{mode:0o600});
    const tmp=file+'.studio-'+randomBytes(6).toString('hex');await writeFile(tmp,data.content,{mode:0o600});await rename(tmp,file);
    return json(res,200,{content:data.content,version:digest(data.content)});
  }
  const job=name.match(/^\/api\/jobs\/([a-f0-9]+)\/(pause|resume|trigger)$/);
  if(job && req.method==='POST') {
    return json(res,200,await native(`/api/cron/jobs/${job[1]}/${job[2]}?profile=default`,'POST',{}));
  }
  fail('没有找到这个接口。',404);
}
const server=http.createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,`http://127.0.0.1:${PORT}`);
    res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');
    if(url.pathname==='/health' && req.method==='GET' && local(req)) return json(res,200,{app:'bigfish-desktop',ok:true});
    if(url.pathname.startsWith('/api/')) return await handleAPI(req,res,url);
    if(!local(req)) fail('不支持此访问地址。',403);
    if(!desktopAccess.allowed(req)) {res.writeHead(410,{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'});return res.end('大肥鱼已改为 macOS 应用。请从「应用程序」或启动台打开大肥鱼。');}
    res.setHeader('Set-Cookie',[`fish_session=${SESSION}; HttpOnly; SameSite=Strict; Path=/`,desktopAccess.cookie]);
    if(vite) return vite.middlewares(req,res,()=>{res.statusCode=404;res.end();});
    const target=path.resolve(UI,'dist','.'+decodeURIComponent(url.pathname));
    const dist=path.join(UI,'dist');
    if(!target.startsWith(dist+path.sep) && target!==dist) fail('无效路径。',403);
    const ext=path.extname(target), file=ext?target:path.join(dist,'index.html');
    const resolved=await realpath(file).catch(()=>null);
    if(!resolved||!resolved.startsWith(dist+path.sep)) fail('页面不存在，请先构建界面。',404);
    const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2','.png':'image/png','.json':'application/json','.webp':'image/webp','.mov':'video/quicktime','.webm':'video/webm'};
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.setHeader('Cache-Control',ext==='.html'||!ext?'no-cache':'public, max-age=3600');
    const bytes = await readFile(file);
    if (['.mov','.webm'].includes(path.extname(file))) {
      res.setHeader('Accept-Ranges','bytes');
      const range = mediaRange(req.headers.range, bytes.length);
      if (range?.invalid) { res.writeHead(416, {'Content-Range':`bytes */${bytes.length}`}); return res.end(); }
      if (range) { res.writeHead(206, {'Content-Range':`bytes ${range.start}-${range.end}/${bytes.length}`, 'Content-Length':range.end-range.start+1}); return res.end(req.method==='HEAD'?undefined:bytes.subarray(range.start,range.end+1)); }
    }
    res.setHeader('Content-Length',bytes.length);res.end(req.method==='HEAD'?undefined:bytes);
  } catch(error) { if(!res.headersSent) json(res,error.status||503,{error:error.status?error.message:'连接暂时不可用，请确认 Hermes 控制台已启动。'});else res.end(); }
});
const wss=new WebSocketServer({noServer:true,maxPayload:1024*1024});
server.on('upgrade',async(req,socket,head)=>{
  const url=new URL(req.url,`http://127.0.0.1:${PORT}`);
  if(url.pathname!=='/api/chat') {socket.destroy();return;}
  const ticket=url.searchParams.get('ticket'), valid=Boolean(ticket && chatTickets.get(ticket)>Date.now());
  if(ticket) chatTickets.delete(ticket);
  try{authorize(req,valid);await getToken();}catch(error){console.warn('Chat connection refused:',error.status||503);socket.destroy();return;}
  wss.handleUpgrade(req,socket,head,client=>{
    attachChatClient(client,{nativeUrl:`ws://127.0.0.1:9119/api/ws?token=${encodeURIComponent(nativeToken)}`,root:ROOT,onPrompt:()=>inbox.activity(),onIdle:()=>inbox.activity(),onBalanceFailure:()=>models.balanceConnection().then(c=>c&&balance.noteFailure()).catch(()=>{})});
  });
});
if(process.argv.includes('--dev')) {
  const {createServer}=await import('vite');vite=await createServer({root:UI,server:{middlewareMode:true,hmr:{server}},appType:'spa'});
}
server.listen(PORT,'127.0.0.1',()=>console.log('大肥鱼应用内部服务已就绪。'));
async function shutdown() {
  roomCapture.close();
  clearInterval(inboxTimer);
  clearInterval(balanceTimer);
  for(const client of wss.clients) client.terminate();
  if(vite) await vite.close();
  server.close(()=>process.exit(0));
  setTimeout(()=>process.exit(0),2000).unref();
}
process.on('SIGTERM',shutdown);process.on('SIGINT',shutdown);
