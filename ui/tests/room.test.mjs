import test from 'node:test';
import assert from 'node:assert/strict';
import {roomEnvironment,roomActivity,roomFrustum} from '../src/room/environment.mjs';
import {createFrameLoop} from '../src/room/frame-loop.mjs';
import {OrthographicCamera,Vector3} from 'three';
import {weatherParticles,precipitationPosition} from '../src/room/precipitation.mjs';

test('automatic dayparts use China time, including midnight and boundaries',()=>{
  for(const [at,want] of [['2026-11-01T22:59:00Z','night'],['2026-11-01T23:00:00Z','day'],['2026-11-02T09:00:00Z','dusk'],['2026-11-02T11:00:00Z','night']])assert.equal(roomEnvironment('auto','clear',new Date(at)).period,want);
});
test('manual atmosphere validates persisted settings and handles overcast light locally',()=>{
  const at=new Date('2026-11-02T02:00:00Z');
  assert.equal(roomEnvironment('night','snow',at).period,'night');
  assert.equal(roomEnvironment('broken','broken',at).weather,'clear');
  assert.equal(roomEnvironment('broken','clear',at).period,'day');
  assert.ok(roomEnvironment('day','rain',at).ambient<roomEnvironment('day','clear',at).ambient);
});
test('activity uses service facts without inventing reading or sleep for idle',()=>{
  assert.deepEqual(roomActivity({state:'surfing',label:'正在翻网页'}),{animation:'working',label:'正在翻网页'});
  assert.equal(roomActivity({state:'idle'}).animation,'idle');
  assert.equal(roomActivity({state:'letter'}).animation,'idle');
  assert.equal(roomActivity({state:'offline'}).animation,'look');
});

test('render clock has one subscription, caps time after suspension, and cannot restart after disposal',()=>{
  let at=0,next=0;const callbacks=new Map(),frames=[];
  const loop=createFrameLoop((dt)=>frames.push(dt),{request:cb=>{callbacks.set(++next,cb);return next;},cancel:id=>callbacks.delete(id),now:()=>at});
  const advance=time=>{at=time;const pending=[...callbacks.values()];callbacks.clear();pending.forEach(cb=>cb(time));};
  loop.active(true);loop.active(true);assert.equal(callbacks.size,1);
  advance(10);assert.equal(frames.length,0);advance(40);assert.equal(frames.length,1);
  loop.active(false);assert.equal(callbacks.size,0);advance(3_600_000);assert.equal(frames.length,1);
  loop.active(true);advance(3_600_040);assert.ok(frames.at(-1)<.1);
  advance(3_700_000);assert.equal(frames.at(-1),.1);
  loop.dispose();assert.equal(callbacks.size,0);loop.active(true);assert.equal(callbacks.size,0);
});

test('room bounds fit narrow and wide viewports across permitted camera angles without cutting walls',()=>{
  const corners=[];for(const x of [-3.8,3.8])for(const y of [-.5,3.8])for(const z of [-3.3,3.3])corners.push(new Vector3(x,y,z));
  for(const aspect of [484/400,940/640,1600/640])for(const azimuth of [.32,.7,1.13])for(const polar of [.65,.9,1.14]){
    const camera=new OrthographicCamera(-6,6,5,-5,.1,70);
    camera.position.set(17*Math.sin(polar)*Math.sin(azimuth),1.5+17*Math.cos(polar),17*Math.sin(polar)*Math.cos(azimuth));
    camera.lookAt(0,1.5,0);camera.updateMatrixWorld();
    Object.assign(camera,roomFrustum(aspect,corners.map(p=>p.clone().applyMatrix4(camera.matrixWorldInverse))));camera.updateProjectionMatrix();
    for(const p of corners){const projected=p.clone().project(camera);assert.ok(Math.abs(projected.x)<1&&Math.abs(projected.y)<1);}
    assert.ok(Math.abs((camera.right-camera.left)/(camera.top-camera.bottom)-aspect)<1e-9);
  }
});

test('weather remains inside the actual window over long running and switches between rain and snow',()=>{
  const particles=weatherParticles();assert.equal(particles.length,72);assert.deepEqual(particles,weatherParticles());
  assert.equal(new Set(particles.map(p=>p.speed)).size,particles.length);
  for(const time of [0,.04,1,10,7200,86400])for(const weather of ['snow','rain'])for(const particle of particles){
    const p=precipitationPosition(particle,time,weather);
    assert.ok(p.x>-.99&&p.x<2.4);assert.ok(p.y>=.98&&p.y<2.98);assert.equal(p.z,-3.1);
  }
  const snow=precipitationPosition(particles[0],.1,'snow'),rain=precipitationPosition(particles[0],.1,'rain');
  assert.notEqual(snow.y,rain.y);assert.notEqual(snow.x,rain.x);
});
