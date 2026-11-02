import type {Layout} from './layout.mjs'
export interface RoomPhoto {id:string;caption:string;created_at:string;view:'room'|'window';revision:number;width:number;height:number;image_url:string}
export interface RoomAction {id:string;actor:'user'|'assistant';object:'cup'|'book'|'cushion';from:Layout['cup'];to:Layout['cup'];revision:number;created_at:string}
export interface RoomSnapshot {revision:number;layout:Layout;locks:Record<'cup'|'book'|'cushion',boolean>;can_undo:boolean;photos:RoomPhoto[];actions:RoomAction[]}
export function readPhotoDraft():RoomPhoto|null {try{const p=JSON.parse(localStorage.getItem('fish.photoDraft')||'null');return p&&/^ph-[a-f0-9]{24}$/.test(p.id)&&typeof p.caption==='string'?{...p,image_url:'/api/room/photos/'+p.id+'/image'}:null}catch{return null}}
