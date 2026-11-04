// Per-resource refresh owns deduplication and late-response ordering. No model calls.
export const refreshTTL={overview:60_000,sessions:60_000,inbox:15_000,documents:120_000,stickers:120_000,curiosity:60_000};
export function createResourceRefresh({load,apply,now=Date.now,ttl=refreshTTL}){
  const entries=new Map();let stopped=false;
  function entry(name){if(!entries.has(name))entries.set(name,{generation:0,value:undefined,loaded:false,updated:0,pending:null});return entries.get(name);}
  function invalidate(names=[...entries.keys()]){for(const name of names){const e=entry(name);e.generation++;e.loaded=false;}}
  async function get(name,{force=false}={}){
    if(stopped)return;
    const e=entry(name);if(force)invalidate([name]);
    if(e.pending?.generation===e.generation)return e.pending.promise;
    if(e.loaded&&now()-e.updated<(ttl[name]??60_000))return e.value;
    const generation=e.generation;
    const promise=Promise.resolve().then(()=>load(name)).then(value=>{
      if(!stopped&&generation===e.generation){e.value=value;e.loaded=true;e.updated=now();apply(name,value);}
      return value;
    }).finally(()=>{if(e.pending?.promise===promise)e.pending=null;});
    e.pending={generation,promise};return promise;
  }
  async function refresh(names,options){const results=await Promise.allSettled([...new Set(names)].map(n=>get(n,options)));const failed=results.find(r=>r.status==='rejected');if(failed)throw failed.reason;}
  return {get,refresh,invalidate,dispose(){stopped=true;invalidate();}};
}
