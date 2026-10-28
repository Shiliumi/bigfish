import {spawn} from 'node:child_process';
import path from 'node:path';
export function journal(root,data){
 return learningScript(root,'fish_journal.py',data);
}
export function learningScript(root,script,data){
 if(!['fish_journal.py','personality.py','fish_budget.py'].includes(script))return Promise.reject(new Error('不支持的本机操作。'));
 return new Promise((resolve,reject)=>{
  const child=spawn(process.env.FISH_PYTHON||'python3',[path.join(root,'scripts',script),'api'],{cwd:root,stdio:['pipe','pipe','pipe']});let output='',done=false;
  const finish=(error,value)=>{if(done)return;done=true;clearTimeout(timer);error?reject(error):resolve(value);};
  const timer=setTimeout(()=>{child.kill();finish(Object.assign(new Error('回忆库响应超时，请稍后重试。'),{status:503}));},12000);
  child.stdout.on('data',chunk=>{output+=chunk;if(output.length>1024*1024){child.kill();finish(new Error('回忆结果过长。'));}});
  child.stderr.resume();child.on('error',()=>finish(Object.assign(new Error('本机回忆库尚未就绪。'),{status:503})));
  child.on('close',code=>{try{const value=JSON.parse(output);if(code||value?.error)return finish(Object.assign(new Error(value?.error||'回忆操作失败，请重试。'),{status:409}));finish(null,value);}catch{finish(Object.assign(new Error('回忆库返回格式异常。'),{status:503}));}});
  child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(data));
 });
}
