import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import activity_gate as gate
from fish_journal import Journal

class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.now=datetime(2026,10,28,12,tzinfo=ZoneInfo('Asia/Shanghai'))
    def report(self,name='1200-surf.md',text='an actual report'):
        path=self.root/'reports/2026-10-28'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);return str(path.relative_to(self.root))
    def finish(self,ident):
        path=self.report('memory-review-'+ident[:12]+'.md','Review-Snapshot: '+ident+'\nReviewed the selected sources.')
        return gate.commit(self.root,ident,path)
    def test_empty_review_and_quiet_hours_skip_before_agent(self):
        self.assertFalse(gate.evaluate(self.root,'memory',self.now)['wakeAgent'])
        self.assertFalse(gate.evaluate(self.root,'surf',self.now.replace(hour=23))['wakeAgent'])
    def test_review_requires_report_and_never_consumes_on_failure(self):
        self.report();decision=gate.evaluate(self.root,'memory',self.now);ident=decision['context']['snapshot_id']
        with self.assertRaises(ValueError):gate.commit(self.root,ident,'reports/missing.md')
        self.assertIsNotNone(gate.pending(self.root))
        self.finish(ident);self.assertIsNone(gate.pending(self.root))
        self.assertTrue(self.finish(ident)['already_committed'])
    def test_new_sources_during_review_are_not_consumed(self):
        self.report();ident=gate.evaluate(self.root,'memory',self.now)['context']['snapshot_id']
        self.report('1500-surf.md','a newer source');self.finish(ident)
        self.assertEqual(len(gate.pending(self.root)['selected']['reports']),1)
    def test_changed_source_rejects_checkpoint(self):
        self.report();ident=gate.evaluate(self.root,'memory',self.now)['context']['snapshot_id'];self.report(text='edited source')
        with self.assertRaises(ValueError):self.finish(ident)
        self.assertFalse((self.root/'data/automation/review-cursor.json').exists())
    def test_bounded_batch_and_non_source_reports_ignored(self):
        for n in range(15):self.report(f'{n:04d}-surf.md',str(n))
        self.report('memory-review.md');other=self.root/'reports/research';other.mkdir();(other/'review.md').write_text('not agent data')
        batch=gate.pending(self.root);self.assertEqual(len(batch['selected']['reports']),12);self.assertEqual(batch['remaining']['reports'],15)
        ident=gate.evaluate(self.root,'memory',self.now)['context']['snapshot_id'];self.finish(ident)
        self.assertEqual(len(gate.pending(self.root)['selected']['reports']),3)
    def test_lease_and_pause_never_start_parallel_agents(self):
        self.assertTrue(gate.evaluate(self.root,'surf',self.now)['wakeAgent'])
        self.assertFalse(gate.evaluate(self.root,'surf',self.now+timedelta(minutes=1))['wakeAgent'])
        gate.write(self.root/'data/automation/settings.json',{'paused':True,'max_outings':1})
        self.assertFalse(gate.evaluate(self.root,'memory',self.now)['wakeAgent'])
    def test_deleted_episode_cannot_be_consumed_as_current(self):
        with Journal(self.root) as journal:item=journal.capture('test-chat','上次的积木厨房','下次还想看看。')
        ident=gate.evaluate(self.root,'memory',self.now)['context']['snapshot_id']
        with Journal(self.root) as journal:journal.update(item['id'],1,forget=True)
        with self.assertRaises(ValueError):self.finish(ident)
        self.assertIsNone(gate.pending(self.root))
    def test_preference_events_appended_during_review_remain_pending(self):
        from personality import propose_trial,trial_feedback
        with Journal(self.root,now=self.now) as store:item=store.capture('start','一起看看积木机关','这次机关很吸引我。')
        trial=propose_trial(self.root,{'id':'builds','text':'我似乎喜欢积木里小小的机关。','reason':'这次具体看到了一个有趣的机关。','evidence_ids':[item['id']]},self.now)
        ident=gate.evaluate(self.root,'memory',self.now)['context']['snapshot_id']
        gate.review(self.root,ident)
        with Journal(self.root,now=self.now+timedelta(days=1)) as store:new=store.capture('next','另一个积木厨房作品','我又想跟着看看这个机关。')
        trial_feedback(self.root,{'id':trial['id'],'revision':trial['revision'],'outcome':'followed','reason':'这次新作品还有另一个具体的机关。','evidence_ids':[new['id']]},self.now+timedelta(days=1))
        self.finish(ident);pending=gate.pending(self.root);self.assertEqual(len(pending['selected']['preference_events']),1)

    def test_corrupt_settings_rejected(self):
        gate.write(self.root/'data/automation/settings.json',{'paused':False,'max_outings':0})
        with self.assertRaises(ValueError):gate.evaluate(self.root,'surf',self.now)


class GateCommandTest(unittest.TestCase):
    def test_corrupt_state_emits_skip_with_success_exit_for_hermes(self):
        import subprocess, shutil
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'scripts').mkdir();(root/'data/automation').mkdir(parents=True)
            for name in ('activity_gate.py','curiosity.py','fish_journal.py'):
                shutil.copy2(Path(__file__).with_name(name),root/'scripts'/name)
            (root/'data/automation/settings.json').write_text('{invalid json')
            result=subprocess.run(['python3',str(root/'scripts/activity_gate.py'),'surf'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0);value=json.loads(result.stdout);self.assertFalse(value['wakeAgent']);self.assertTrue(value['error'])
            self.assertTrue(json.loads((root/'data/automation/gates.json').read_text())['surf']['error'])

if __name__=='__main__':unittest.main()
