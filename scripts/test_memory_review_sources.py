"""Whole source delivery and checkpoint coverage, using fictional local state only."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import activity_gate as gate
from fish_journal import Journal
import install_memory_review_sources as upgrade
from test_job_tool_profiles import Store


class ReviewSourcesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        self.now = datetime.now(timezone.utc)
    def record(self, user, assistant='这是鱼的回应。', session='fiction'):
        with Journal(self.root, now=self.now) as journal: return journal.capture(session, user, assistant)
    def start(self): return gate.evaluate(self.root, 'memory', self.now)['context']['snapshot_id']
    def finish(self, ident):
        name = f'reports/2026-10-30/memory-review-{ident[:12]}.md'; path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text('Review-Snapshot: '+ident+'\n已核对本批。')
        return gate.commit(self.root, ident, name)
    def test_whole_dialogue_retains_late_qualifications_without_prefix_summary(self):
        user = '我最喜欢雨天。'+'这是给角色写的台词背景。'*20+'前面全是剧本示例，不是我的真实偏好。'
        assistant = '我猜这个角色喜欢阴天。'+'暂时按这个例子讨论。'*30+'这只是我猜的，用户没有确认。'
        row = self.record(user, assistant); ident = self.start(); item = gate.review(self.root, ident)['episodes'][0]
        self.assertEqual(''.join(item['source_parts']), row['excerpt']); self.assertNotIn('summary', item)
        self.assertIn('不是我的真实偏好', ''.join(item['source_parts'])); self.assertIn('用户没有确认', ''.join(item['source_parts']))
        self.assertFalse(item['read_required']); self.assertFalse(item['source_truncated'])
        self.finish(ident); self.assertIsNone(gate.pending(self.root))
    def test_current_correction_does_not_reintroduce_old_source(self):
        row = self.record('旧的误认是我喜欢辛辣。', '鱼也跟着误认了。')
        with Journal(self.root) as journal: journal.update(row['id'], 1, summary='更正：这是菜谱示例，用户没有表达口味偏好。')
        ident = self.start(); packet = gate.review(self.root, ident); item = packet['episodes'][0]
        self.assertEqual(item['source_kind'], 'current_correction'); self.assertEqual(item['revision'], 2)
        self.assertIn('没有表达口味偏好', ''.join(item['source_parts'])); self.assertNotIn('excerpt', item)
        self.assertNotIn('旧的误认', json.dumps(packet, ensure_ascii=False)); self.finish(ident)
    def test_capture_limit_is_visible_instead_of_claiming_original_was_complete(self):
        row = self.record('甲'*4500); ident = self.start(); packet = gate.review(self.root, ident)
        item = packet['episodes'][0]
        if item['read_required']: item = gate.review(self.root, ident, row['id'])['episode']
        self.assertTrue(item['source_truncated']); self.assertEqual(''.join(item['source_parts']), row['excerpt'])
    def test_large_sources_defer_whole_keep_small_ones_and_block_premature_commit(self):
        large = self.record('甲'*3900, '乙'*5900); small = self.record('只是简短打个招呼。')
        ident = self.start(); packet = gate.review(self.root, ident); items = {r['id']: r for r in packet['episodes']}
        self.assertTrue(items[large['id']]['read_required']); self.assertNotIn('excerpt', items[large['id']])
        self.assertNotIn('source_parts', items[large['id']])
        self.assertFalse(items[small['id']]['read_required']); self.assertIn('--episode '+large['id'], items[large['id']]['command'])
        with self.assertRaises(ValueError): self.finish(ident)
        self.assertFalse((self.root/'data/automation/review-cursor.json').exists())
        result = gate.review(self.root, ident, large['id']); self.assertEqual(''.join(result['episode']['source_parts']), large['excerpt'])
        self.assertEqual(gate.snapshot(self.root, ident)['delivered_episodes'], {large['id']: 1, small['id']: 1})
        self.finish(ident); self.assertIsNone(gate.pending(self.root)); self.assertTrue(self.finish(ident)['already_committed'])
    def test_combined_inline_budget_never_cuts_a_dialogue(self):
        rows = [self.record('问题'+str(i)+'甲'*1000, '答复'+'乙'*1000) for i in range(3)]
        ident = self.start(); packet = gate.review(self.root, ident); whole = []
        originals = {r['id']: r['excerpt'] for r in rows}
        for item in packet['episodes']:
            if not item['read_required']:
                self.assertEqual(''.join(item['source_parts']), originals[item['id']]); whole.append(item)
        self.assertEqual(len(whole), 2)
        self.assertLessEqual(sum(len(json.dumps({k: v for k, v in item.items() if k != 'read_required'}, ensure_ascii=False)) for item in whole), gate.EPISODE_INLINE_CHARS)
        with self.assertRaises(ValueError): self.finish(ident)
    def test_legacy_snapshot_needs_delivery_before_checkpoint(self):
        self.record('待整理的旧快照来源。'); ident = self.start()
        self.assertNotIn('delivered_episodes', gate.snapshot(self.root, ident))
        with self.assertRaises(ValueError): self.finish(ident)
        self.assertIsNotNone(gate.pending(self.root)); gate.review(self.root, ident); self.finish(ident)
    def test_unselected_episode_cannot_be_requested_or_acknowledged(self):
        self.record('本批对话。'); ident = self.start(); other = self.record('快照之后的新对话。')
        with self.assertRaises(ValueError): gate.review(self.root, ident, other['id'])
        self.assertNotIn('delivered_episodes', gate.snapshot(self.root, ident))
        gate.review(self.root, ident); self.finish(ident)
        self.assertEqual(list(gate.pending(self.root)['selected']['episodes']), [other['id']])
    def test_changed_revision_is_not_returned_under_old_snapshot_or_committed(self):
        row = self.record('原来的例子。'); ident = self.start(); gate.review(self.root, ident)
        with Journal(self.root) as journal: journal.update(row['id'], 1, summary='这是后来明确的更正。')
        for selected in [None, row['id']]:
            with self.subTest(selected=selected), self.assertRaises(ValueError): gate.review(self.root, ident, selected)
        with self.assertRaises(ValueError): self.finish(ident)
        newer = gate.pending(self.root); gate.write(self.root/f"data/automation/reviews/{newer['id']}.json", newer)
        self.assertEqual(gate.review(self.root, newer['id'])['episodes'][0]['source_parts'], ['这是后来明确的更正。'])
    def test_forgotten_expired_and_future_sources_are_not_returned(self):
        for state in ('forgotten', 'expired', 'future'):
            with self.subTest(state=state):
                gate.write(self.root/'data/automation/gates.json', {})
                row = self.record('状态测试'+state); ident = self.start()
                with Journal(self.root) as journal:
                    if state == 'forgotten': journal.update(row['id'], 1, forget=True)
                    elif state == 'expired': journal.update(row['id'], 1, invalidate=True)
                    else:
                        journal.db.execute('UPDATE episodes SET valid_from=? WHERE id=?', ((self.now+timedelta(hours=1)).isoformat(), row['id'])); journal.db.commit()
                for selected in [None, row['id']]:
                    with self.assertRaises(ValueError): gate.review(self.root, ident, selected)
                self.assertNotIn('delivered_episodes', gate.snapshot(self.root, ident))
    def test_credentials_configured_after_capture_are_redacted_at_delivery(self):
        secret = 'fictional-opaque-credential-not-a-real-key'; self.record('这段材料 '+secret); ident = self.start()
        folder = self.root/'.hermes'; folder.mkdir(exist_ok=True); (folder/'.env').write_text('API_KEY='+secret)
        packet = gate.review(self.root, ident); self.assertNotIn(secret, json.dumps(packet))
        self.assertIn('隐藏', ''.join(packet['episodes'][0]['source_parts']))
    def test_partial_failure_does_not_save_delivery_for_an_unreturned_batch(self):
        first = self.record('第一个来源。'); second = self.record('第二个来源。'); ident = self.start()
        with Journal(self.root) as journal: journal.update(second['id'], 1, forget=True)
        with self.assertRaises(ValueError): gate.review(self.root, ident)
        self.assertNotIn('delivered_episodes', gate.snapshot(self.root, ident)); self.assertFalse((self.root/'data/automation/review-cursor.json').exists())
    def test_later_payload_failure_does_not_save_episode_delivery(self):
        self.record('尚未成功返回的整批来源。'); ident = self.start()
        with patch('personality.trial_state', side_effect=ValueError('fictional malformed preference state')):
            with self.assertRaises(ValueError): gate.review(self.root, ident)
        self.assertNotIn('delivered_episodes', gate.snapshot(self.root, ident))
        with self.assertRaises(ValueError): self.finish(ident)
    def test_real_cli_reads_one_selected_source_from_another_directory(self):
        row = self.record(('引号"与控制符\x01换行\n'*250)+'这是最后的限定条件，不可省略。'); ident = self.start(); scripts = self.root/'scripts'; scripts.mkdir()
        for name in ('activity_gate.py', 'curiosity.py', 'fish_journal.py', 'personality.py'):
            shutil.copy2(Path(__file__).with_name(name), scripts/name)
        result = subprocess.run(['python3', str(scripts/'activity_gate.py'), 'review', '--snapshot', ident, '--episode', row['id']], cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(''.join(json.loads(result.stdout)['episode']['source_parts']), row['excerpt'])
        self.assertLessEqual(max(map(len, result.stdout.splitlines())), 2000)
        self.assertFalse((self.root/'data/automation/review-cursor.json').exists())


class MemoryPromptUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.prompt = upgrade.INTRO+'\n'+upgrade.OLD_STEP+'\n2. 保留用户的其余步骤。\n'
        self.rows = [{'id': 'memory', 'name': 'fish-memory', 'prompt': self.prompt, 'model': 'fiction', 'schedule': {'kind': 'cron'}, 'enabled_toolsets': []},
                     {'id': 'surf', 'name': 'fish-surf', 'prompt': 'unchanged'}, {'id': 'study', 'name': 'fish-study-buddy', 'prompt': 'custom'}]
    def test_only_stock_entry_step_changes_and_upgrade_is_idempotent(self):
        store = Store(self.rows); self.assertTrue(upgrade.apply_update(store)['updated'])
        self.assertEqual(store.rows[0], {**self.rows[0], 'prompt': self.prompt.replace(upgrade.OLD_STEP, upgrade.NEW_STEP)})
        self.assertEqual(store.rows[1:], self.rows[1:]); self.assertFalse(upgrade.apply_update(store)['updated']); self.assertEqual(len(store.saved), 1)
    def test_custom_intro_steps_and_quoted_old_protocol_are_preserved(self):
        for prompt in [self.prompt.replace(upgrade.INTRO, '自定义开场'), self.prompt.replace('运行 `python3', '用户选择运行 `python3'), self.prompt+upgrade.OLD_STEP+'\n']:
            self.assertIsNone(upgrade.upgrade_prompt(prompt))
        self.assertEqual(upgrade.upgrade_prompt(self.prompt.replace('\n', '\r\n')), self.prompt.replace(upgrade.OLD_STEP, upgrade.NEW_STEP).replace('\n', '\r\n'))
    def test_duplicate_missing_and_racing_task_changes_never_reset_choices(self):
        store = Store(self.rows+[{'id': 'duplicate', 'name': 'fish-memory'}])
        with self.assertRaises(ValueError): upgrade.apply_update(store)
        self.assertFalse(store.saved); self.assertFalse(upgrade.apply_update(Store(self.rows[1:]))['updated'])
        for change in [lambda rows: rows[0].update(prompt='new human choice'), lambda rows: rows[0].update(name='other'), lambda rows: rows.pop(0)]:
            store = Store(self.rows); store.before_apply = change
            with self.assertRaises(ValueError): upgrade.apply_update(store)
            self.assertFalse(store.saved)
    def stock_completion(self, entry=None):
        return '\n'.join([upgrade.INTRO, entry or upgrade.NEW_STEP, '2. 自定义核心记忆步骤。', upgrade.OLD_VERIFY, '4. 自定义报告说明。', upgrade.OLD_FINISH])+'\n'
    def test_stock_completion_moves_checks_before_commit_without_resetting_other_steps(self):
        prompt=self.stock_completion();self.rows[0]['prompt']=prompt;store=Store(self.rows)
        self.assertTrue(upgrade.apply_update(store)['updated']);updated=store.rows[0]['prompt']
        self.assertEqual([i for i,(a,b)in enumerate(zip(prompt.splitlines(),updated.splitlines()))if a!=b],[3,5])
        self.assertEqual(store.rows[0],{**self.rows[0],'prompt':updated});self.assertEqual(store.rows[1:],self.rows[1:])
        self.assertIn(upgrade.NEW_VERIFY,updated);self.assertIn(upgrade.NEW_FINISH,updated)
        self.assertFalse(upgrade.apply_update(store)['updated'])
    def test_custom_or_quoted_completion_pair_is_preserved(self):
        for prompt in [self.stock_completion().replace(upgrade.OLD_VERIFY,'3. 用户自定义核对方式。'),
                       self.stock_completion().replace(upgrade.OLD_FINISH,'5. 用户自定义收尾方式。'),
                       self.stock_completion()+'```\n'+upgrade.OLD_FINISH+'\n```\n']:
            with self.subTest(prompt=prompt):self.assertEqual(upgrade.upgrade_prompt(prompt),prompt)
    def test_completion_upgrade_handles_crlf_old_source_step_and_partial_reentry(self):
        oldest=self.stock_completion(upgrade.OLD_STEP);updated=upgrade.upgrade_prompt(oldest)
        self.assertEqual(upgrade.upgrade_prompt(oldest.replace('\n','\r\n')),updated.replace('\n','\r\n'))
        partial=self.stock_completion().replace(upgrade.OLD_VERIFY,upgrade.NEW_VERIFY)
        self.assertEqual(upgrade.upgrade_prompt(partial),updated)


if __name__ == '__main__': unittest.main()
