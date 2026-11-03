export const places:Record<string,number[]>
export function route(from:string,to:string):string[]
export function roomIntent(state?:string,mode?:string,now?:Date):'walk'|'desk'|'sleep'|'idle'
export interface MotionState{position:number[];pose:string;direction:number;frame:number;time:number;goal:string;walking:boolean}
export function createRoomMotion():{update(dt:number):MotionState;state():MotionState;setIntent(value:string):void;snap(value:string):void;active(value:boolean):void}
