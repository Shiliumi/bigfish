import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,copyFile,rm} from 'node:fs/promises';import path from 'node:path';import os from 'node:os';import {fileURLToPath} from 'node:url';
import {learningScript} from '../server/journal.mjs';
test('matter bridge carries real state, exact source notes and version conflicts through the local Python API',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-matters-api-'));t.after(()=>rm(root,{recursive:true,force:true}));await mkdir(path.join(root,'scripts'));
 for(const name of ['fish_journal.py','fish_matters.py'])await copyFile(fileURLToPath(new URL('../../scripts/'+name,import.meta.url)),path.join(root,'scripts',name));
 const call=data=>learningScript(root,'fish_matters.py',data),title='准备完成纸桥承重实验';
 const added=await call({action:'remember',title,kind:'goal'});assert.equal(added.item.source_ref,'local:editor');assert.equal(added.item.quote,title);
 const id=added.item.id;assert.equal((await call({action:'remember',title,kind:'goal'})).item.id,id);
 const updated=await call({action:'update',id,revision:1,status:'done',quote:'纸桥承重实验已经完成了，做了两种结构。'});assert.equal(updated.item.effective_status,'done');
 await assert.rejects(()=>call({action:'update',id,revision:1,status:'paused'}),e=>e.status===409);
 const detail=await call({action:'detail',id});assert.equal(detail.history.length,2);assert.ok(!JSON.stringify(detail).includes('turn_hash'));assert.equal(detail.quote,'纸桥承重实验已经完成了，做了两种结构。');
 assert.equal((await call({action:'list',query:'纸桥'})).items.length,1);
 await call({action:'update',id,revision:2,status:'done',forget:true});assert.equal(await call({action:'detail',id}),null);
 assert.equal((await call({action:'list'})).items.length,0);
});
