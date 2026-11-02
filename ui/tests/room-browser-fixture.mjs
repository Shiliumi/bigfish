// Run manually: node ui/tests/room-browser-fixture.mjs. No live profile or model API is used.
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
const ui=fileURLToPath(new URL('..',import.meta.url));
const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>小屋交互回归 · 虚构状态</title><div id="root"></div><script type="module" src="/tests/room-fixture.tsx"></script></html>';
const server=await createServer({configFile:false,root:ui,esbuild:{jsx:'automatic'},plugins:[{name:'room-fixture',configureServer(server){server.middlewares.use((req,res,next)=>{
  if(req.url?.startsWith('/api/')){const known=req.url==='/api/companion';res.statusCode=known?200:404;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(known?{state:'idle',label:'在小屋里待着呢'}:{error:'此接口没有隔离夹具'}));return;}
  if(req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}next();
});}}],server:{host:'127.0.0.1',port:9131,strictPort:true,fs:{allow:[ui]}}});
await server.listen();console.log('小屋隔离测试：http://127.0.0.1:9131（虚构状态，不读取真实档案）');
