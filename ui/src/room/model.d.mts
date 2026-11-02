import type {RoomSnapshot} from './types'
export type Atmosphere={period:'auto'|'day'|'dusk'|'night';weather:'clear'|'rain'|'snow';lamp:boolean}
export const roomItems:Record<string,{name:string;area?:string;details?:string}>
export function validateAtmosphere(value:unknown):Atmosphere
export function describeRoom(snapshot:RoomSnapshot,now?:Date):Record<string,unknown>
