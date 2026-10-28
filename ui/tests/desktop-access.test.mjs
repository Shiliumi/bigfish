import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm,stat} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createDesktopAccess} from '../server/desktop-access.mjs';
test('desktop proof is private, persists across service restarts, and is not granted to a normal browser',async()=>{
 const root=await mkdtemp(path.join(os.tmpdir(),'fish-desktop-'));try{const access=await createDesktopAccess(root),key=(await readFile(path.join(root,'.setup/desktop-access.key'),'utf8')).trim();assert.equal((await stat(path.join(root,'.setup/desktop-access.key'))).mode&0o777,0o600);assert.equal(access.allowed({headers:{}}),false);assert.equal(access.allowed({headers:{'x-fish-desktop':'incorrect'}}),false);assert.equal(access.allowed({headers:{'x-fish-desktop':key}}),true);assert.ok(!access.cookie.includes(key));const restarted=await createDesktopAccess(root);assert.equal(restarted.allowed({headers:{cookie:access.cookie.split(';')[0]}}),true);}finally{await rm(root,{recursive:true,force:true});}
});
test('standalone browser entry and its old session cookie cannot access the application',async()=>{
 const base='http://127.0.0.1:9120';const page=await fetch(base);assert.equal(page.status,410);assert.ok(!(await page.text()).includes('<script'));assert.equal(page.headers.get('set-cookie'),null);assert.equal((await fetch(base+'/api/hermes/summary',{headers:{cookie:'fish_session=old'}})).status,401);assert.equal((await fetch(base+'/health')).status,200);
});
test('Hermes runs headless and no longer serves its dashboard SPA',async()=>{
 const response=await fetch('http://127.0.0.1:9119/');const html=await response.text();assert.ok(!/<script[^>]+src=/.test(html));assert.ok(!html.includes('id="app"'));
});
