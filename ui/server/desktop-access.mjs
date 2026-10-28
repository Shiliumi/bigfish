import {readFile,writeFile,mkdir,chmod} from 'node:fs/promises';
import path from 'node:path';
import {homedir} from 'node:os';
export const desktopKeyPath=()=>path.join(homedir(),'Library/Application Support/Bigfish/desktop-access.key');
import {randomBytes,createHash,timingSafeEqual} from 'node:crypto';
const equals=(a,b)=>typeof a==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
export async function createDesktopAccess(root,{keyPath=path.join(root,'.setup/desktop-access.key')}={}){
 const file=keyPath;await mkdir(path.dirname(file),{recursive:true});
 let token;try{token=(await readFile(file,'utf8')).trim();}catch(e){if(e.code!=='ENOENT')throw e;}
 if(!/^[a-f0-9]{64}$/.test(token||'')){token=randomBytes(32).toString('hex');await writeFile(file,token+'\n',{mode:0o600});}await chmod(file,0o600);
 const cookie=createHash('sha256').update('bigfish-desktop:'+token).digest('hex');
 return {header:req=>equals(req.headers['x-fish-desktop'],token),allowed(req){return this.header(req)||(req.headers.cookie||'').split(';').some(c=>equals(c.trim(),'fish_desktop='+cookie));},cookie:`fish_desktop=${cookie}; HttpOnly; SameSite=Strict; Path=/`};
}
