export type ObjectId='cup'|'book'|'cushion';
export interface Placement {surface:string;x:number;z:number;rotation:number}
export type Layout=Record<ObjectId,Placement>;
export const surfaces:Record<string,{label:string;y:number;bounds:number[];obstacles:number[][]}>;
export const objects:Record<ObjectId,{label:string;width:number;depth:number;surfaces:string[];presets:Record<string,number[]>}>;
export function defaultLayout():Layout;
export function validateLayout(layout:unknown):Layout;
export function placeObject(layout:Layout,id:string,placement:Placement):Layout;
export function footprint(id:ObjectId,p:Placement):number[];
export function layoutCaption(layout:Layout):string;
