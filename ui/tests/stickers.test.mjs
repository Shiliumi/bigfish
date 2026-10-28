import {desktopKeyPath} from '../server/desktop-access.mjs';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import assert from 'node:assert/strict';

const BASE = 'http://127.0.0.1:9120';
const access=(await readFile(desktopKeyPath(),'utf8')).trim();
const page = await fetch(BASE,{headers:{'X-Fish-Desktop':access}});
const cookie = page.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ');

test('the private collection returns attributed, locally stored whale stickers', async () => {
  const response = await fetch(BASE + '/api/stickers', { headers: { cookie } });
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.ok(data.items.length >= 48);
  const sticker = data.items[0];
  assert.ok(sticker.author); assert.ok(sticker.source.startsWith('https://kiriyuki.com/'));
  assert.match(sticker.image_url, /^\/api\/stickers\/[a-f0-9]{16}$/);
  const image = await fetch(BASE + sticker.image_url, { headers: { cookie } });
  assert.equal(image.status, 200); assert.equal(image.headers.get('content-type'), 'image/gif');
  assert.ok(Buffer.from(await image.arrayBuffer()).subarray(0, 6).toString().startsWith('GIF8'));
  assert.equal((await fetch(BASE + sticker.image_url)).status, 401);
  assert.equal((await fetch(BASE + '/api/stickers/0000000000000000', { headers: { cookie } })).status, 404);
});
