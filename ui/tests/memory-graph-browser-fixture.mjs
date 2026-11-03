// Manual UI regression: node ui/tests/memory-graph-browser-fixture.mjs
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
import {mkdtemp,rm,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
const ui=fileURLToPath(new URL('..',import.meta.url)),root=await mkdtemp(path.join(os.tmpdir(),'fish-stars-browser-'));
await writeFile(path.join(root,'.fixture-owned'),'Synthetic memory star map QA.');
function python(data,command='api'){return new Promise((resolve,reject)=>{
 const p=spawn('python3',[path.join(ui,'tests/memory-graph-fixture.py'),root,command],{stdio:['pipe','pipe','pipe']});let output='',errors='';
 p.stdout.on('data',b=>output+=b);p.stderr.on('data',b=>errors+=b);p.on('error',reject);p.on('close',code=>{if(code)return reject(new Error(errors||'Fixture error'));try{resolve(JSON.parse(output));}catch(e){reject(e)}});p.stdin.end(JSON.stringify(data));
});}
await python({},'seed');let mode='normal';
const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>记忆星图 · 仅虚构验收</title><div id="root"></div><script type="module" src="/tests/memory-graph-fixture.tsx"></script></html>';
const server=await createServer({configFile:false,root:ui,esbuild:{jsx:'automatic'},plugins:[{name:'stars-fixture',configureServer(server){server.middlewares.use(async(req,res,next)=>{try{
 if(req.url?.startsWith('/api/')){
  const url=new URL(req.url,'http://127.0.0.1'),json=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};let body='';
  if(['PATCH','POST'].includes(req.method))for await(const chunk of req){body+=chunk;if(body.length>8000)throw Error('Fixture request too large');}
  if(url.pathname==='/api/fixture/mode'&&req.method==='POST'){mode=JSON.parse(body).mode;return json(200,{mode});}
  if(url.pathname==='/api/memory-graph'){
   if(mode==='fail')return json(503,{error:'虚构验收：模拟记忆库暂时离线'});
   const p=url.searchParams,value=await python({action:'graph',q:p.get('q')||'',scope:p.get('scope')||'current',kind:p.get('kind')||'all',pinned:p.get('pinned')==='true',from:p.get('from')||'',to:p.get('to')||''});
   if(mode==='empty'){value.nodes=[];value.edges=[];value.range={from:null,to:null};value.stats={...value.stats,shown:0,matched:0,current:0,historical:0,pinned:0,omitted:0};value.revision='empty';}
   return json(200,value);
  }
  if(url.pathname==='/api/episodes')return json(200,await python({q:url.searchParams.get('q')||'',scope:url.searchParams.get('scope')||'current'}));
  const episode=url.pathname.match(/^\/api\/episodes\/(ep-[a-f0-9]{24})$/);
  if(episode){const value=await python({...(req.method==='PATCH'?JSON.parse(body):{}),id:episode[1],action:req.method==='PATCH'?'update':'detail'});return value?json(200,value):json(404,{error:'这段回忆不存在或已遗忘。'});}
  return json(404,{error:'No fixture for this route'});
 }
 if(req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');return res.end(html);}next();
 }catch(error){res.writeHead(409,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.message}));}});}}],server:{host:'127.0.0.1',port:9132,strictPort:true,fs:{allow:[ui]}}});
async function close(){await server.close();await rm(root,{recursive:true,force:true});process.exit();}
process.on('SIGINT',close);process.on('SIGTERM',close);
await server.listen();console.log('记忆星图隔离验收：http://127.0.0.1:9132/ · 仅虚构档案');
