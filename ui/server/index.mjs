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

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = path.dirname(UI), HOME = path.join(ROOT, '.hermes');
const PORT = Number(process.env.FISH_UI_PORT || 9120), NATIVE = 'http://127.0.0.1:9119';
const SESSION = randomBytes(32).toString('hex');
const desktopAccess = await createDesktopAccess(ROOT,{keyPath:desktopKeyPath()});
const hermesPanel = createHermesPanel(native,{renameChat:async(id,title)=>renameStoredChat(`ws://127.0.0.1:9119/api/ws?token=${encodeURIComponent(await getToken())}`,id,title)});
const usage = createUsage(ROOT,native);
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
  const letters = await inbox.snapshot(), curiosity = await curiositySnapshot(ROOT);
  const outingStarted = curiosity.last_outing?.status==='started' && Date.now()-Date.parse(curiosity.last_outing.started_at)<15*60000;
  const notice = letters.messages.find(m=>!m.read_at&&!m.pet_notified_at&&Date.now()-Date.parse(m.sent_at)<15*60000);
  return {...companionState({ ...companionCache, activities: chatActivity(), unread: letters.unread, outingStarted }),notice:notice?{id:notice.id,text:notice.text,kind:notice.kind||'surf',sent_at:notice.sent_at,source_url:notice.source_url,source_title:notice.source_title}:null,balance:balance.snapshot()};
}
const inbox = createInbox(ROOT);
const models = createModelSettings(ROOT,{native,isBusy:()=>chatActivity().length>0});
const balance = createBalance(ROOT,{connection:()=>models.balanceConnection(),onState:async state=>{const notice=balanceNotice(state,Date.now());if(notice)await inbox.queueLocal(notice);else if(['ready','unsupported'].includes(state.status))await inbox.cancelPending('balance');}});
const balanceTimer=setInterval(()=>balance.refresh().catch(()=>{}),15*60000);balanceTimer.unref();void balance.refresh().catch(()=>{});
const inboxTimer = setInterval(() => inbox.tick().catch(() => console.warn('来信检查失败，将在下一轮重试。')), 15000);
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
async function body(req) {
  let data=''; for await(const chunk of req) { data+=chunk; if(Buffer.byteLength(data)>1024*1024) fail('内容过长。',413); }
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
  const results=await Promise.allSettled([native('/api/status?profile=default'),native('/api/cron/jobs?profile=default'),reports(),textFile(path.join(ROOT,'data/surf-state.json')),textFile(documents.memory)]);
  const value=(i,fallback)=>results[i].status==='fulfilled'?results[i].value:fallback;
  const status=value(0,{}), jobs=value(1,[]), records=value(2,[]);
  let visited=[];try{visited=JSON.parse(value(3,'{}')).visited||[];}catch{}
  const {model}=await models.snapshot();
  return {connected:results[0].status==='fulfilled' && Boolean(status.gateway_running),model,jobs:Array.isArray(jobs)?jobs:jobs.jobs||[],reports:records,visited,memories:value(4,'').split(/\n?§\n?/).filter(s=>s.trim()).length,service:status.gateway_state||null};
}
async function handleAPI(req,res,url) {
  authorize(req);const name=url.pathname;
  if(name==='/api/usage' && req.method==='GET') return json(res,200,await usage.snapshot(url.searchParams.get('days')));
  if(name==='/api/automation/settings' && req.method==='PUT') return json(res,200,await usage.saveSettings(await body(req)));
  if(name==='/api/episodes' && req.method==='GET') return json(res,200,await journal(ROOT,{q:(url.searchParams.get('q')||'').slice(0,200),scope:url.searchParams.get('scope')||'current',limit:30}));
  if(name==='/api/personality' && req.method==='GET') return json(res,200,await learningScript(ROOT,'personality.py',{action:'snapshot'}));
  const preference=name.match(/^\/api\/personality\/([a-z][a-z0-9-]{1,39})$/);
  if(preference && req.method==='PATCH') {const data=await body(req);return json(res,200,await learningScript(ROOT,'personality.py',{action:'retire',id:preference[1],revision:data.revision}));}
  const episode=name.match(/^\/api\/episodes\/(ep-[a-f0-9]{24})$/);
  if(episode && req.method==='GET') {const value=await journal(ROOT,{action:'detail',id:episode[1]});if(!value)fail('这段回忆不存在或已遗忘。',404);return json(res,200,value);}
  if(episode && req.method==='PATCH') {const data=await body(req);return json(res,200,await journal(ROOT,{action:'update',id:episode[1],revision:data.revision,summary:data.summary,pinned:data.pinned,forget:data.forget??false,kind:data.kind,invalidate:data.invalidate??false,...(Object.hasOwn(data,'valid_until')?{valid_until:data.valid_until}:{})}));}
  if(name==='/api/curiosity' && req.method==='GET') return json(res,200,await curiositySnapshot(ROOT));
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
    attachChatClient(client,{nativeUrl:`ws://127.0.0.1:9119/api/ws?token=${encodeURIComponent(nativeToken)}`,root:ROOT,onPrompt:()=>inbox.activity(),onBalanceFailure:()=>models.balanceConnection().then(c=>c&&balance.noteFailure()).catch(()=>{})});
  });
});
if(process.argv.includes('--dev')) {
  const {createServer}=await import('vite');vite=await createServer({root:UI,server:{middlewareMode:true,hmr:{server}},appType:'spa'});
}
server.listen(PORT,'127.0.0.1',()=>console.log('大肥鱼应用内部服务已就绪。'));
async function shutdown() {
  clearInterval(inboxTimer);
  clearInterval(balanceTimer);
  for(const client of wss.clients) client.terminate();
  if(vite) await vite.close();
  server.close(()=>process.exit(0));
  setTimeout(()=>process.exit(0),2000).unref();
}
process.on('SIGTERM',shutdown);process.on('SIGINT',shutdown);
