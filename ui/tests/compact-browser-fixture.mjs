// All data is synthetic and volatile; never proxies the real application API.
import {createServer} from 'vite';import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('..',import.meta.url)),counts={};
const jobs=[{id:'fixture-surf',name:'fish-surf',enabled:true,next_run_at:'2026-11-04T10:00:00Z',last_status:'ok',last_run_at:'2026-11-04T01:00:00Z',schedule:{expr:'0 9,12,15,18,21 * * *'}},{id:'fixture-memory',name:'fish-memory',enabled:true,next_run_at:'2026-11-04T14:30:00Z',schedule:{expr:'30 22 * * *'}}];
const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>大肥鱼精简验收 · 虚构状态</title><div id="root"></div><script>window.__FISH_DESKTOP__=true</script><script type="module" src="/tests/compact-fixture.tsx"></script></html>';
const server=await createServer({configFile:false,root,esbuild:{jsx:'automatic'},plugins:[{name:'compact-fixture',configureServer(s){s.middlewares.use(async(req,res,next)=>{if(req.url==='/'){res.setHeader('Content-Type','text/html;charset=utf-8');return res.end(html);}if(!req.url?.startsWith('/api/'))return next();const json=(code,value)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};const u=new URL(req.url,'http://127.0.0.1'),name=u.pathname.slice(5);counts[name]=(counts[name]||0)+1;let body='';for await(const part of req)body+=part;
 if(name==='fixture/requests')return json(200,counts);
 if(name==='overview')return json(200,{connected:true,model:'虚构验收模型',jobs,reports:[{id:'surf',type:'surf',title:'虚构验收：纸机关',date:'2026-11-04',preview:'读了纸机关的折痕',content:'# 纸机关\n虚构阅读材料',modified:'2026-11-04T01:00:00Z'},{id:'memory',type:'memory',title:'虚构验收：整理记录',date:'2026-11-04',preview:'整理完毕',content:'# 整理\n未修改核心记忆',modified:'2026-11-04T01:00:00Z'}],visited:[],memories:2});
 if(name==='sessions')return json(200,[]);
 if(name==='inbox')return json(200,{messages:[],unread:0,can_interrupt:false,alert_ids:[],settings:{enabled:true,dailyLimit:2,greetings:true}});
 if(name==='documents')return json(200,Object.fromEntries(['user','memory','soul','interests'].map(n=>[n,{content:'虚构验收 '+n,version:'fixture'}])));
 if(name==='stickers')return json(200,{items:[{id:'1234567890abcdef',name:'虚构验收：开心',emotion:'开心',tags:['开心'],use:'表达开心',source:'https://example.org/fiction',author:'虚构验收',image_url:'/character.webp'}]});
 if(name==='curiosity')return json(200,{threads:[],runs:[],controls:{revision:0,items:[]}});
 if(name==='episodes')return json(200,{items:[],stats:{total:0,historical:0}});
 if(name==='matters')return json(200,{items:[]});
 if(name==='personality')return json(200,{trials:[],legacy_traits:[],history:[]});
 if(name==='model-settings')return json(200,{provider:'custom',base_url:'https://example.org/v1',model:'fixture',name:'虚构验收',has_key:false,api_mode:'chat',version:'fixture'});
 if(name==='hermes/summary')return json(200,{version:'fixture',gateway_running:true,active_sessions:0,partial:false,jobs,stats:{total:0,messages:0}});
 if(name==='hermes/tools'||name==='hermes/skills')return json(200,[]);
 if(name==='hermes/sessions')return json(200,{sessions:[],total:0,has_more:false});
 if(name.endsWith('/runs'))return json(200,{runs:[{started_at:1793754000,status:'已完成'}]});
 if(name.startsWith('jobs/')){const j=jobs.find(j=>name.includes(j.id));if(j)j.enabled=name.endsWith('/resume');return json(200,{ok:true});}
 if(name==='usage')return json(503,{error:'虚构夹具不提供用量记录'});
 if(name==='room/life/presence'||name==='presence')return json(200,{ok:true});
 if(name==='room/environment')return json(200,{revision:1,environment:{period:'auto',weather:'clear',lamp:true}});
 if(name==='room/render/claim'){const timer=setTimeout(()=>json(200,{job:null}),15000);res.on('close',()=>clearTimeout(timer));return;}
 if(name==='chat-ticket')return json(503,{error:'隔离验收不连接真实模型'});
 return json(404,{error:'隔离验收未提供该接口'});
 });}}],server:{host:'127.0.0.1',port:9132,strictPort:true,fs:{allow:[root]}}});
async function close(){await server.close();process.exit();}process.on('SIGINT',close);process.on('SIGTERM',close);await server.listen();console.log('精简界面隔离验收：http://127.0.0.1:9132');
