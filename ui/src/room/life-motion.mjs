// Navigation is explicit: floor routes avoid the bed, desk and tall plant.
export const places={rug:[.5,.08,1.15],center:[.35,.08,.2],deskDoor:[.5,.08,-.65],desk:[1.15,.17,-1.08],bedDoor:[-1.08,.08,.65],bedStep:[-1.22,.98,.65],bed:[-2.22,.96,.3],shelf:[-1.62,.08,2.18],window:[2.05,.08,.8]};
const connections=[['rug','center'],['center','deskDoor'],['deskDoor','desk'],['center','bedDoor'],['bedDoor','bedStep'],['bedStep','bed'],['rug','shelf'],['rug','window']];
export function roomIntent(state='idle',mode='auto',now=new Date()){
  if(['walk','desk','sleep'].includes(mode))return mode;
  if(['surfing','working'].includes(state))return 'desk';
  if(['thinking','letter'].includes(state))return 'idle';
  const hour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',hourCycle:'h23'}).format(now));
  return hour>=1&&hour<7?'sleep':'walk';
}
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
export function route(from,to){
  const queue=[[from]],seen=new Set([from]);while(queue.length){const current=queue.shift(),last=current.at(-1);if(last===to)return current;
    for(const edge of connections)if(edge.includes(last)){const next=edge.find(n=>n!==last);if(!seen.has(next)){seen.add(next);queue.push([...current,next]);}}
  }throw Error('房间路线不存在');
}
export function createRoomMotion(){
  let position=[...places.rug],goal='rug',intent='idle',path=[],pose='idle',elapsed=0,rest=0,direction=1,roam=0,enabled=true;
  const nearest=()=>Object.keys(places).reduce((a,b)=>distance(position,places[a])<distance(position,places[b])?a:b);
  function travel(target){goal=target;const start=nearest();path=[...route(start,target)];if(distance(position,places[start])<.01)path.shift();pose=path.length?'walk':target==='bed'?'sleep':target==='desk'?'sit':'idle';rest=0;}
  function update(dt){if(!enabled)return state();elapsed+=Math.min(.1,Math.max(0,dt));
    if(path.length){const target=places[path[0]],length=distance(position,target),step=.8*Math.min(.1,Math.max(0,dt));if(length<=step+.001){position=[...target];path.shift();if(!path.length)pose=goal==='bed'?'sleep':goal==='desk'?'sit':'idle';}
      else{const dx=target[0]-position[0],dz=target[2]-position[2];if(Math.abs(dx)+Math.abs(dz)>.02)direction=dx-dz>=0?1:-1;position=position.map((v,i)=>v+(target[i]-v)*step/length);}}
    else if(intent==='walk'){rest+=dt;if(rest>=24){const choices=['window','rug','shelf','rug'];travel(choices[roam++%choices.length]);}}
    return state();
  }
  function state(){return {position:[...position],pose,direction,frame:Math.floor(elapsed*7)%4,time:elapsed,goal,walking:path.length>0};}
  return {update,state,setIntent(value){if(intent===value)return;intent=value;travel(value==='sleep'?'bed':value==='desk'?'desk':value==='walk'?['window','shelf'][roam++%2]:'rug');},
    snap(value){intent=value;goal=value==='sleep'?'bed':value==='desk'?'desk':'rug';position=[...places[goal]];path=[];pose=goal==='bed'?'sleep':goal==='desk'?'sit':'idle';},active(value){enabled=value}};
}
