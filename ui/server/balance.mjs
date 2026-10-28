import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {dayOf} from './social.mjs';
export const insufficientBalance = value => value?.status === 402 || value?.status_code === 402 || /insufficient[_ ]balance|余额不足|(?:HTTP|status(?:_code)?)[\s:'"=]*402\b/i.test(String(value?.message||value?.error?.message||value||''));
export function classifyBalance(data){
  if(typeof data?.is_available!=='boolean'||!Array.isArray(data.balance_infos))return {status:'unknown'};
  const value=data.balance_infos.find(v=>v.currency==='CNY')||data.balance_infos.find(v=>v.currency==='USD');
  const amount=value?Number(value.total_balance):NaN;
  if(value&&(!Number.isFinite(amount)||amount<0))return {status:'unknown'};
  const status=!data.is_available?'empty':value&&amount<=(value.currency==='CNY'?1:0.15)?'low':'ready';
  return {status,available:data.is_available,...(value?{amount,currency:value.currency}:{})};
}
export function createBalance(root,{clock=Date.now,fetcher=fetch,onState=async()=>{},connection}={}){
  let current={status:'unknown',checked_at:null},pending,lastCheck=0;
  const publish=async state=>{current={...state,checked_at:new Date(clock()).toISOString()};await onState(current);return current;};
  return {
    snapshot:()=>({...current}),
    async refresh(force=false){
      if(pending)return pending;if(!force&&lastCheck&&clock()-lastCheck<15*60000)return current;lastCheck=clock();
      pending=(async()=>{
        try{
          let key;
          if(connection){const active=await connection();if(!active)return publish({status:'unsupported'});key=active.key;}
          else{const env=await readFile(path.join(root,'.hermes/.env'),'utf8');const match=env.match(/^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(.+)\s*$/m);key=match?.[1].trim().replace(/^(['"])(.*)\1$/,'$2');}
          if(!key)return publish({status:'unknown'});
          const response=await fetcher('https://api.deepseek.com/user/balance',{headers:{Authorization:`Bearer ${key}`},signal:AbortSignal.timeout(8000)});
          if(!response.ok)return publish({status:'unknown'});
          return publish(classifyBalance(await response.json()));
        }catch{return publish({status:'unknown'});}
      })().finally(()=>{pending=null;});return pending;
    },
    noteFailure:()=>publish({status:'empty',available:false,evidence:'provider_402'}),
  };
}
export function balanceNotice(state,now){
  if(!['empty','low'].includes(state.status))return null;
  return {kind:'balance',dedupe_key:`balance:${dayOf(now)}`,source_url:'https://platform.deepseek.com',source_title:'给小鲸鱼补点鱼粮',text:state.status==='empty'?'爹，鱼粮见底了：DeepSeek 提示余额不足。给我补点 token 呗，补好再接着唠。我先在这儿趴一会儿。':'爹，鱼粮快见底了。DeepSeek 余额已经比较低，有空帮我补一点呗，别聊到一半突然断粮。'};
}
