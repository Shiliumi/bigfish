import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { deliveryDecision, SOCIAL_DEFAULTS, createInbox } from '../server/inbox.mjs';

const noon = Date.parse('2026-10-27T12:00:00+08:00');
const candidate = { created_at: new Date(noon - 60000).toISOString(), source_url: 'https://example.org/interesting' };
test('quiet hours, cooldown, daily cap, recent conversation and duplicates prevent interruptions', () => {
  const decide = (history = [], settings = SOCIAL_DEFAULTS, now = noon, active = 0) => deliveryDecision(candidate, history, settings, now, active);
  assert.equal(decide(), 'send');
  assert.equal(decide([], { ...SOCIAL_DEFAULTS, enabled: false }), 'wait');
  assert.equal(decide([], SOCIAL_DEFAULTS, Date.parse('2026-10-27T23:00:00+08:00')), 'wait');
  assert.equal(decide([], SOCIAL_DEFAULTS, noon, noon - 1000), 'wait');
  assert.equal(decide([{ source_url: 'https://example.org/other', sent_at: new Date(noon - 3600000).toISOString() }]), 'wait');
  assert.equal(decide([{ source_url: candidate.source_url, sent_at: new Date(noon - 6 * 3600000).toISOString() }]), 'duplicate');
  const later = Date.parse('2026-10-27T21:00:00+08:00');
  assert.equal(decide([9, 14].map(hour => ({ source_url: 'other' + hour, sent_at: `2026-10-27T${String(hour).padStart(2, '0')}:00:00+08:00` })), SOCIAL_DEFAULTS, later), 'wait');
  assert.equal(decide([], SOCIAL_DEFAULTS, noon + 25 * 3600000), 'expired');
});
test('verified discoveries persist once; unverified links and low-value candidates never become messages', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'bigfish-inbox-'));
  try {
    await mkdir(path.join(root, 'data/outbox'), { recursive: true });
    await mkdir(path.join(root, 'reports/2026-10-27'), { recursive: true });
    await writeFile(path.join(root, 'reports/2026-10-27/1200-surf.md'), candidate.source_url);
    await writeFile(path.join(root, 'data/surf-state.json'), JSON.stringify({ visited: [{ url: candidate.source_url }] }));
    const entry = { ...candidate, created_at: new Date(noon).toISOString(), worth_sharing: true, why_share: '具体的新发现，确实值得和你聊', text: '这个设计居然把问题绕过去了，有点东西。', report_path: 'reports/2026-10-27/1200-surf.md' };
    await writeFile(path.join(root, 'data/outbox/valid.json'), JSON.stringify(entry));
    await writeFile(path.join(root, 'data/outbox/unverified.json'), JSON.stringify({ ...entry, source_url: 'https://example.org/made-up' }));
    await writeFile(path.join(root, 'data/outbox/boring.json'), JSON.stringify({ ...entry, worth_sharing: false }));
    const inbox = createInbox(root, () => noon); await inbox.tick(); await inbox.tick();
    const snapshot = await inbox.snapshot();
    assert.equal(snapshot.messages.length, 1);
    await inbox.update(snapshot.messages[0].id, {read:true});
    assert.equal((await createInbox(root).snapshot()).unread, 0);
    assert.ok(snapshot.messages.every(m => m.source_url === candidate.source_url));
    await inbox.settings(false); assert.equal((await inbox.snapshot()).settings.enabled, false);
  } finally { await rm(root, { recursive: true, force: true }); }
});
