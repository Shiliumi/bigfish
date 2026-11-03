// Stable, local positions: geometry has no bearing on memory strength or relevance.
function random(seed){let n=2166136261;for(const c of seed)n=Math.imul(n^c.charCodeAt(0),16777619);return()=>{n+=0x6D2B79F5;let t=n;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;};}
function sphere(next,radius){const z=next()*2-1,a=next()*Math.PI*2,s=Math.sqrt(1-z*z);return [Math.cos(a)*s*radius,z*radius,Math.sin(a)*s*radius];}
export function starPositions(nodes){return nodes.map(node=>{const center=sphere(random(node.group),3.5),next=random(node.id),offset=sphere(next,2.5+next()*4.5);return {id:node.id,position:center.map((value,i)=>value+offset[i])};});}
export function dateOffset(from,to){return Math.round((Date.parse(to+'T00:00:00Z')-Date.parse(from+'T00:00:00Z'))/86400000);}
export function dateAt(from,offset){return new Date(Date.parse(from+'T00:00:00Z')+offset*86400000).toISOString().slice(0,10);}
export function relatedStars(data,id){return data.edges.filter(edge=>edge.source===id||edge.target===id).map(edge=>({id:edge.source===id?edge.target:edge.source,reasons:edge.reasons}));}
