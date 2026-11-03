import * as T from 'three'
import {OrbitControls} from 'three/addons/controls/OrbitControls.js'
import {starPositions} from './star-layout.mjs'
import type {MemoryGraphData} from './types'

export function createStarScene(host:HTMLDivElement,options:{select:(id:string|null)=>void;lost:()=>void;restored:()=>void}) {
  const renderer=new T.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'})
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor(0,0)
  renderer.domElement.setAttribute('role','img');renderer.domElement.setAttribute('aria-label','三维记忆星图，拖动旋转；也可以用下方的记录列表选择星星')
  host.prepend(renderer.domElement)
  const scene=new T.Scene(),camera=new T.PerspectiveCamera(42,1,.1,150)
  const controls=new OrbitControls(camera,renderer.domElement)
  controls.enablePan=false;controls.enableDamping=true;controls.dampingFactor=.09;controls.minDistance=11;controls.maxDistance=85
  controls.autoRotateSpeed=.28;controls.enableZoom=false
  const geometry=new T.BufferGeometry(),linesGeometry=new T.BufferGeometry()
  const material=new T.ShaderMaterial({transparent:true,depthWrite:false,blending:T.AdditiveBlending,
    uniforms:{pixelRatio:{value:Math.min(devicePixelRatio,2)},selected:{value:-1}},
    vertexShader:`attribute vec3 starColor;attribute float starSize;attribute float starIndex;attribute float faded;
      varying vec3 color;varying float chosen;varying float dim;
      uniform float pixelRatio;uniform float selected;
      void main(){color=starColor;chosen=abs(starIndex-selected)<0.1?1.0:0.0;dim=faded;
        vec4 p=modelViewMatrix*vec4(position,1.0);gl_Position=projectionMatrix*p;
        gl_PointSize=clamp(starSize*pixelRatio*28.0/max(8.0,-p.z),8.0*pixelRatio,55.0*pixelRatio)*(1.0+chosen*0.3);}`,
    fragmentShader:`varying vec3 color;varying float chosen;varying float dim;
      void main(){float d=length(gl_PointCoord-vec2(0.5))*2.0;if(d>1.0)discard;
        float halo=exp(-d*d*8.0)*0.43;float core=exp(-d*d*75.0);
        float ring=chosen*exp(-pow((d-0.7)*22.0,2.0))*0.8;
        gl_FragColor=vec4(mix(color,vec3(1.0),core*0.85),clamp(halo+core+ring,0.0,1.0)*dim);}`,
  })
  const stars=new T.Points(geometry,material);stars.frustumCulled=false;scene.add(stars)
  const lineMaterial=new T.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.22,depthWrite:false})
  const lines=new T.LineSegments(linesGeometry,lineMaterial);lines.frustumCulled=false;scene.add(lines)
  let data:MemoryGraphData|null=null,positions:T.Vector3[]=[],index=new Map<string,number>(),selected:string|null=null
  let active=true,disposed=false,lost=false,rotating=false,frame=0,last=0,down:[number,number]|null=null
  const reduced=matchMedia('(prefers-reduced-motion: reduce)')
  function schedule(){if(!frame&&active&&!disposed&&!lost)frame=requestAnimationFrame(draw)}
  function draw(time:number){frame=0;if(!active||disposed||lost)return
    const dt=last?Math.min((time-last)/1000,.05):1/30;last=time
    controls.autoRotate=rotating&&!reduced.matches
    const moved=controls.update(dt);renderer.render(scene,camera)
    if(moved||controls.autoRotate)schedule()
  }
  controls.addEventListener('change',schedule)
  function fit(){const {clientWidth:w,clientHeight:h}=host;if(!w||!h)return
    camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h)
    schedule()
  }
  function reset(){const distance=Math.max(29,12/Math.tan(T.MathUtils.degToRad(21))/Math.min(1,camera.aspect));camera.position.set(0,distance*.15,distance);controls.target.set(0,0,0);controls.update();schedule()}
  function edges(){if(!data)return;const points:number[]=[],colors:number[]=[]
    for(const edge of data.edges){const a=index.get(edge.source),b=index.get(edge.target);if(a===undefined||b===undefined)continue
      points.push(...positions[a].toArray(),...positions[b].toArray())
      const highlight=selected===edge.source||selected===edge.target,c=new T.Color(highlight?'#ffd69b':edge.reasons.some(r=>r.kind==='alias')?'#ad9fc5':'#7692aa')
      colors.push(...c.toArray(),...c.toArray())
    }
    linesGeometry.dispose();linesGeometry.setAttribute('position',new T.Float32BufferAttribute(points,3));linesGeometry.setAttribute('color',new T.Float32BufferAttribute(colors,3));linesGeometry.computeBoundingSphere()
    lineMaterial.opacity=selected ? .7 : .22
  }
  function pick(event:PointerEvent){const rect=renderer.domElement.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;let nearest:string|null=null,distance=15
    for(let i=0;i<positions.length;i++){const p=positions[i].clone().project(camera);if(p.z< -1||p.z>1)continue
      const delta=Math.hypot((p.x+1)*rect.width/2-x,(1-p.y)*rect.height/2-y)
      if(delta<distance){nearest=data!.nodes[i].id;distance=delta}
    }return nearest
  }
  const onDown=(e:PointerEvent)=>{if(e.button===0)down=[e.clientX,e.clientY]}
  const onCancel=()=>{down=null}
  const onUp=(e:PointerEvent)=>{if(!down)return;const click=Math.hypot(e.clientX-down[0],e.clientY-down[1])<5;down=null;if(click)options.select(pick(e))}
  const onMove=(e:PointerEvent)=>{if(!e.buttons)renderer.domElement.style.cursor=pick(e)?'pointer':'grab'}
  const onWheel=(e:WheelEvent)=>{controls.enableZoom=e.ctrlKey||e.metaKey}
  const onLost=(e:Event)=>{e.preventDefault();lost=true;cancelAnimationFrame(frame);frame=0;options.lost()}
  const onRestored=()=>{lost=false;options.restored();schedule()}
  const onMotion=()=>schedule()
  renderer.domElement.addEventListener('pointercancel',onCancel);renderer.domElement.addEventListener('pointerdown',onDown);renderer.domElement.addEventListener('pointerup',onUp);renderer.domElement.addEventListener('pointermove',onMove)
  renderer.domElement.addEventListener('wheel',onWheel,true);renderer.domElement.addEventListener('webglcontextlost',onLost);renderer.domElement.addEventListener('webglcontextrestored',onRestored)
  reduced.addEventListener('change',onMotion)
  const observer=new ResizeObserver(fit);observer.observe(host);fit();reset()
  return {
    data(value:MemoryGraphData){data=value;positions=starPositions(value.nodes).map(p=>new T.Vector3(...p.position as [number,number,number]));index=new Map(value.nodes.map((node,i)=>[node.id,i]))
      const colors=value.nodes.flatMap(n=>new T.Color(n.pinned?'#ffbfba':n.kind==='impression'?'#b3daf9':'#ffe4a8').toArray())
      geometry.dispose();geometry.setAttribute('position',new T.Float32BufferAttribute(positions.flatMap(p=>p.toArray()),3));geometry.setAttribute('starColor',new T.Float32BufferAttribute(colors,3))
      geometry.setAttribute('starSize',new T.Float32BufferAttribute(value.nodes.map(n=>n.pinned?33:25),1));geometry.setAttribute('starIndex',new T.Float32BufferAttribute(value.nodes.map((_,i)=>i),1))
      geometry.setAttribute('faded',new T.Float32BufferAttribute(value.nodes.map(n=>n.effective_status==='active'?1:.45),1));geometry.computeBoundingSphere();edges();schedule()
    },
    select(id:string|null){selected=id;material.uniforms.selected.value=id?index.get(id)??-1:-1;edges();schedule()},
    active(value:boolean){active=value;last=0;if(!value){cancelAnimationFrame(frame);frame=0;down=null}else{fit();schedule()}},
    rotate(value:boolean){rotating=value;schedule()},reset,
    zoom(delta:number){camera.position.sub(controls.target).multiplyScalar(delta > 0 ? .84 : 1.19).clampLength(controls.minDistance,controls.maxDistance).add(controls.target);controls.update();schedule()},
    dispose(){disposed=true;cancelAnimationFrame(frame);observer.disconnect();controls.removeEventListener('change',schedule);controls.dispose();reduced.removeEventListener('change',onMotion)
      renderer.domElement.removeEventListener('pointercancel',onCancel);renderer.domElement.removeEventListener('pointerdown',onDown);renderer.domElement.removeEventListener('pointerup',onUp);renderer.domElement.removeEventListener('pointermove',onMove);renderer.domElement.removeEventListener('wheel',onWheel,true)
      renderer.domElement.removeEventListener('webglcontextlost',onLost);renderer.domElement.removeEventListener('webglcontextrestored',onRestored)
      geometry.dispose();linesGeometry.dispose();material.dispose();lineMaterial.dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()
    },
  }
}
export type StarScene=ReturnType<typeof createStarScene>
