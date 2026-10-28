import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {parse} from 'yaml';
const error = (message,status=400) => Object.assign(new Error(message),{status});
const hash = value => createHash('sha256').update(value).digest('hex');
export function normalizeBase(value) {
  if(typeof value!=='string'||value.length>2048)throw error('请填写 API 地址。');
  let url;try{url=new URL(value.trim());}catch{throw error('API 地址需要包含 https:// 或 http://。');}
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw error('API 地址不能包含账号、密码、查询参数或锚点。');
  if(url.protocol==='http:'&&!['localhost','127.0.0.1','[::1]'].includes(url.hostname))throw error('远程 API 请使用 HTTPS；本机服务可使用 HTTP。');
  url.pathname=url.pathname.replace(/\/+$/,'');
  if(/\/(chat\/completions|models|responses)$/.test(url.pathname))throw error('请填写服务的基础地址，例如 https://api.example.com/v1，不要带 /chat/completions 或 /models。');
  return url.toString().replace(/\/+$/,'');
}
export function parseEnv(text){
  const env={};for(const line of text.split('\n')){const match=line.match(/^\s*(?:export\s+)?([A-Za-z_][\w]*)\s*=\s*(.*?)\s*$/);if(!match)continue;let value=match[2];if(value.startsWith('"')&&value.endsWith('"')){try{value=JSON.parse(value);}catch{value=value.slice(1,-1);}}else if(value.startsWith("'")&&value.endsWith("'"))value=value.slice(1,-1);else value=value.replace(/\s+#.*$/,'');env[match[1]]=value;}return env;
}
const secret = (value,env) => {if(typeof value!=='string')return '';const ref=value.match(/^\$\{([A-Za-z_][\w]*)\}$/);return ref?env[ref[1]]||'':value;};
export function resolveConnection(config,env){
  const m=typeof config.model==='object'&&config.model?config.model:{default:config.model};
  const provider=m.provider||'deepseek', p=config.providers?.[provider]||{};
  const base_url=normalizeBase(m.base_url||p.base_url||(provider==='deepseek'?'https://api.deepseek.com/v1':provider==='openai'?'https://api.openai.com/v1':''));
  const keyEnv=m.key_env||m.api_key_env||p.key_env||p.api_key_env;
  const key=secret(m.api_key,env)||secret(p.api_key,env)||(keyEnv?env[keyEnv]||'':'')||(provider==='deepseek'?env.DEEPSEEK_API_KEY||'':provider==='openai'?env.OPENAI_API_KEY||'':'');
  return {provider,base_url,model:String(m.default||p.model||''),key,name:p.name|| (provider==='deepseek'?'DeepSeek':provider==='openai'?'OpenAI':'自定义服务'),api_mode:m.api_mode||p.api_mode||'chat_completions'};
}
export function createModelSettings(root,{native,fetcher=fetch,isBusy=()=>false,readConnection}={}){
  let saving=false;
  async function read(){
    if(readConnection)return readConnection();
    const [cfg,env]=await Promise.all([readFile(path.join(root,'.hermes/config.yaml'),'utf8'),readFile(path.join(root,'.hermes/.env'),'utf8').catch(e=>{if(e.code==='ENOENT')return '';throw e;})]);
    return resolveConnection(parse(cfg)||{},parseEnv(env));
  }
  const version=c=>hash(JSON.stringify(c));
  const publicState=c=>({provider:c.provider,base_url:c.base_url,model:c.model,name:c.name,has_key:Boolean(c.key),api_mode:c.api_mode,version:version(c)});
  async function draft(data,requireModel=false){
    if(!data||typeof data!=='object'||Array.isArray(data))throw error('模型设置格式不正确。');
    const current=await read(),base_url=normalizeBase(data.base_url);
    if(data.api_key!==undefined&&(typeof data.api_key!=='string'||data.api_key.length>4096||/[\r\n\x00-\x1f\x7f]/.test(data.api_key)))throw error('密钥格式不正确。');
    if(data.clear_key!==undefined&&typeof data.clear_key!=='boolean')throw error('密钥设置格式不正确。');
    const submitted=data.api_key?.trim()||'';
    const key=data.clear_key?'':submitted||(base_url===current.base_url?current.key:'');
    const model=typeof data.model==='string'?data.model.trim():'';
    if(model.length>256||/[\x00-\x1f\x7f]/.test(model)||requireModel&&!model)throw error('请填写有效的模型名称。');
    return {current,base_url,key,model};
  }
  async function request(c,route,payload){
    let response;try{response=await fetcher(c.base_url+route,{method:payload?'POST':'GET',headers:{Accept:'application/json',...(c.key?{Authorization:'Bearer '+c.key}:{}),...(payload?{'Content-Type':'application/json'}:{})},body:payload?JSON.stringify(payload):undefined,redirect:'error',signal:AbortSignal.timeout(25000)});}catch(e){throw error(e.name==='TimeoutError'||e.name==='AbortError'?'请求超时，请检查地址或稍后再试。':'无法连接该 API，请检查地址、网络和 HTTPS 证书。',502);}
    if(!response.ok){await response.body?.cancel().catch(()=>{});const messages={401:'密钥无效或已过期，请检查 API Key。',403:'该密钥没有访问权限。',402:'模型服务提示余额不足。',404:route==='/models'?'服务未提供模型列表，请手动填写模型名后测试。':'未找到模型或接口，请检查基础地址与模型名。',429:'服务正在限流或额度已达上限，请稍后再试。'};throw error(messages[response.status]||`模型服务返回 HTTP ${response.status}。`,502);}
    try{return await response.json();}catch{throw error('服务没有返回有效的 JSON，请检查 API 地址。',502);}
  }
  return {
    snapshot:async()=>publicState(await read()),
    balanceConnection:async()=>{const c=await read();return new URL(c.base_url).hostname==='api.deepseek.com'?c:null;},
    async list(data){const c=await draft(data);const result=await request(c,'/models');const rows=Array.isArray(result.data)?result.data:Array.isArray(result.models)?result.models:[];const models=[...new Set(rows.map(v=>typeof v==='string'?v:v?.id||v?.name).filter(v=>typeof v==='string'&&v.length>0&&v.length<=256))].sort().slice(0,2000);if(!models.length)throw error('接口没有提供可选模型，可手动填写模型名。',502);return {models};},
    async test(data){const c=await draft(data,true),start=Date.now();const result=await request(c,'/chat/completions',{model:c.model,messages:[{role:'user',content:'Reply with OK.'}],max_tokens:32,stream:false});const message=result?.choices?.[0]?.message;if(!message||![message.content,message.reasoning_content,message.tool_calls].some(v=>typeof v==='string'?Boolean(v.trim()):Array.isArray(v)&&v.length))throw error('接口已响应，但没有返回有效的模型回复。',502);return {ok:true,latency_ms:Date.now()-start,model:c.model,message:'模型已成功生成回复，可以连接。'};},
    async save(data){
      if(saving||isBusy())throw error('她还在回复，等这句说完再切换模型。',409);
      saving=true;try{const c=await draft(data,true);if(data.version!==version(c.current))throw error('模型配置刚刚被修改，请关闭设置后重新打开。',409);
        if(!native)throw error('模型配置暂时无法保存。',503);
        const id='fish-'+hash(c.base_url).slice(0,12);
        const name=typeof data.name==='string'&&data.name.trim()?data.name.trim().slice(0,60):new URL(c.base_url).hostname;
        let result;try{result=await native('/api/providers/custom-endpoints?profile=default','POST',{id,name,base_url:c.base_url,model:c.model,api_key:c.key,api_mode:'chat_completions',models:[c.model],discover_models:true,make_default:true});}catch{throw error('Hermes 未能保存模型配置，请确认后台连接后重试。',503);}
        if(!result.ok)throw error('模型配置没有保存成功。',503);
        return {ok:true,...await this.snapshot()};
      }finally{saving=false;}
    },
  };
}
