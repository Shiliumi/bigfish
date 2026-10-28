import {WebSocket} from 'ws';
// The standalone Hermes session transport owns Bigfish chats. A metadata-only
// lazy attachment lets it rename a stored chat without starting a model turn.
const failure=message=>Object.assign(new Error(message),{status:503});
export async function renameStoredChat(url,id,title){
 const socket=new WebSocket(url,{origin:'http://127.0.0.1:9119'}),pending=new Map();let sequence=0;
 const ready=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(failure('连接 Hermes 超时。')),8000);socket.once('open',()=>{clearTimeout(timer);resolve()});socket.once('error',()=>{clearTimeout(timer);reject(failure('Hermes 连接暂时不可用。'))});});
 socket.on('message',data=>{for(const line of data.toString().split('\n')){let frame;try{frame=JSON.parse(line)}catch{continue}const p=pending.get(frame.id);if(!p||frame.method)continue;pending.delete(frame.id);clearTimeout(p.timer);if(frame.error)p.reject(failure('Hermes 没有完成标题修改。'));else p.resolve(frame.result);}});
 socket.on('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(failure('Hermes 连接已断开，标题可能尚未保存。'));}pending.clear()});
 const rpc=(method,params)=>new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(failure('标题修改响应超时，请刷新核对后再试。'));},8000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({jsonrpc:'2.0',id,method,params:{...params,profile:'default'}}));});
 try{await ready;const session=await rpc('session.resume',{session_id:id,lazy:true,inline_images:false,close_on_disconnect:true,source:'bigfish'});const result=await rpc('session.title',{session_id:session.session_id,title});if(result.pending||result.title!==title)throw failure('标题尚未保存，请稍后刷新核对。');return {ok:true};}finally{socket.close();}
}
