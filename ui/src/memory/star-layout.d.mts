import type {MemoryStar,MemoryGraphData,MemoryEdge} from './types'
export function starPositions(nodes:MemoryStar[]):{id:string;position:number[]}[]
export function dateOffset(from:string,to:string):number
export function dateAt(from:string,offset:number):string
export function relatedStars(data:MemoryGraphData,id:string):{id:string;reasons:MemoryEdge['reasons']}[]
