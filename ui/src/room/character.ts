import * as T from 'three'
import {createRoomMotion} from './life-motion.mjs'

export function roomCharacter(scene:T.Scene){
  let disposed=false,isActive=true
  const motion=createRoomMotion(),loader=new T.TextureLoader(),textures:T.Texture[]=[],reduced=matchMedia('(prefers-reduced-motion: reduce)')
  const load=(url:string)=>loader.loadAsync(url).then(t=>{t.colorSpace=T.SRGBColorSpace;t.minFilter=T.LinearFilter;t.magFilter=T.LinearFilter;if(disposed)t.dispose();else textures.push(t);return t})
  const material=new T.SpriteMaterial({transparent:true,alphaTest:.12,depthTest:true,depthWrite:false,toneMapped:false})
  const sprite=new T.Sprite(material);sprite.center.set(.5,.07);sprite.name='room-character';scene.add(sprite)
  const ready=Promise.all([load('/pet/idle-poster.png'),load('/room/walk-atlas.png'),load('/room/sitting.png'),load('/room/sleeping.png')])
  let maps:T.Texture[]|null=null,intent='idle',greeting=0
  const video=document.createElement('video');video.muted=true;video.loop=true;video.playsInline=true;video.preload='auto';video.src='/pet/idle.mov'
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=720;const context=canvas.getContext('2d')!,movie=new T.CanvasTexture(canvas);movie.colorSpace=T.SRGBColorSpace;textures.push(movie)
  const masks=new Map<T.Texture,ImageData>()
  ready.then(value=>{if(disposed)return;maps=value;maps[1].repeat.set(.25,1);for(const index of [2,3]){maps[index].repeat.x=-1;maps[index].offset.x=1}apply(0)}).catch(()=>{})
  function apply(dt:number){if(greeting>0){greeting-=dt;if(greeting<=0){video.src='/pet/idle.mov';motion.active(isActive)}}const state=motion.update(dt);if(!maps)return state
    const pose=greeting>0?'idle':state.pose,index=pose==='walk'?1:pose==='sit'?2:pose==='sleep'?3:0
    let map=maps[index];if(pose==='idle'&&isActive&&!reduced.matches){if(video.paused)void video.play().catch(()=>{});if(video.readyState>=2){try{context.clearRect(0,0,640,720);context.drawImage(video,0,0,640,720);movie.needsUpdate=true;map=movie}catch{}}}else if(!video.paused)video.pause()
    if(material.map!==map){material.map=map;material.needsUpdate=true}
    const width=pose==='sleep'?1.67:pose==='sit'?2.2:pose==='walk'?1.36:1.7,height=pose==='sleep'?1.11:pose==='sit'?2.2:pose==='walk'?2.04:1.9125
    sprite.scale.set(width,height*(1+(reduced.matches?0:Math.sin(state.time*(pose==='sleep'?1.4:2.1))*.004)),1)
    // Mirror the gait along its own local horizontal axis; never rotate a standing pose into sleep.
    if(pose==='walk'&&state.direction<0){maps[1].repeat.x=-.25;maps[1].offset.x=(state.frame+1)*.25}else {maps[1].repeat.x=.25;maps[1].offset.x=state.frame*.25}
    sprite.position.set(...state.position as [number,number,number]);material.opacity=1
    return state
  }
  return {ready:ready.then(()=>{}),sprite,update:apply,state:motion.state,
    hit(uv:T.Vector2){const texture=material.map;if(!texture)return false;if(texture===movie)return true;let mask=masks.get(texture);if(!mask){const canvas=document.createElement('canvas'),image=texture.image as HTMLImageElement;canvas.width=image.width;canvas.height=image.height;const context=canvas.getContext('2d')!;context.drawImage(image,0,0);mask=context.getImageData(0,0,canvas.width,canvas.height);masks.set(texture,mask)}const p=uv.clone();texture.updateMatrix();texture.transformUv(p);const x=Math.min(mask.width-1,Math.max(0,Math.floor(p.x*mask.width))),y=Math.min(mask.height-1,Math.max(0,Math.floor(p.y*mask.height)));return mask.data[(y*mask.width+x)*4+3]>64},
    intent(value:string,snap=false){intent=value;if(greeting>0){greeting=0;video.src='/pet/idle.mov';motion.active(isActive)};if(snap||reduced.matches)motion.snap(value);else motion.setIntent(value);apply(0)},
    greet(){if(greeting>0||['sit','sleep'].includes(motion.state().pose))return;greeting=3;motion.active(false);video.src='/pet/greeting.mov';if(isActive)void video.play().catch(()=>{})},
    reduced(){if(reduced.matches){motion.snap(intent);video.pause()}},
    active(value:boolean){isActive=value;motion.active(value&&greeting<=0);if(!value)video.pause()},
    color(value:string){material.color.set(value)},
    dispose(){disposed=true;video.pause();video.removeAttribute('src');video.load();scene.remove(sprite);material.dispose();textures.forEach(t=>t.dispose());masks.clear()},
  }
}
