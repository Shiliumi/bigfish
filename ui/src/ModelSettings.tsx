import {useEffect, useState} from 'react'
import {AlertCircle, CheckCircle2, RefreshCw, Settings2, Sparkles} from 'lucide-react'
import {api} from './api'
import './settings.css'
export interface ModelConfig {provider:string;base_url:string;model:string;name:string;has_key:boolean;api_mode:string;version:string}
export default function ModelSettings({busy,onSaved,onEdit}:{busy:boolean;onSaved:(config:ModelConfig)=>Promise<void>;onEdit:(key:string)=>void}) {
  const [config,setConfig]=useState<ModelConfig|null>(null),[base,setBase]=useState(''),[model,setModel]=useState(''),[key,setKey]=useState(''),[clearKey,setClearKey]=useState(false)
  const [models,setModels]=useState<string[]>([]),[pending,setPending]=useState('loading'),[error,setError]=useState(''),[result,setResult]=useState<{message:string;latency_ms:number}|null>(null),[notice,setNotice]=useState('')
  async function load(){setPending('loading');setError('');try{const value=await api<ModelConfig>('/model-settings');setConfig(value);setBase(value.base_url);setModel(value.model);setKey('');setClearKey(false)}catch(e){setError((e as Error).message)}finally{setPending('')}}
  useEffect(()=>{void load()},[])
  const sameAddress=base.trim().replace(/\/+$/,'')===config?.base_url
  function connectionChanged(){setError('');setResult(null);setNotice('')}
  const payload=()=>({base_url:base,model,api_key:key,clear_key:clearKey,version:config?.version})
  async function run(action:'models'|'test'|'save') {
    setPending(action);setError('');setResult(null);setNotice('')
    try {
      if(action==='models'){const value=await api<{models:string[]}>('/model-settings/models',{method:'POST',body:JSON.stringify(payload())});setModels(value.models);setNotice(`找到 ${value.models.length} 个模型，可从下方列表选择。`)}
      if(action==='test'){const value=await api<{message:string;latency_ms:number}>('/model-settings/test',{method:'POST',body:JSON.stringify(payload())});setResult(value)}
      if(action==='save'){const value=await api<ModelConfig>('/model-settings',{method:'PUT',body:JSON.stringify(payload())});setKey('');setClearKey(false);setConfig(value);setNotice('已保存，接下来的新对话会使用这个模型。');await onSaved(value)}
    }catch(e){setError((e as Error).message)}finally{setPending('')}
  }
  const disabled=Boolean(pending)
  return <div className="fish-settings">
    <div className="settings-intro"><span className="settings-symbol"><Sparkles size={21}/></span><div><h3>给小鲸鱼换个脑袋</h3><p>连接你自己的模型服务，记忆和聊天记录继续留在这台 Mac。</p></div></div>
    {pending==='loading'?<div className="settings-loading"><RefreshCw size={17} className="spin"/>正在读取本机配置…</div>:config?<>
      <fieldset className="model-fields" disabled={disabled}>
        <div className="model-protocol"><span>接口类型</span><strong>OpenAI 兼容 · Chat Completions</strong></div>
        <label className="model-field"><span>API 基础地址</span><input type="url" aria-label="模型 API 地址" value={base} placeholder="https://api.example.com/v1" autoComplete="off" spellCheck={false} onChange={e=>{setBase(e.target.value);setKey('');setModels([]);setClearKey(false);connectionChanged()}}/><small>填到 /v1 或服务商指定的基础路径，不需要 /chat/completions。</small></label>
        <div className="endpoint-shortcuts"><span>快捷填入</span><button type="button" onClick={()=>{setBase('https://api.deepseek.com/v1');setModel('deepseek-flash');setKey('');setClearKey(false);setModels([]);connectionChanged()}}>DeepSeek</button><button type="button" onClick={()=>{setBase('http://localhost:11434/v1');setModel('');setKey('');setClearKey(false);setModels([]);connectionChanged()}}>本机 Ollama</button></div>
        <label className="model-field"><span>API Key <em>本机保存</em></span><input type="password" aria-label="模型 API 密钥" value={key} placeholder={sameAddress&&config.has_key&&!clearKey?'已保存密钥，留空继续使用':'输入此服务的密钥；本机免密服务可留空'} autoComplete="new-password" spellCheck={false} onChange={e=>{setKey(e.target.value);setClearKey(false);connectionChanged()}}/><small>{sameAddress?'密钥不会回显，也不会进入聊天记录。':'已更换地址：旧密钥不会带到这个服务，请填写新密钥。'}</small></label>
        {sameAddress&&config.has_key&&<label className="clear-model-key"><input type="checkbox" checked={clearKey} onChange={e=>{setClearKey(e.target.checked);setKey('');connectionChanged()}}/>不使用已保存的密钥（用于免密服务）</label>}
        <div className="model-picker-heading"><label htmlFor="fish-model-id">模型名称</label><button type="button" className="text-button" onClick={()=>void run('models')} disabled={!base.trim()}><RefreshCw size={13} className={pending==='models'?'spin':''}/>{pending==='models'?'获取中…':'获取模型列表'}</button></div>
        <input id="fish-model-id" className="model-id-input" aria-label="模型名称" value={model} placeholder="填写服务商提供的完整模型 ID" spellCheck={false} autoComplete="off" onChange={e=>{setModel(e.target.value);connectionChanged()}}/>
        {models.length>0&&<label className="model-select"><span>从列表选择</span><select aria-label="选择模型" value={models.includes(model)?model:''} onChange={e=>{setModel(e.target.value);connectionChanged()}}><option value="" disabled>选择一个模型</option>{models.map(id=><option key={id} value={id}>{id}</option>)}</select></label>}
        <p className="model-hint">没有模型列表也可以手动填写。自主冲浪需要模型支持工具调用。</p>
      </fieldset>
      <div className="model-feedback" aria-live="polite">{error&&<p className="model-error" role="alert"><AlertCircle size={17}/><span>{error}</span></p>}{result&&<p className="model-success"><CheckCircle2 size={17}/><span>{result.message}<small>耗时 {(result.latency_ms/1000).toFixed(2)} 秒</small></span></p>}{notice&&<p className="model-notice">{notice}</p>}</div>
      <div className="model-setting-actions"><p>保存会开启新对话，旧聊天仍在「最近聊过」。<br/>测试会发一条简短请求，消耗少量 token。</p><div><button className="secondary-button" disabled={disabled||!base.trim()||!model.trim()} onClick={()=>void run('test')}>{pending==='test'&&<RefreshCw size={14} className="spin"/>}测试连通性</button><button className="primary-button" disabled={disabled||busy||!base.trim()||!model.trim()} onClick={()=>void run('save')}>{pending==='save'&&<RefreshCw size={14} className="spin"/>}{pending==='save'?'保存中…':'保存并开启新对话'}</button></div>{busy&&<small>她正在回复，结束后可以保存切换。</small>}</div>
    </>:<div className="model-feedback"><p className="model-error" role="alert">{error}</p><button className="secondary-button" onClick={()=>void load()}>重新读取</button></div>}
    <div className="settings-more"><h4>相处的小偏好</h4><button disabled={disabled} onClick={()=>onEdit('interests')}><Settings2 size={17}/><span>兴趣与探索偏好</span><span>›</span></button><button disabled={disabled} onClick={()=>onEdit('soul')}><Sparkles size={17}/><span>她的人格与说话方式</span><span>›</span></button></div>
  </div>
}
