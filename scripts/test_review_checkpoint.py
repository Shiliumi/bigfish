"""Fault injection for the single-file commit point and derived review metadata."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import activity_gate as gate
from fish_journal import Journal


class CheckpointTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.now=datetime(2026,10,31,12,tzinfo=ZoneInfo('Asia/Shanghai'))
        source=self.root/'reports/2026-10-31/1200-surf.md';source.parent.mkdir(parents=True);source.write_text('fictional report')
        self.source=source
        self.ident=gate.evaluate(self.root,'memory',self.now)['context']['snapshot_id']
        self.report=f'reports/2026-10-31/memory-review-{self.ident[:12]}.md';(self.root/self.report).write_text('Review-Snapshot: '+self.ident+'\n已经核对来源。')
        self.cursor=self.root/'data/automation/review-cursor.json';self.snapshot=self.root/f'data/automation/reviews/{self.ident}.json'
    def fail_at(self, phase):
        original=gate.write
        def write(path,value):
            match=(phase=='publish'and path==self.cursor and '_pending_commit'in value or
                   phase=='snapshot'and path==self.snapshot and value.get('committed_at') or
                   phase=='lease'and path.name=='gates.json'and value.get('memory',{}).get('lease_until')is None or
                   phase=='clear'and path==self.cursor and '_pending_commit'not in value)
            if match:raise OSError('fictional '+phase+' failure')
            return original(path,value)
        return patch.object(gate,'write',side_effect=write)
    def assert_completed(self):
        self.assertNotIn('_pending_commit',gate.read(self.cursor,{}));self.assertTrue(gate.snapshot(self.root,self.ident)['committed_at'])
        self.assertIsNone(gate.read(self.root/'data/automation/gates.json',{})['memory']['lease_until'])
    def test_failure_before_publication_does_not_advance_and_is_retryable(self):
        with self.fail_at('publish'):
            with self.assertRaises(OSError):gate.commit(self.root,self.ident,self.report)
        self.assertFalse(self.cursor.exists());self.assertIsNotNone(gate.pending(self.root))
        self.assertFalse(gate.snapshot(self.root,self.ident).get('committed_at'))
        self.assertTrue(gate.commit(self.root,self.ident,self.report)['ok']);self.assert_completed()
    def test_each_post_commit_failure_returns_success_and_recovers_without_reprocessing(self):
        for phase in ('snapshot','lease','clear'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory()as directory:
                # Each phase gets an independent prepared copy, without mutating real state.
                root=Path(directory);shutil.copytree(self.root,root,dirs_exist_ok=True)
                original=gate.write
                def fail(path,value):
                    selected=path.name==self.ident+'.json'and value.get('committed_at')if phase=='snapshot'else path.name=='gates.json'and value.get('memory',{}).get('lease_until')is None if phase=='lease'else path.name=='review-cursor.json'and '_pending_commit'not in value
                    if selected:raise OSError('fictional post-commit failure')
                    return original(path,value)
                with patch.object(gate,'write',side_effect=fail):result=gate.commit(root,self.ident,self.report)
                self.assertTrue(result['ok']);self.assertTrue(result['cleanup_pending']);self.assertIsNone(gate.pending(root))
                self.assertTrue(gate.recover_checkpoint(root)['recovered'])
                self.assertNotIn('_pending_commit',gate.read(root/'data/automation/review-cursor.json',{}))
                self.assertTrue(gate.commit(root,self.ident,self.report)['already_committed'])
    def test_write_error_after_cursor_was_published_is_not_reported_as_rollback(self):
        original=gate.write
        def publish_then_fail(path,value):
            result=original(path,value)
            if path==self.cursor and '_pending_commit'in value:raise OSError('fictional failure after replacement')
            return result
        with patch.object(gate,'write',side_effect=publish_then_fail):result=gate.commit(self.root,self.ident,self.report)
        self.assertTrue(result['ok']);self.assertFalse(result['cleanup_pending']);self.assert_completed()
    def test_post_publication_read_failure_retains_confirmed_success(self):
        original_write,original_read=gate.write,gate.read;published=False
        def write(path,value):
            nonlocal published
            result=original_write(path,value)
            if path==self.cursor and '_pending_commit'in value:published=True
            return result
        def read(path,default):
            if published and path==self.cursor:raise OSError('fictional read failure after publication')
            return original_read(path,default)
        with patch.object(gate,'write',side_effect=write),patch.object(gate,'read',side_effect=read):result=gate.commit(self.root,self.ident,self.report)
        self.assertTrue(result['ok']);self.assertTrue(result['cleanup_pending']);self.assertTrue(gate.recover_checkpoint(self.root)['recovered'])
    def test_write_and_confirmation_read_failure_leave_an_idempotent_retry(self):
        original_write,original_read=gate.write,gate.read;published=False
        def write(path,value):
            nonlocal published
            result=original_write(path,value)
            if path==self.cursor and '_pending_commit'in value:
                published=True;raise OSError('fictional error after publication')
            return result
        def read(path,default):
            if published and path==self.cursor:raise OSError('fictional confirmation unavailable')
            return original_read(path,default)
        with patch.object(gate,'write',side_effect=write),patch.object(gate,'read',side_effect=read):
            with self.assertRaises(OSError):gate.commit(self.root,self.ident,self.report)
        self.assertIn('_pending_commit',gate.read(self.cursor,{}));self.assertIsNone(gate.pending(self.root))
        self.assertTrue(gate.commit(self.root,self.ident,self.report)['already_committed']);self.assert_completed()
    def test_inconsistent_snapshot_and_substring_only_report_are_rejected_before_publish(self):
        original=self.snapshot.read_bytes();value=gate.snapshot(self.root,self.ident);value['selected']['reports']={};gate.write(self.snapshot,value)
        with self.assertRaises(ValueError):gate.commit(self.root,self.ident,self.report)
        self.assertFalse(self.cursor.exists());self.snapshot.write_bytes(original)
        (self.root/self.report).write_text('Not-Review-Snapshot: '+self.ident)
        with self.assertRaises(ValueError):gate.commit(self.root,self.ident,self.report)
        self.assertFalse(self.cursor.exists())
    def test_recovery_does_not_read_changed_or_removed_original_sources_or_report(self):
        with self.fail_at('snapshot'):self.assertTrue(gate.commit(self.root,self.ident,self.report)['ok'])
        self.source.write_text('changed after commit');(self.root/self.report).unlink()
        with patch.object(gate,'inventory',side_effect=AssertionError('must not revalidate committed sources')):
            self.assertTrue(gate.commit(self.root,self.ident,self.report)['already_committed'])
        self.assert_completed();self.assertEqual(list(gate.pending(self.root)['selected']['reports']),[str(self.source.relative_to(self.root))])
    def test_missing_snapshot_can_be_rebuilt_from_the_published_receipt(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        self.snapshot.unlink();self.assertTrue(gate.recover_checkpoint(self.root)['recovered']);self.assert_completed()
    def test_conflicting_snapshot_is_preserved_and_new_model_wake_is_skipped(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        conflict=gate.snapshot(self.root,self.ident);conflict['selected']['reports']['extra']='fictional-version';gate.write(self.snapshot,conflict)
        before=self.snapshot.read_bytes();decision=gate.evaluate(self.root,'memory',self.now+timedelta(days=1))
        self.assertFalse(decision['wakeAgent']);self.assertTrue(decision['error']);self.assertEqual(self.snapshot.read_bytes(),before)
        self.assertIn('_pending_commit',gate.read(self.cursor,{}))
    def test_recovery_clears_only_matching_lease_and_preserves_unrelated_cursor_fields(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        cursor=gate.read(self.cursor,{});cursor['custom_metadata']={'keep':True};gate.write(self.cursor,cursor)
        gates={'memory':{'context':{'snapshot_id':'b'*64},'lease_until':(self.now+timedelta(hours=2)).isoformat()},'surf':{'keep':'unchanged'}}
        gate.write(self.root/'data/automation/gates.json',gates)
        self.assertTrue(gate.recover_checkpoint(self.root)['recovered'])
        self.assertEqual(gate.read(self.root/'data/automation/gates.json',{}),gates)
        self.assertEqual(gate.read(self.cursor,{})['custom_metadata'],{'keep':True})
    def test_dry_run_and_pause_do_not_repair_or_modify_a_pending_commit(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        files=[self.cursor,self.snapshot,self.root/'data/automation/gates.json'];before=[p.read_bytes()for p in files]
        self.assertFalse(gate.evaluate(self.root,'memory',self.now+timedelta(days=1),persist=False)['wakeAgent'])
        self.assertEqual([p.read_bytes()for p in files],before)
        gate.write(self.root/'data/automation/settings.json',{'paused':True,'max_outings':3})
        self.assertFalse(gate.evaluate(self.root,'memory',self.now+timedelta(days=1))['wakeAgent'])
        self.assertEqual(self.cursor.read_bytes(),before[0]);self.assertEqual(self.snapshot.read_bytes(),before[1])
    def test_preflight_recovers_locally_then_selects_only_new_sources(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        new=self.source.with_name('1500-surf.md');new.write_text('new fictional report')
        decision=gate.evaluate(self.root,'memory',self.now+timedelta(days=1));self.assertTrue(decision['wakeAgent'])
        self.assertTrue(decision['maintenance']['recovered'])
        selected=gate.snapshot(self.root,decision['context']['snapshot_id'])['selected']['reports']
        self.assertEqual(list(selected),[str(new.relative_to(self.root))])
    def test_failed_recovery_tick_keeps_lease_identity_for_the_next_retry(self):
        with self.fail_at('snapshot'):
            gate.commit(self.root,self.ident,self.report)
            first=gate.evaluate(self.root,'memory',self.now+timedelta(minutes=1))
        self.assertFalse(first['wakeAgent']);self.assertTrue(first['maintenance']['pending'])
        self.assertEqual(first['context']['snapshot_id'],self.ident)
        new=self.source.with_name('1500-surf.md');new.write_text('new fictional report')
        second=gate.evaluate(self.root,'memory',self.now+timedelta(minutes=2))
        self.assertTrue(second['wakeAgent']);self.assertTrue(second['maintenance']['recovered'])
        self.assertNotEqual(second['context']['snapshot_id'],self.ident)
    def test_cursor_versions_that_conflict_with_receipt_are_preserved_for_review(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        cursor=gate.read(self.cursor,{});cursor['reports'][str(self.source.relative_to(self.root))]='different-version'
        gate.write(self.cursor,cursor);before=self.cursor.read_bytes();snapshot_before=self.snapshot.read_bytes()
        self.assertTrue(gate.recover_checkpoint(self.root)['pending'])
        self.assertEqual(self.cursor.read_bytes(),before);self.assertEqual(self.snapshot.read_bytes(),snapshot_before)
        with self.assertRaises(ValueError):gate.commit(self.root,self.ident,self.report)
    def test_receipt_cleanup_error_after_successful_replacement_is_safe_to_retry(self):
        original=gate.write
        def clear_then_fail(path,value):
            result=original(path,value)
            if path==self.cursor and '_pending_commit'not in value:raise OSError('fictional failure after receipt cleanup')
            return result
        with patch.object(gate,'write',side_effect=clear_then_fail):result=gate.commit(self.root,self.ident,self.report)
        self.assertTrue(result['ok']);self.assertTrue(result['cleanup_pending']);self.assert_completed()
        self.assertFalse(gate.recover_checkpoint(self.root)['pending'])
        self.assertTrue(gate.commit(self.root,self.ident,self.report)['already_committed'])
    def test_new_commit_waits_for_previous_cleanup_and_old_retry_cannot_rewind_cursor(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        new=self.source.with_name('1500-surf.md');new.write_text('new fictional report');batch=gate.pending(self.root)
        gate.write(self.root/f"data/automation/reviews/{batch['id']}.json",batch)
        report=f"reports/2026-10-31/memory-review-{batch['id'][:12]}.md";(self.root/report).write_text('Review-Snapshot: '+batch['id'])
        with self.fail_at('snapshot'):
            with self.assertRaises(ValueError):gate.commit(self.root,batch['id'],report)
        self.assertTrue(gate.commit(self.root,batch['id'],report)['ok']);before=self.cursor.read_bytes()
        self.assertTrue(gate.commit(self.root,self.ident,self.report)['already_committed']);self.assertEqual(self.cursor.read_bytes(),before)
    def test_changed_episode_after_publication_stays_pending_after_cleanup(self):
        with Journal(self.root)as journal:row=journal.capture('fiction','原来的共同经历。','当时的回应。')
        batch=gate.pending(self.root);gate.write(self.root/f"data/automation/reviews/{batch['id']}.json",batch);gate.review(self.root,batch['id'])
        report=f"reports/2026-10-31/memory-review-{batch['id'][:12]}.md";(self.root/report).write_text('Review-Snapshot: '+batch['id'])
        original=gate.write
        def fail(path,value):
            if path.name==batch['id']+'.json'and value.get('committed_at'):raise OSError('fictional metadata failure')
            return original(path,value)
        with patch.object(gate,'write',side_effect=fail):gate.commit(self.root,batch['id'],report)
        with Journal(self.root)as journal:journal.update(row['id'],1,summary='后来明确更正了原记法。')
        self.assertTrue(gate.recover_checkpoint(self.root)['recovered'])
        self.assertEqual(gate.pending(self.root)['selected']['episodes'],{row['id']:2})
    def test_malformed_receipt_is_not_interpreted_as_an_empty_success(self):
        with self.fail_at('snapshot'):gate.commit(self.root,self.ident,self.report)
        cursor=gate.read(self.cursor,{});cursor['_pending_commit']['version']=99;gate.write(self.cursor,cursor);before=self.cursor.read_bytes()
        self.assertTrue(gate.recover_checkpoint(self.root)['pending']);self.assertEqual(self.cursor.read_bytes(),before)


class CheckpointProcessTest(unittest.TestCase):
    def prepare(self,root):
        source=root/'reports/2026-10-31/1200-surf.md';source.parent.mkdir(parents=True);source.write_text('fictional source')
        batch=gate.pending(root);gate.write(root/f"data/automation/reviews/{batch['id']}.json",batch)
        report=f"reports/2026-10-31/memory-review-{batch['id'][:12]}.md";(root/report).write_text('Review-Snapshot: '+batch['id'])
        scripts=root/'scripts';scripts.mkdir()
        for name in ('activity_gate.py','curiosity.py','fish_journal.py','personality.py'):shutil.copy2(Path(gate.__file__).with_name(name),scripts/name)
        return batch,report,['python3',str(scripts/'activity_gate.py'),'commit','--snapshot',batch['id'],'--report',report]
    def test_two_real_cli_commits_are_serialized_and_idempotent(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);batch,report,command=self.prepare(root)
            processes=[subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)for _ in range(2)]
            results=[]
            for process in processes:
                out,error=process.communicate(timeout=10);self.assertEqual(process.returncode,0,error);results.append(json.loads(out))
            self.assertTrue(all(r['ok']for r in results));self.assertEqual(sum(bool(r.get('already_committed'))for r in results),1)
            self.assertIsNone(gate.pending(root));self.assertNotIn('_pending_commit',gate.read(root/'data/automation/review-cursor.json',{}))
    def test_cli_failure_reports_unconfirmed_instead_of_asserting_cursor_unchanged(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);batch,report,command=self.prepare(root);(root/report).write_text('missing required marker')
            result=subprocess.run(command,capture_output=True,text=True);self.assertNotEqual(result.returncode,0)
            value=json.loads(result.stdout);self.assertFalse(value['ok']);self.assertEqual(value['commit_state'],'unconfirmed')
            self.assertNotIn('游标保持原样',result.stdout+result.stderr);self.assertIsNotNone(gate.pending(root))
    def test_real_process_exit_after_publication_recovers_without_rerunning_agent(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);source=root/'reports/2026-10-31/1200-surf.md';source.parent.mkdir(parents=True);source.write_text('fictional source')
            batch=gate.pending(root);gate.write(root/f"data/automation/reviews/{batch['id']}.json",batch)
            report=f"reports/2026-10-31/memory-review-{batch['id'][:12]}.md";(root/report).write_text('Review-Snapshot: '+batch['id'])
            script=root/'crash.py';script.write_text('import os,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nimport activity_gate as g\nroot=Path(sys.argv[2]);old=g.write\ndef crash(path,value):\n old(path,value)\n if path.name=="review-cursor.json"and"_pending_commit"in value:os._exit(71)\ng.write=crash\ng.commit(root,sys.argv[3],sys.argv[4])\n')
            result=subprocess.run(['python3',str(script),str(Path(gate.__file__).parent),str(root),batch['id'],report],capture_output=True,text=True)
            self.assertEqual(result.returncode,71);self.assertIsNone(gate.pending(root))
            self.assertTrue(gate.recover_checkpoint(root)['recovered']);self.assertTrue(gate.snapshot(root,batch['id'])['committed_at'])


if __name__=='__main__':unittest.main()
