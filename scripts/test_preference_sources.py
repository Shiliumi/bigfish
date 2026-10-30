"""Read-time source checks for unpromoted personality trials; fictional state only."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
import personality as growth
from fish_journal import Journal


class TrialSourceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        self.now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        (self.root/'.hermes').mkdir(); (self.root/'.hermes/SOUL.md').write_text('手写身份，保留。')
        self.text = '我似乎喜欢从具体的小反差里接一句短话。'
    def episode(self, name, days=0):
        with Journal(self.root, now=self.now+timedelta(days=days)) as journal:
            return journal.capture('fiction-'+name, '这次聊到纸盒机关'+name, '这个小反差'+name+'让我想再接一句。')
    def start(self, name='small-reaction', kind='expression', ids=None):
        row = self.episode(name) if ids is None else None
        trial = growth.propose_trial(self.root, {'id': name, 'kind': kind, 'text': self.text,
            'reason': '这次聊天确实出现了一个具体的小反差。', 'evidence_ids': ids or [row['id']]}, self.now)
        return trial, row
    def view(self, now=None): return growth.preference_snapshot(self.root, now or self.now)['trials']
    def context(self, **options): return growth.preference_context(self.root, '纸盒机关', now=options.pop('now', self.now), **options)
    def forget(self, row):
        with Journal(self.root, now=self.now) as journal: journal.update(row['id'], 1, forget=True)
    def test_only_support_forgotten_pauses_without_echoing_old_wording(self):
        trial, row = self.start(); self.forget(row); item = self.view()[0]
        self.assertEqual(item['stage'], 'reconsidering'); self.assertTrue(item['needs_review'])
        self.assertFalse(item['has_current_support']); self.assertEqual(item['evidence'], [])
        packet = self.context(); self.assertEqual(packet[0]['stage'], 'reconsidering')
        self.assertNotIn(self.text, json.dumps(packet, ensure_ascii=False)); self.assertNotIn('text', packet[0]); self.assertIn('暂停', packet[0]['note'])
    def test_changed_expired_and_future_support_do_not_remain_active_trials(self):
        for action in ('corrected', 'expired', 'future'):
            with self.subTest(action=action):
                trial, row = self.start('trial-'+action)
                with Journal(self.root, now=self.now) as journal:
                    if action == 'corrected': journal.update(row['id'], 1, summary='更正：那段只是给角色写的示例。')
                    elif action == 'expired': journal.update(row['id'], 1, invalidate=True)
                    else:
                        journal.db.execute('UPDATE episodes SET valid_from=? WHERE id=?', ((self.now+timedelta(hours=1)).isoformat(), row['id'])); journal.db.commit()
                item = next(r for r in self.view() if r['id'] == trial['id'])
                self.assertEqual(item['stage'], 'reconsidering'); self.assertFalse(item['has_current_support'])
                self.assertNotIn(self.text, json.dumps(self.context(), ensure_ascii=False))
    def test_external_observation_losing_its_report_also_pauses(self):
        url = 'https://example.org/paper-box'; report = 'reports/2026-10-01/1200-surf.md'
        path = self.root/report; path.parent.mkdir(parents=True); path.write_text('虚构正文 '+url)
        (self.root/'data').mkdir(exist_ok=True); (self.root/'data/surf-state.json').write_text(json.dumps({'visited': [{'url': url, 'report': report, 'read_at': self.now.isoformat()}]}))
        observation = growth.record(self.root, {'url': url, 'seen_at': self.now.isoformat(), 'report_path': report,
            'read_depth': 'body', 'observation': '纸盒展开时露出一个小机关。', 'candidate_trait': '想看看具体的折叠小机关。', 'reason': '喜欢这个结构突然展开的反差。'}, self.now)[0]
        trial, _ = self.start(kind='interest', ids=[observation['id']]); path.unlink()
        self.assertEqual(self.view()[0]['stage'], 'reconsidering')
        self.assertNotIn(self.text, json.dumps(self.context(for_browsing=True), ensure_ascii=False))
    def test_uncertain_only_signal_is_not_positive_support(self):
        trial, row = self.start()
        growth.trial_feedback(self.root, {'id': trial['id'], 'revision': trial['revision'], 'outcome': 'uncertain',
            'reason': '这次还没有想清楚，暂时不作为喜欢的依据。', 'evidence_ids': [row['id']]}, self.now)
        self.assertFalse(self.view()[0]['has_current_support']); self.assertEqual(self.view()[0]['stage'], 'reconsidering')
        self.assertNotIn(self.text, json.dumps(self.context(), ensure_ascii=False))
    def test_new_negative_feedback_marks_unpromoted_trial_for_review(self):
        trial, row = self.start(); other = self.episode('negative', 1)
        growth.trial_feedback(self.root, {'id': trial['id'], 'revision': trial['revision'], 'outcome': 'not_for_me',
            'reason': '这次觉得这种表达不合适，先收起再想。', 'evidence_ids': [other['id']]}, self.now+timedelta(days=1))
        item = self.view(self.now+timedelta(days=1))[0]
        self.assertTrue(item['has_current_support']); self.assertEqual(item['stage'], 'reconsidering')
        self.assertEqual(self.context(now=self.now+timedelta(days=1))[0]['stage'], 'reconsidering')
    def test_one_missing_source_does_not_hide_other_valid_positive_support(self):
        a = self.episode('first'); b = self.episode('second'); trial, _ = self.start(ids=[a['id'], b['id']]); self.forget(a)
        item = self.view()[0]; self.assertEqual(item['stage'], 'trying'); self.assertTrue(item['has_current_support'])
        self.assertEqual([r['id'] for r in item['evidence']], [b['id']]); self.assertEqual(self.context()[0]['text'], self.text)
    def test_negative_review_needs_new_positive_followup_and_existing_cooldown(self):
        trial, _ = self.start(); negative = self.episode('negative', 1)
        trial = growth.trial_feedback(self.root, {'id': trial['id'], 'revision': trial['revision'], 'outcome': 'not_for_me',
            'reason': '这次觉得不合适，需要先收起。', 'evidence_ids': [negative['id']]}, self.now+timedelta(days=1))
        self.assertEqual(self.view(self.now+timedelta(days=5))[0]['stage'], 'reconsidering')
        positive = self.episode('later-positive', 2)
        growth.trial_feedback(self.root, {'id': trial['id'], 'revision': trial['revision'], 'outcome': 'enjoyed',
            'reason': '后来这次独立的新经历确实更适合这种表达。', 'evidence_ids': [positive['id']]}, self.now+timedelta(days=2))
        self.assertEqual(self.view(self.now+timedelta(days=2))[0]['stage'], 'reconsidering')
        self.assertEqual(self.view(self.now+timedelta(days=4))[0]['stage'], 'trying')
    def test_fresh_explicit_followup_resumes_without_restoring_forgotten_source(self):
        trial, row = self.start(); self.forget(row); self.assertEqual(self.view()[0]['stage'], 'reconsidering')
        new = self.episode('fresh', 1)
        growth.trial_feedback(self.root, {'id': trial['id'], 'revision': trial['revision'], 'outcome': 'enjoyed',
            'reason': '这次新机关的反差让我确实又想接一句。', 'evidence_ids': [new['id']]}, self.now+timedelta(days=1))
        item = self.view(self.now+timedelta(days=1))[0]; self.assertEqual(item['stage'], 'trying')
        self.assertEqual([r['id'] for r in item['evidence']], [new['id']]); self.assertEqual(self.context(now=self.now+timedelta(days=1))[0]['text'], self.text)
        with Journal(self.root, now=self.now+timedelta(days=1)) as journal: self.assertEqual(journal.get(row['id'])['status'], 'deleted')
    def test_unavailable_trial_warning_survives_style_opt_out_without_old_text(self):
        _, row = self.start(); self.forget(row)
        for mode in ('focused', 'gentle', 'feedback', 'playful', 'personal'):
            with self.subTest(mode=mode):
                packet = self.context(style_mode=mode, allow_expression=False)
                self.assertEqual(packet[0]['stage'], 'reconsidering'); self.assertNotIn(self.text, json.dumps(packet, ensure_ascii=False))
    def test_source_loss_does_not_revive_faded_or_retired_trials(self):
        trial, row = self.start(); self.forget(row)
        self.assertEqual(self.view(self.now+timedelta(days=22))[0]['stage'], 'faded')
        self.assertEqual(self.context(now=self.now+timedelta(days=22)), [])
        growth.retire_trial(self.root, {'id': trial['id'], 'revision': trial['revision'], 'reason': '这次主动放下，不继续表演这个表达。'}, self.now)
        self.assertEqual(self.view()[0]['stage'], 'retired'); self.assertEqual(self.context()[0]['stage'], 'retired')
        self.assertEqual(self.context(now=self.now+timedelta(days=8)), [])
    def test_read_time_pause_does_not_mutate_trial_core_or_memory(self):
        trial, row = self.start(); self.forget(row)
        files = [self.root/'data/personality/trials.json', self.root/'.hermes/SOUL.md']; original = [p.read_bytes() for p in files]
        with Journal(self.root, now=self.now) as journal:
            changes = journal.db.total_changes; self.context(journal=journal); self.assertEqual(journal.db.total_changes, changes)
        self.assertEqual([p.read_bytes() for p in files], original)
        self.assertEqual(growth.trial_state(self.root)['trials'][0]['revision'], trial['revision'])
        self.assertFalse((self.root/'data/personality/profile.json').exists())


if __name__ == '__main__': unittest.main()
