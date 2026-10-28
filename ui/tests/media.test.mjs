import test from 'node:test';
import assert from 'node:assert/strict';
import { mediaRange } from '../server/media.mjs';
test('Safari probes, subsequent chunks and suffix ranges preserve exact byte offsets', () => {
  assert.deepEqual(mediaRange('bytes=0-1',100),{start:0,end:1});
  assert.deepEqual(mediaRange('bytes=30-',100),{start:30,end:99});
  assert.deepEqual(mediaRange('bytes=-10',100),{start:90,end:99});
  assert.deepEqual(mediaRange('bytes=80-500',100),{start:80,end:99});
  assert.equal(mediaRange(undefined,100),null);
  for (const invalid of ['bytes=100-','bytes=10-2','bytes=-0','bytes=-','bytes=0-1,5-8','bytes=abc','bytes=99999999999999999999-']) assert.deepEqual(mediaRange(invalid,100),{invalid:true});
});
