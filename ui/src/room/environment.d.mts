export interface RoomEnvironment {label:string; background:string; sky:string; ambient:number; sun:number; lamp:number; period:string; weather:string}
export function roomEnvironment(period?:string, weather?:string, now?:Date):RoomEnvironment;
export function roomActivity(state?:{state?:string;label?:string}):{animation:string;label:string};
export function roomFrustum(aspect:number,corners:{x:number;y:number}[]):{left:number;right:number;top:number;bottom:number};
