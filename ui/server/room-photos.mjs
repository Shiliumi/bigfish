import {mkdir,readdir,stat,rename,unlink} from 'node:fs/promises';
import path from 'node:path';import {createHash} from 'node:crypto';
const error=(message,status=400)=>Object.assign(new Error(message),{status});
export const publicPhoto=p=>({id:p.id,caption:p.caption,created_at:p.created_at,view:p.view,revision:p.revision,width:p.width,height:p.height,deleted_at:p.deleted_at??null,image_url:'/api/room/photos/'+p.id+'/image'});
export function createPhotoLibrary(folder,{maxBytes=200*1024*1024,maxCount=500}={}){
  const staging=path.join(folder,'.purge'),file=id=>path.join(folder,id+'.png'),staged=id=>path.join(staging,id+'.png');
  const exists=async p=>Boolean(await stat(p).catch(e=>{if(e.code==='ENOENT')return null;throw e;}));
  async function recover(s){
    const stagedNames=new Set(await readdir(staging).catch(e=>{if(e.code==='ENOENT')return [];throw e;}));
    for(const p of s.photos){if(!/^ph-[a-f0-9]{24}$/.test(p.id))throw error('照片清单损坏，原存档已保留。',503);if(!stagedNames.has(p.id+'.png'))continue;
      if(p.purged_at)await unlink(staged(p.id)).catch(()=>{});else if(!await exists(file(p.id)))await rename(staged(p.id),file(p.id));
    }
  }
  async function usage(s){let bytes=0;for(const dir of [folder,staging])for(const name of await readdir(dir).catch(e=>{if(e.code==='ENOENT')return [];throw e;})){if(!/^ph-[a-f0-9]{24}\.png$/.test(name))continue;const info=await stat(path.join(dir,name));if(info.isFile())bytes+=info.size;}
    return {bytes,max_bytes:maxBytes,count:s.photos.filter(p=>!p.purged_at).length,max_count:maxCount,active:s.photos.filter(p=>!p.deleted_at&&!p.purged_at).length,trash:s.photos.filter(p=>p.deleted_at&&!p.purged_at).length};}
  async function library(s,scope='active',offset=0){if(!['active','trash'].includes(scope)||!Number.isSafeInteger(offset)||offset<0||offset>100000)throw error('相册筛选不正确。');const rows=s.photos.filter(p=>!p.purged_at&&(scope==='trash'?!!p.deleted_at:!p.deleted_at)).slice().reverse();return {revision:s.photo_revision??0,scope,items:rows.slice(offset,offset+24).map(publicPhoto),total:rows.length,offset,has_more:offset+24<rows.length,usage:await usage(s)};}
  return {recover,library,
    async reserve(s,bytes){const value=await usage(s);if(value.bytes+bytes>maxBytes||value.count>=maxCount)throw error('相册空间不足，请导出并清理回收站后再拍照。',413);},
    async manage(s,data,save){
      if(!data||!['trash','restore','purge'].includes(data.action)||!/^ph-[a-f0-9]{24}$/.test(data.id)||!Number.isSafeInteger(data.revision)||typeof data.operation_id!=='string'||!/^[a-f0-9-]{36}$/.test(data.operation_id))throw error('照片管理请求不正确。');
      const hash=createHash('sha256').update(JSON.stringify([data.action,data.id,data.revision,data.confirm??null])).digest('hex');s.photo_receipts??=[];
      const old=s.photo_receipts.find(p=>p.id===data.operation_id);if(old){if(old.hash!==hash)throw error('同一照片操作发生了变化。',409);return old.result;}
      if(data.revision!==(s.photo_revision??0))throw error('相册已更新，请重新读取后操作。',409);const p=s.photos.find(p=>p.id===data.id);if(!p||p.purged_at)throw error('照片已永久删除或不存在。',410);
      if(data.action==='purge'&&(!p.deleted_at||data.confirm!=='delete-photo-permanently'))throw error('请先移入回收站，并明确确认永久删除。');
      let moved=false;
      if(data.action==='purge'&&await exists(file(p.id))){await mkdir(staging,{recursive:true,mode:0o700});await rename(file(p.id),staged(p.id));moved=true;}
      const now=new Date().toISOString();
      if(data.action==='trash')p.deleted_at??=now;else if(data.action==='restore')p.deleted_at=null;else {for(const key of Object.keys(p))if(!['id','view','created_at','revision','width','height','deleted_at'].includes(key))delete p[key];p.purged_at=now;}
      s.photo_revision=(s.photo_revision??0)+1;const result={ok:true,revision:s.photo_revision};s.photo_receipts.push({id:data.operation_id,hash,result});s.photo_receipts=s.photo_receipts.slice(-200);
      try{await save(s);}catch(e){if(moved)await rename(staged(p.id),file(p.id));throw e;}
      if(data.action==='purge')await unlink(staged(p.id)).catch(()=>{});return result;
    },
  };
}
