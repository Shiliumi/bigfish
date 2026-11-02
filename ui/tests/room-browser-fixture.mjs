// Run manually: node ui/tests/room-browser-fixture.mjs. All writes stay in an owned temp profile.
import {createServer} from 'vite';import {fileURLToPath} from 'node:url';import {mkdtemp,rm} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
import {createRoomStore} from '../server/room.mjs';
import {createRoomCapture} from '../server/room-capture.mjs';
const ui=fileURLToPath(new URL('..',import.meta.url)),root=await mkdtemp(path.join(os.tmpdir(),'fish-room-browser-')),room=createRoomStore(root);
const capture=createRoomCapture(room);
const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小屋交互回归 · 虚构状态</title><div id="root"></div><script type="module" src="/tests/room-fixture.tsx"></script></html>';
const server=await createServer({configFile:false,root:ui,esbuild:{jsx:'automatic'},plugins:[{name:'room-fixture',configureServer(server){server.middlewares.use(async(req,res,next)=>{try{
  if(req.url?.startsWith('/api/')){
    const json=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
    let body='';if(['PUT','POST'].includes(req.method)){for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>3*1024*1024)throw Error('夹具请求过大');}}
    if(req.url==='/api/companion')return json(200,{state:'idle',label:'在小屋里待着呢'});
    if(req.url==='/api/room')return json(200,req.method==='PUT'?await room.update(JSON.parse(body)):await room.snapshot());
    if(req.url==='/api/room/context')return json(200,await room.context());
    if(req.url==='/api/room/environment')return json(200,req.method==='PUT'?await room.setAtmosphere(JSON.parse(body)):await room.atmosphere());
    if(req.url==='/api/room/capture'&&req.method==='POST')return json(200,await capture.request(JSON.parse(body)));
    if(req.url==='/api/room/render/claim'&&req.method==='POST'){const abort=new AbortController();res.on('close',()=>abort.abort());return json(200,{job:await capture.claim(JSON.parse(body).worker,abort.signal)});}
    if(req.url==='/api/room/render/complete'&&req.method==='POST')return json(200,await capture.complete(JSON.parse(body)));
    if(req.url==='/api/room/actions'&&req.method==='POST')return json(200,await room.move(JSON.parse(body)));
    if(req.url==='/api/room/photos'&&req.method==='POST')return json(201,await room.photo(JSON.parse(body)));
    const photo=req.url.match(/^\/api\/room\/photos\/(ph-[a-f0-9]{24})(\/image)?$/);if(photo){if(photo[2]){res.setHeader('Content-Type','image/png');return res.end(await room.image(photo[1]));}return json(200,await room.detail(photo[1]));}
    return json(404,{error:'此接口没有隔离夹具'});
  }
  if(req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}next();
}catch(error){res.writeHead(error.status||400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.message}));}});}}],server:{host:'127.0.0.1',port:9131,strictPort:true,fs:{allow:[ui]}}});
async function close(){capture.close();await server.close();await rm(root,{recursive:true,force:true});process.exit();}process.on('SIGINT',close);process.on('SIGTERM',close);
await server.listen();console.log('小屋隔离测试：http://127.0.0.1:9131（虚构档案，布置和照片仅存于临时目录）');
