export const refreshTTL:Record<string,number>
export function createResourceRefresh(options:{load:(name:string)=>Promise<any>;apply:(name:string,value:any)=>void;now?:()=>number;ttl?:Record<string,number>}):{get:(name:string,options?:{force?:boolean})=>Promise<any>;refresh:(names:string[],options?:{force?:boolean})=>Promise<void>;invalidate:(names?:string[])=>void;dispose:()=>void}
