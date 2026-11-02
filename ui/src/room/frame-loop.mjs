// A single cancellable clock per mounted room. Suspension drops elapsed background time.
export function createFrameLoop(draw, {request=requestAnimationFrame, cancel=cancelAnimationFrame, now=()=>performance.now()} = {}) {
  let active=false, disposed=false, handle=null, previous=0;
  const tick=time=>{
    handle=null;if(!active||disposed)return;
    if(time-previous>=1000/30){const dt=Math.min((time-previous)/1000,.1);previous=time;draw(dt,time);}
    if(active&&!disposed)handle=request(tick);
  };
  return {
    active(value){if(disposed||active===value)return;active=value;if(handle!==null){cancel(handle);handle=null;}if(active){previous=now();handle=request(tick);}},
    dispose(){active=false;disposed=true;if(handle!==null)cancel(handle);handle=null;},
  };
}
