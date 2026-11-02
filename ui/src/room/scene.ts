import * as T from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import type { RoomEnvironment } from './environment.mjs'
import { createFrameLoop } from './frame-loop.mjs'
import { roomFrustum } from './environment.mjs'
import { weatherParticles, precipitationPosition } from './precipitation.mjs'

type Options = {select:(id:string)=>void; project:(x:number,y:number,size:number)=>void; lost:()=>void; restored:()=>void}

export function createRoom(host:HTMLDivElement, options:Options) {
  const scene = new T.Scene()
  const renderer = new T.WebGLRenderer({antialias:true, alpha:false, powerPreference:'low-power'})
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.shadowMap.enabled = true
  renderer.shadowMap.type = T.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false
  renderer.outputColorSpace = T.SRGBColorSpace; renderer.toneMapping = T.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05
  renderer.domElement.setAttribute('aria-label','三维小屋，可拖动转动视角，点击家具查看')
  renderer.domElement.setAttribute('role','img'); host.prepend(renderer.domElement)
  const camera = new T.OrthographicCamera(-6,6,5,-5,.1,70)
  camera.position.set(10,8.8,12)
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0,1.5,0); controls.enablePan = false; controls.enableDamping = true; controls.dampingFactor = .09
  controls.minPolarAngle = .65; controls.maxPolarAngle = 1.14
  controls.minAzimuthAngle = .32; controls.maxAzimuthAngle = 1.13
  controls.minZoom = .85; controls.maxZoom = 1.35; controls.update(); controls.saveState()
  const materials = new Set<T.Material>(), geometries = new Set<T.BufferGeometry>(), textures = new Set<T.Texture>()
  const targets:T.Object3D[] = []
  const mat = (color:string, extra:T.MeshStandardMaterialParameters = {}) => {
    const m = new T.MeshStandardMaterial({color, roughness:.85, ...extra}); materials.add(m); return m
  }
  const cream = mat('#eee8db'), white = mat('#faf7f0'), wood = mat('#b99573'), lightWood = mat('#dbc7a7'), blue = mat('#789da9'), navy = mat('#42627c'), green = mat('#6e9280'), gold = mat('#bca47a',{metalness:.35}), dark = mat('#3d5056')
  function mesh(parent:T.Object3D, geometry:T.BufferGeometry, material:T.Material, x:number,y:number,z:number) {
    geometries.add(geometry); const o = new T.Mesh(geometry, material); o.position.set(x,y,z)
    o.castShadow = true; o.receiveShadow = true; parent.add(o); return o
  }
  function box(parent:T.Object3D,w:number,h:number,d:number,x:number,y:number,z:number,material:T.Material,r=.035) {
    return mesh(parent,new RoundedBoxGeometry(w,h,d,2,Math.min(r,w/3,h/3,d/3)),material,x,y,z)
  }
  const sphere = (parent:T.Object3D,r:number,x:number,y:number,z:number,m:T.Material) => mesh(parent,new T.SphereGeometry(r,20,12),m,x,y,z)
  const cylinder = (parent:T.Object3D,top:number,bottom:number,h:number,x:number,y:number,z:number,m:T.Material) => mesh(parent,new T.CylinderGeometry(top,bottom,h,28),m,x,y,z)
  function group(id:string) { const g = new T.Group(); g.userData.slot=id; scene.add(g); targets.push(g); return g }

  // Open dollhouse walls; the window is a real opening rather than an overlay on a wall.
  box(scene,7.3,.28,6.3,0,-.19,0,mat('#c4b5a1'),.08)
  for(let i=0;i<13;i++) box(scene,.535,.07,6.05,-3.24+i*.54,-.015,0,mat(i%3===0?'#d2baa0':i%3===1?'#d8c3aa':'#ddcbb4'),.008)
  box(scene,.16,3.6,6.12,-3.57,1.75,0,mat('#dce3de'))
  const back = mat('#e4e9e1')
  box(scene,2.55,3.6,.16,-2.27,1.75,-3.08,back)
  box(scene,1.05,3.6,.16,3.06,1.75,-3.08,back)
  box(scene,3.5,.87,.16,.73,.385,-3.08,back)
  box(scene,3.5,.46,.16,.73,3.32,-3.08,back)
  box(scene,.11,.15,6,-3.45,.1,0,white); box(scene,7,.15,.11,0,.1,-2.96,white)
  box(scene,.22,.12,6.3,-3.57,3.59,0,white); box(scene,7.3,.12,.22,0,3.59,-3.08,white)

  const windowGroup = group('window')
  const skyCanvas = document.createElement('canvas'); skyCanvas.width=768; skyCanvas.height=512
  const skyTexture = new T.CanvasTexture(skyCanvas); skyTexture.colorSpace=T.SRGBColorSpace; textures.add(skyTexture)
  const skyMaterial = new T.MeshBasicMaterial({map:skyTexture}); materials.add(skyMaterial)
  mesh(windowGroup,new T.PlaneGeometry(3.48,2.12),skyMaterial,.73,1.94,-3.14).castShadow=false
  for(const x of [-1.03,.73,2.49]) box(windowGroup,.075,2.28,.12,x,1.95,-2.97,white,.012)
  for(const y of [.82,1.95,3.08]) box(windowGroup,3.62,.075,.13,.73,y,-2.97,white,.01)
  box(windowGroup,3.8,.11,.38,.73,.83,-2.91,lightWood)
  const curtain = mat('#d3d9cd')
  for(const side of [-1.25,2.72]) for(let i=0;i<5;i++) {
    const fold=cylinder(windowGroup,.055,.075,2.38,side+i*.042,1.91,-2.81,curtain); fold.scale.z=1.4
  }
  cylinder(windowGroup,.025,.025,4.2,.73,3.2,-2.79,gold).rotation.z=Math.PI/2

  const bed=group('bed')
  box(bed,1.85,.38,2.95,-2.3,.35,.15,lightWood,.08)
  box(bed,1.85,1.1,.16,-2.3,.88,-1.4,wood,.07)
  box(bed,1.72,.32,2.77,-2.3,.65,.15,white,.11)
  box(bed,1.75,.14,1.95,-2.3,.86,.6,blue,.06)
  box(bed,1.77,.1,.42,-2.3,.95,.03,mat('#9fb8be'),.045)
  const pillow=box(bed,1.18,.23,.58,-2.3,.91,-.85,cream,.11); pillow.rotation.y=-.045
  box(bed,1.78,.12,.26,-2.3,.92,1.4,navy,.03)
  // Whale plush on the bed, built from soft geometry.
  const plush=sphere(bed,.32,-2.3,1.22,-.66,blue); plush.scale.set(1.1,.82,.85)
  sphere(bed,.034,-2.16,1.25,-.43,dark); sphere(bed,.034,-2.46,1.25,-.43,dark)
  const tail=sphere(bed,.16,-2.64,1.25,-.77,blue); tail.scale.set(1.6,.3,1)

  const bedside=group('lamp')
  box(bedside,.67,.75,.65,-.98,.4,-1.38,white,.06)
  for(const y of [.27,.57]) { box(bedside,.57,.25,.04,-.98,y,-1.04,cream); sphere(bedside,.027,-.98,y,-1.005,gold) }
  cylinder(bedside,.17,.17,.035,-.98,.81,-1.38,gold)
  cylinder(bedside,.025,.025,.36,-.98,1,-1.38,gold)
  cylinder(bedside,.19,.28,.31,-.98,1.3,-1.38,mat('#fff0ce',{emissive:'#ffdca3',emissiveIntensity:.22}))

  const desk=group('desk')
  box(desk,2.65,.13,.86,1.15,1.12,-2.33,lightWood,.06)
  for(const x of [.02,2.28]) for(const z of [-2.65,-2.02]) box(desk,.09,1.04,.09,x,.53,z,wood)
  box(desk,.54,.88,.66,2.04,.52,-2.33,cream)
  for(let i=0;i<3;i++) { box(desk,.49,.23,.025,2.04,.25+i*.27,-1.99,white); box(desk,.14,.025,.035,2.04,.29+i*.27,-1.964,gold) }
  cylinder(desk,.21,.21,.035,1.02,1.22,-2.4,dark)
  box(desk,.06,.24,.06,1.02,1.33,-2.49,dark)
  box(desk,1.24,.77,.08,1.02,1.77,-2.49,dark,.055)
  const screenCanvas=document.createElement('canvas'); screenCanvas.width=512; screenCanvas.height=320
  const sc=screenCanvas.getContext('2d')!; const sg=sc.createLinearGradient(0,0,0,320); sg.addColorStop(0,'#b8dce8'); sg.addColorStop(1,'#709aad'); sc.fillStyle=sg;sc.fillRect(0,0,512,320)
  sc.fillStyle='#f6edd1';sc.beginPath();sc.arc(380,70,25,0,Math.PI*2);sc.fill()
  for(let j=0;j<3;j++) {sc.fillStyle=['#789fae','#5e889c','#466d85'][j];sc.beginPath();sc.moveTo(0,200+j*32);for(let x=0;x<=512;x+=8)sc.lineTo(x,200+j*32+Math.sin(x*.018+j)*13);sc.lineTo(512,320);sc.lineTo(0,320);sc.fill()}
  const screenTexture=new T.CanvasTexture(screenCanvas);screenTexture.colorSpace=T.SRGBColorSpace;textures.add(screenTexture)
  const sm=new T.MeshBasicMaterial({map:screenTexture});materials.add(sm);mesh(desk,new T.PlaneGeometry(1.12,.65),sm,1.02,1.77,-2.444)
  box(desk,.69,.035,.23,1.02,1.21,-1.98,white,.025)
  for(let i=0;i<8;i++) box(desk,.05,.008,.13,.77+i*.07,1.231,-1.98,cream,.002)
  const mug=group('cup');cylinder(mug,.105,.08,.22,.15,1.29,-2.13,white)
  cylinder(mug,.08,.08,.006,.15,1.404,-2.13,mat('#846b56'))
  const handle=mesh(mug,new T.TorusGeometry(.072,.018,8,20),white,.28,1.31,-2.13)
  handle.rotation.y=.2

  const chair=group('chair')
  cylinder(chair,.035,.035,.5,1.15,.35,-1.08,dark)
  box(chair,.65,.13,.62,1.15,.64,-1.08,blue,.07)
  box(chair,.65,.72,.09,1.15,1.04,-.79,blue,.07)
  for(let i=0;i<5;i++) {const a=i*Math.PI*2/5;const leg=box(chair,.045,.055,.43,1.15+Math.sin(a)*.17,.12,-1.08+Math.cos(a)*.17,dark);leg.rotation.y=a;sphere(chair,.06,1.15+Math.sin(a)*.36,.085,-1.08+Math.cos(a)*.36,dark)}

  const shelf=group('shelf')
  box(shelf,.48,2.45,.95,-3.25,1.28,1.53,lightWood)
  for(let i=0;i<3;i++) box(shelf,.05,.64,.79,-2.99,.53+i*.74,1.53,cream)
  const bookColors=['#708a95','#bd947f','#d6bf8f','#a1aaa0','#6d7f94']
  for(let row=0;row<3;row++) for(let i=0;i<5;i++) box(shelf,.25,.36+(i%3)*.05,.09,-2.94,.47+row*.74,1.2+i*.14,mat(bookColors[i]))
  for(const y of [.1,.82,1.56,2.49]) box(shelf,.58,.07,1.03,-3.2,y,1.53,wood)

  function plant(x:number,z:number,scale=1) {
    const plant=group('plant');plant.position.set(x,0,z);plant.scale.setScalar(scale)
    cylinder(plant,.25,.17,.48,0,.25,0,white)
    cylinder(plant,.225,.225,.015,0,.5,0,mat('#675e4e'))
    cylinder(plant,.027,.035,1,0,.91,0,wood)
    for(let i=0;i<8;i++){const angle=i*2.4;const leaf=sphere(plant,.27,Math.sin(angle)*.22,.8+i*.085,Math.cos(angle)*.19,green);leaf.scale.set(1,.35,.65);leaf.rotation.set(.3,angle,.3)}
  }
  plant(2.75,-.1,1.12)
  // Small shelf plant, photographs and paper details make the room feel inhabited.
  box(scene,.55,.06,1.5,-3.23,2.5,-.55,wood)
  cylinder(scene,.14,.1,.23,-3.1,2.64,-.8,cream)
  for(let i=0;i<5;i++) {const leaf=sphere(scene,.13,-3.1+Math.sin(i*2)*.07,2.84+i*.035,-.8+Math.cos(i*2)*.09,green);leaf.scale.y=.7}
  const picture=group('picture');box(picture,.07,.68,.58,-3.44,2.38,-1.98,wood)
  box(picture,.075,.55,.45,-3.39,2.38,-1.98,white)
  sphere(picture,.14,-3.34,2.42,-1.98,blue).scale.set(.1,1,1)

  const rug=group('rug');const rugMat=mat('#c8d8d6')
  const rugMesh=cylinder(rug,1.48,1.48,.025,.45,.045,.91,rugMat);rugMesh.scale.z=.83
  const ring=mesh(rug,new T.TorusGeometry(1.34,.018,6,96),white,.45,.065,.91);ring.rotation.x=Math.PI/2;ring.scale.y=.83
  const whale=sphere(rug,.57,.35,.075,.88,mat('#709aa6'));whale.scale.set(1,.025,.58)
  const fin=sphere(rug,.23,.94,.075,.89,blue);fin.scale.set(1,.05,.6);fin.rotation.y=.65
  sphere(rug,.027,.07,.089,1.02,white).scale.y=.1
  const cushion=group('cushion');const pillow2=sphere(cushion,.38,-.75,.15,1.58,navy);pillow2.scale.set(1.4,.35,.9)
  const book=group('book');box(book,.41,.07,.55,-.91,.085,2.15,mat('#b98b78'));box(book,.36,.045,.5,-.91,.14,2.15,white);box(book,.41,.025,.55,-.91,.18,2.15,mat('#bd9c84'))

  const ambient=new T.HemisphereLight('#f5f7f2','#c5b096',2);scene.add(ambient)
  const sun=new T.DirectionalLight('#fff2d8',3);sun.position.set(2.5,7,4);sun.castShadow=true
  sun.shadow.mapSize.set(1024,1024);Object.assign(sun.shadow.camera,{left:-5,right:5,top:5,bottom:-5,near:.5,far:22});sun.shadow.normalBias=.035;sun.shadow.bias=-.0002;sun.shadow.radius=3;scene.add(sun)
  const lamp=new T.PointLight('#ffc782',2,5,2);lamp.position.set(-.98,1.25,-1.36);scene.add(lamp)
  const fill=new T.DirectionalLight('#d0e9fa',1);fill.position.set(-2,4,-4);scene.add(fill)
  const ground=mesh(scene,new T.PlaneGeometry(200,200),mat('#eef3f2'),0,-.35,0);ground.rotation.x=-Math.PI/2;ground.castShadow=false

  const particles=new T.Group();scene.add(particles)
  const seeds=weatherParticles(),positions=new Float32Array(seeds.length*3)
  for(let i=0;i<seeds.length;i++){const p=precipitationPosition(seeds[i],0,'snow');positions.set([p.x,p.y,p.z],i*3)}
  const pg=new T.BufferGeometry();pg.setAttribute('position',new T.BufferAttribute(positions,3));geometries.add(pg)
  // PointsMaterial sizes are screen pixels with an orthographic camera, not world units.
  const snowCanvas=document.createElement('canvas');snowCanvas.width=32;snowCanvas.height=32
  const snowContext=snowCanvas.getContext('2d')!,flake=snowContext.createRadialGradient(16,16,0,16,16,16)
  flake.addColorStop(0,'#ffffff');flake.addColorStop(.55,'#fffffff2');flake.addColorStop(1,'#ffffff00')
  snowContext.fillStyle=flake;snowContext.fillRect(0,0,32,32)
  const snowTexture=new T.CanvasTexture(snowCanvas);snowTexture.colorSpace=T.SRGBColorSpace;textures.add(snowTexture)
  const pm=new T.PointsMaterial({color:'#ffffff',size:3.6,sizeAttenuation:false,map:snowTexture,transparent:true,opacity:.95,alphaTest:.04,depthWrite:false,toneMapped:false});materials.add(pm)
  const points=new T.Points(pg,pm);points.frustumCulled=false;particles.add(points)
  const rainPositions=new Float32Array(72*6), rainGeometry=new T.BufferGeometry()
  for(let i=0;i<72;i++)rainPositions.set([positions[i*3],positions[i*3+1],-3.1,positions[i*3]-.025,positions[i*3+1]-.13,-3.1],i*6)
  rainGeometry.setAttribute('position',new T.BufferAttribute(rainPositions,3));geometries.add(rainGeometry)
  const rainMaterial=new T.LineBasicMaterial({color:'#d8e7ed',transparent:true,opacity:.55});materials.add(rainMaterial)
  const rain=new T.LineSegments(rainGeometry,rainMaterial);rain.frustumCulled=false;particles.add(rain)
  let environment:RoomEnvironment, lampOn=true, active=false, disposed=false, lost=false, weatherTime=0
  let width=1,height=1
  const corners:T.Vector3[]=[]
  for(const x of [-3.8,3.8])for(const y of [-.5,3.8])for(const z of [-3.3,3.3])corners.push(new T.Vector3(x,y,z))
  function fit(){
    camera.updateMatrixWorld();Object.assign(camera,roomFrustum(width/height,corners.map(p=>p.clone().applyMatrix4(camera.matrixWorldInverse))))
    camera.updateProjectionMatrix()
  }
  function sky(env:RoomEnvironment) {
    const c=skyCanvas.getContext('2d')!, night=env.period==='night';const grad=c.createLinearGradient(0,0,0,512)
    const snow=env.weather==='snow'
    grad.addColorStop(0,snow?(night?'#405674':'#91aabf'):env.sky);grad.addColorStop(1,night?'#718293':snow?'#c5d5db':env.period==='dusk'?'#f4dfbd':'#e2ebe4');c.fillStyle=grad;c.fillRect(0,0,768,512)
    if(!snow){c.fillStyle=night?'#f7edcd':'#fff2cd';c.beginPath();c.arc(580,110,night?29:38,0,Math.PI*2);c.fill()}
    if(night&&!snow)for(let i=0;i<27;i++){c.fillStyle='#eff3e4';c.globalAlpha=.25+(i%4)*.16;c.beginPath();c.arc((i*137)%768,25+(i*67)%240,1+i%2,0,Math.PI*2);c.fill()}c.globalAlpha=1
    for(let i=0;i<3;i++){c.fillStyle=night?['#647d8d','#4c697c','#3c596e'][i]:['#a0bbc0','#8babaf','#789b9e'][i];c.beginPath();c.moveTo(0,350+i*42);for(let x=0;x<=768;x+=8)c.lineTo(x,350+i*42+Math.sin(x*.008+i*1.3)*24);c.lineTo(768,512);c.lineTo(0,512);c.fill()}
    skyTexture.needsUpdate=true
  }
  function project() {
    const feet=new T.Vector3(.5,.09,1.15).project(camera)
    const head=new T.Vector3(.5,1.8,1.15).project(camera)
    options.project((feet.x+1)*width/2,(1-feet.y)*height/2,Math.abs(head.y-feet.y)*height/2)
  }
  function render() {
    if(disposed||lost||!environment)return
    controls.update();fit();project();renderer.render(scene,camera)
  }
  const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)')
  const loop=createFrameLoop((dt)=>{
    if(!active||disposed||lost)return
    weatherTime+=dt
    if(environment.weather!=='clear'){
      for(let i=0;i<seeds.length;i++){
        const {x,y,z}=precipitationPosition(seeds[i],weatherTime,environment.weather)
        positions.set([x,y,z],i*3);rainPositions.set([x,y,z,x-.025,y-.13,z],i*6)
      }
      pg.attributes.position.needsUpdate=true
      rainGeometry.attributes.position.needsUpdate=true
    }
    const moved=controls.update()
    if(moved||environment.weather!=='clear'){fit();project();renderer.render(scene,camera)}
  })
  function resize() {
    const nextWidth=host.clientWidth,nextHeight=host.clientHeight
    if(disposed||nextWidth<1||nextHeight<1)return
    width=nextWidth;height=nextHeight
    fit();renderer.setSize(width,height);render()
  }
  const observer=new ResizeObserver(resize);observer.observe(host)
  const ray=new T.Raycaster(), pointer=new T.Vector2();let down:[number,number]|null=null
  const onDown=(e:PointerEvent)=>{down=[e.clientX,e.clientY]}
  const onUp=(e:PointerEvent)=>{
    if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;down=null
    const bounds=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-bounds.left)/bounds.width*2-1,-(e.clientY-bounds.top)/bounds.height*2+1)
    ray.setFromCamera(pointer,camera);const hit=ray.intersectObjects(targets,true)[0];if(!hit)return
    let object:T.Object3D|null=hit.object;while(object&&!object.userData.slot)object=object.parent
    if(object)options.select(object.userData.slot)
  }
  const onLost=(event:Event)=>{event.preventDefault();lost=true;loop.active(false);options.lost()}
  const onRestored=()=>{lost=false;renderer.shadowMap.needsUpdate=true;resize();loop.active(active&&!reducedMotion.matches);options.restored()}
  const onMotion=()=>loop.active(active&&!lost&&!reducedMotion.matches)
  reducedMotion.addEventListener('change',onMotion)
  renderer.domElement.addEventListener('pointerdown',onDown);renderer.domElement.addEventListener('pointerup',onUp)
  renderer.domElement.addEventListener('webglcontextlost',onLost);renderer.domElement.addEventListener('webglcontextrestored',onRestored)
  controls.addEventListener('change',()=>{if((!active||reducedMotion.matches)&&!disposed&&!lost&&environment){fit();project();renderer.render(scene,camera)}})
  resize()
  return {
    environment(env:RoomEnvironment, light:boolean) {environment=env;lampOn=light;scene.background=new T.Color(env.background);(ground.material as T.MeshStandardMaterial).color.set(env.background);ambient.intensity=env.ambient;sun.intensity=env.sun;sun.color.set(env.period==='dusk'?'#ffd3a3':'#fff2d8');lamp.intensity=lampOn?env.lamp:0;particles.visible=env.weather!=='clear';points.visible=env.weather==='snow';rain.visible=env.weather==='rain';sky(env);renderer.shadowMap.needsUpdate=true;render()},
    active(value:boolean){if(active===value)return;active=value;loop.active(active&&!lost&&!reducedMotion.matches);if(active)resize()},
    reset(){controls.reset();render()},
    dispose(){disposed=true;active=false;loop.dispose();observer.disconnect();controls.dispose();reducedMotion.removeEventListener('change',onMotion);renderer.domElement.removeEventListener('pointerdown',onDown);renderer.domElement.removeEventListener('pointerup',onUp);renderer.domElement.removeEventListener('webglcontextlost',onLost);renderer.domElement.removeEventListener('webglcontextrestored',onRestored);textures.forEach(x=>x.dispose());materials.forEach(x=>x.dispose());geometries.forEach(x=>x.dispose());renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()},
  }
}
export type RoomScene = ReturnType<typeof createRoom>
