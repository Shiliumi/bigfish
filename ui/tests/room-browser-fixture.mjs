// Run manually: node ui/tests/room-browser-fixture.mjs. All writes stay in an owned temp profile.
import {createServer} from 'vite';import {fileURLToPath} from 'node:url';import {mkdtemp,rm,mkdir,writeFile} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
import {createRoomStore} from '../server/room.mjs';
import {createRoomCapture} from '../server/room-capture.mjs';
import {createRoomContents} from '../server/room-contents.mjs';
const ui=fileURLToPath(new URL('..',import.meta.url)),root=await mkdtemp(path.join(os.tmpdir(),'fish-room-browser-')),room=createRoomStore(root);
const capture=createRoomCapture(room);
const memory={id:'ep-'+'1'.repeat(24),summary:'虚构验收：一起看过纸机关，想试试让它自己弹开。',recorded_at:'2026-11-03T01:00:00Z',revision:1,effective_status:'active',kind:'event',source_ref:'fixture:fiction',excerpt:'虚构验收原话：这个纸机关怎样弹开？'};
for(const folder of ['reports/2026-11-03','data/personality'])await mkdir(path.join(root,folder),{recursive:true});
await writeFile(path.join(root,'reports/2026-11-03/0900-surf.md'),'# 虚构阅读验收\nhttps://example.org/fiction-paper');
await writeFile(path.join(root,'data/surf-state.json'),JSON.stringify({visited:[{url:'https://example.org/fiction-paper',title:'虚构验收：会弹开的纸机关',report:'reports/2026-11-03/0900-surf.md'}]}));
await writeFile(path.join(root,'data/personality/observations.jsonl'),JSON.stringify({id:'fixture-observation',url:'https://example.org/fiction-paper',report_path:'reports/2026-11-03/0900-surf.md',seen_at:'2026-11-03T01:00:00Z',read_depth:'body',observation:'虚构验收摘要：纸片的折痕储存了弹开的力。'}));
const contents=createRoomContents(root,{readMemories:async()=>({items:[memory]})});
const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小屋交互回归 · 虚构状态</title><div id="root"></div><script type="module" src="/tests/room-fixture.tsx"></script></html>';
const server=await createServer({configFile:false,root:ui,esbuild:{jsx:'automatic'},plugins:[{name:'room-fixture',configureServer(server){server.middlewares.use(async(req,res,next)=>{try{
  if(req.url?.startsWith('/api/')){
    const json=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
    let body='';if(['PUT','POST'].includes(req.method)){for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>3*1024*1024)throw Error('夹具请求过大');}}
    if(req.url==='/api/companion')return json(200,{state:'idle',label:'在小屋里待着呢'});
    if(req.url==='/api/room')return json(200,req.method==='PUT'?await room.update(JSON.parse(body)):await room.snapshot());
    if(req.url==='/api/room/context')return json(200,await room.context());
    if(req.url==='/api/room/contents')return json(200,await contents.snapshot());
    if(req.url==='/api/room/collection'&&req.method==='PUT')return json(200,await contents.collect(JSON.parse(body)));
    if(req.url?.startsWith('/api/room/library')){const params=new URL(req.url,'http://127.0.0.1').searchParams;return json(200,req.method==='PUT'?await room.managePhoto(JSON.parse(body)):await room.library(params.get('scope')||'active',Number(params.get('offset')||0)));}
    if(req.url==='/api/episodes/'+memory.id)return json(200,memory);
    if(req.url==='/api/room/environment')return json(200,req.method==='PUT'?await room.setAtmosphere(JSON.parse(body)):await room.atmosphere());
    if(req.url==='/api/room/capture'&&req.method==='POST')return json(200,await capture.request(JSON.parse(body)));
    if(req.url==='/api/room/render/claim'&&req.method==='POST'){const abort=new AbortController();res.on('close',()=>abort.abort());return json(200,{job:await capture.claim(JSON.parse(body).worker,abort.signal)});}
    if(req.url==='/api/room/render/complete'&&req.method==='POST')return json(200,await capture.complete(JSON.parse(body)));
    if(req.url==='/api/room/actions'&&req.method==='POST')return json(200,await room.move(JSON.parse(body)));
    if(req.url==='/api/room/photos'&&req.method==='POST')return json(201,await room.photo(JSON.parse(body)));
    const photo=req.url.match(/^\/api\/room\/photos\/(ph-[a-f0-9]{24})(\/image|\/download)?$/);if(photo){if(photo[2]){res.setHeader('Content-Type','image/png');if(photo[2]==='/download')res.setHeader('Content-Disposition','attachment; filename="fixture-room.png"');return res.end(await room.image(photo[1]));}return json(200,await room.detail(photo[1]));}
    return json(404,{error:'此接口没有隔离夹具'});
  }
  if(req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}next();
}catch(error){res.writeHead(error.status||400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.message}));}});}}],server:{host:'127.0.0.1',port:9131,strictPort:true,fs:{allow:[ui]}}});
async function close(){capture.close();await server.close();await rm(root,{recursive:true,force:true});process.exit();}process.on('SIGINT',close);process.on('SIGTERM',close);
await server.listen();console.log('小屋隔离测试：http://127.0.0.1:9131（虚构档案，布置和照片仅存于临时目录）');
