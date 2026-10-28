import test from 'node:test';import assert from 'node:assert/strict';import {routineInfo} from '../src/routines.mjs';
test('custom tasks retain their actual names and never inherit the surf label',()=>{
 for(const name of ['study-reminder','fish-surf-extra','周末读书']){const value=routineInfo({name});assert.equal(value.title,name);assert.equal(value.actionName,name);assert.equal(value.kind,'custom');assert.equal(value.scheduleCaption,'执行时间');assert.doesNotMatch(value.description,/冲浪|记忆整理/)}
 assert.equal(routineInfo({name:'fish-surf'}).kind,'surf');assert.equal(routineInfo({name:'fish-memory'}).kind,'memory');
});
