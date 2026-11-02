export const surfaces={
  floor:{label:'地面',y:.05,bounds:[-1.35,1.8,1.15,2.9],obstacles:[[.1,.9,.75,1.55]]},
  desk:{label:'书桌',y:1.185,bounds:[-.175,2.475,-2.76,-1.9],obstacles:[[.38,1.66,-2.6,-2.38],[.65,1.4,-2.115,-1.845]]},
  sill:{label:'窗台',y:.89,bounds:[-.98,2.43,-3.13,-2.72],obstacles:[]},
  nightstand:{label:'床头柜',y:.78,bounds:[-1.28,-.42,-1.83,-.97],obstacles:[[-1.25,-.95,-1.79,-1.49]]},
  bed:{label:'床上',y:.94,bounds:[-3.12,-1.48,.15,1.51],obstacles:[]},
};
export const objects={
  cup:{label:'杯子',width:.34,depth:.25,surfaces:['desk','sill','nightstand'],presets:{desk:[.2,-2.13],sill:[-.65,-2.925],nightstand:[-.65,-1.17]}},
  book:{label:'书',width:.41,depth:.55,surfaces:['floor','desk','nightstand','bed'],presets:{floor:[-.91,2.28],desk:[2.1,-2.35],nightstand:[-.72,-1.28],bed:[-2.28,.44]}},
  cushion:{label:'抱枕',width:1.064,depth:.684,surfaces:['floor','bed'],presets:{floor:[-.75,1.58],bed:[-2.28,1.12]}},
};
export function defaultLayout(){return {cup:{surface:'desk',x:.2,z:-2.13,rotation:0},book:{surface:'floor',x:-.91,z:2.28,rotation:0},cushion:{surface:'floor',x:-.75,z:1.58,rotation:0}};}
const overlap=(a,b)=>a[0]<b[1]-.001&&a[1]>b[0]+.001&&a[2]<b[3]-.001&&a[3]>b[2]+.001;
export function footprint(id,p){const item=objects[id],turned=p.rotation%180!==0,w=turned?item.depth:item.width,d=turned?item.width:item.depth;return [p.x-w/2,p.x+w/2,p.z-d/2,p.z+d/2];}
export function validateLayout(layout){
  if(!layout||typeof layout!=='object'||Array.isArray(layout)||Object.keys(layout).sort().join()!=='book,cup,cushion')throw Error('布置内容不完整。');
  const result={};
  for(const [id,item]of Object.entries(objects)){
    const p=layout[id];if(!p||Object.keys(p).sort().join()!=='rotation,surface,x,z'||!item.surfaces.includes(p.surface)||![p.x,p.z].every(Number.isFinite)||![0,90,180,270].includes(p.rotation))throw Error('物品位置格式不正确。');
    const rect=footprint(id,p),surface=surfaces[p.surface],b=surface.bounds;
    if(rect[0]<b[0]+.01||rect[1]>b[1]-.01||rect[2]<b[2]+.01||rect[3]>b[3]-.01||surface.obstacles.some(o=>overlap(rect,o)))throw Error(item.label+'在这里放不下，换个位置试试。');
    for(const [other,q]of Object.entries(result))if(q.surface===p.surface&&overlap(rect,footprint(other,q)))throw Error(item.label+'会碰到'+objects[other].label+'。');
    result[id]={surface:p.surface,x:Math.round(p.x*1000)/1000,z:Math.round(p.z*1000)/1000,rotation:p.rotation};
  }
  return result;
}
export function placeObject(layout,id,placement){if(!objects[id])throw Error('这件家具暂时不能移动。');return validateLayout({...layout,[id]:placement});}
export function layoutCaption(layout){return Object.entries(objects).map(([id,o])=>o.label+'在'+surfaces[layout[id].surface].label).join('，');}
