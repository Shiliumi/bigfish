import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,copyFile,rm} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {journal} from '../server/journal.mjs';
const run=promisify(execFile);
test('native journal bridge round-trips explicit aliases, revision conflicts and tombstones',async t=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-journal-bridge-'));t.after(()=>rm(root,{recursive:true,force:true}));await mkdir(path.join(root,'scripts'));
 await copyFile(new URL('../../scripts/fish_journal.py',import.meta.url),path.join(root,'scripts/fish_journal.py'));
 const {stdout}=await run(process.env.FISH_PYTHON||'python3',['-c',`import sys;sys.path.insert(0,sys.argv[1]);from fish_journal import Journal;from pathlib import Path\nwith Journal(Path(sys.argv[1]).parent) as store:print(store.capture('bridge-test','一起看木间实验室的折叠凳。','这个榫卯结构挺巧。')['id'])`,path.join(root,'scripts')]);
 const id=stdout.trim();await journal(root,{action:'update',id,revision:1,aliases:['木头哥','MuJianLab']});
 const found=await journal(root,{q:'MuJianLab'});assert.equal(found.items[0].id,id);assert.equal(found.items[0].match_kind,'alias');assert.ok(!Object.hasOwn(found.items[0],'excerpt'));
 const detail=await journal(root,{action:'detail',id});assert.deepEqual(detail.aliases,['木头哥','MuJianLab']);assert.equal(detail.revision,2);
 await assert.rejects(()=>journal(root,{action:'update',id,revision:1,aliases:['stale-name']}));
 await journal(root,{action:'update',id,revision:2,forget:true});assert.deepEqual((await journal(root,{q:'MuJianLab',scope:'history'})).items,[]);
});
