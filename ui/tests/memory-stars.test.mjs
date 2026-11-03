import test from 'node:test';
import assert from 'node:assert/strict';
import {starPositions,dateAt,dateOffset,relatedStars} from '../src/memory/star-layout.mjs';
test('star layout is deterministic and independent of filter order; positions have no semantic meaning',()=>{
  const nodes=Array.from({length:500},(_,i)=>({id:'ep-'+String(i).padStart(24,'0'),group:'cg-'+i%9})),all=starPositions(nodes);
  assert.deepEqual(starPositions(nodes),all);
  assert.deepEqual(starPositions(nodes.slice(100,110).reverse()),all.slice(100,110).reverse());
  assert.ok(all.every(n=>n.position.every(Number.isFinite)&&Math.hypot(...n.position)<11));
  assert.equal(new Set(all.map(n=>n.position.join(','))).size,500);
});
test('date navigation is day based, handles leap days and year boundaries',()=>{
  assert.equal(dateAt('2024-02-28',1),'2024-02-29');assert.equal(dateOffset('2024-02-28','2024-03-01'),2);
  assert.equal(dateAt('2026-12-31',1),'2027-01-01');assert.equal(dateOffset('2026-10-01','2026-11-03'),33);
});
test('related inspector uses only explicit edges and keeps their reasons',()=>{
  const edge={source:'a',target:'b',reasons:[{kind:'alias',label:'共同手动别名：纸机关'}]};
  assert.deepEqual(relatedStars({edges:[edge]},'b'),[{id:'a',reasons:edge.reasons}]);assert.deepEqual(relatedStars({edges:[edge]},'unlinked'),[]);
});
