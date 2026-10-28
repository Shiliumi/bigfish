import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {WebSocketServer} from 'ws';
import {renameStoredChat} from '../server/session-title.mjs';
test('renaming lazily attaches without a model turn and releases its temporary viewer',async()=>{
 const server=new WebSocketServer({host:'127.0.0.1',port:0});await once(server,'listening');const calls=[];let close;const closed=new Promise(resolve=>close=resolve);
 server.on('connection',socket=>{socket.once('close',close);socket.on('message',raw=>{const frame=JSON.parse(raw);calls.push(frame);socket.send(JSON.stringify({jsonrpc:'2.0',id:frame.id,result:frame.method==='session.resume'?{session_id:'runtime'}:{title:frame.params.title,pending:false}}));});});
 try{assert.deepEqual(await renameStoredChat('ws://127.0.0.1:'+server.address().port,'stored','new'),{ok:true});await closed;assert.deepEqual(calls.map(c=>c.method),['session.resume','session.title']);assert.equal(calls[0].params.lazy,true);assert.equal(calls[0].params.close_on_disconnect,true);assert.equal(calls[1].params.session_id,'runtime');}finally{await new Promise(resolve=>server.close(resolve));}
});
