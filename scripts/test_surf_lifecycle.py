from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import curiosity
import fish_budget
import surf_lifecycle as lifecycle
import activity_gate
import surf_complete


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.now=datetime(2026,10,29,4,tzinfo=timezone.utc);folder=self.root/'.hermes/cron';folder.mkdir(parents=True)
        (folder/'jobs.json').write_text(json.dumps({'jobs':[{'id':'fixture-job','name':'fish-surf'}]}))
        self.db=sqlite3.connect(folder/'executions.db');self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE executions(id TEXT,job_id TEXT,status TEXT,claimed_at TEXT,started_at TEXT,finished_at TEXT)')
        self.execution()
        self.identity=SimpleNamespace(job_name='fish-surf',job_id='fixture-job',execution_id='fixture-execution')
        self.env={'HERMES_CRON_SESSION':'1','HERMES_SESSION_ID':'fixture-session'}
    def execution(self,ident='fixture-execution',status='running',end=None,job='fixture-job'):
        self.db.execute('INSERT INTO executions VALUES(?,?,?,?,?,?)',(ident,job,status,(self.now-timedelta(minutes=1)).isoformat(),(self.now-timedelta(minutes=1)).isoformat(),end.isoformat()if end else None));self.db.commit()
    def begin(self):
        fish_budget.record_cron_owner(self.root,'fixture-session',self.identity)
        with patch.dict(os.environ,self.env):return curiosity.begin(self.root,now=self.now)['run']
    def terminal(self,status='completed'):
        self.db.execute('UPDATE executions SET status=?,finished_at=? WHERE id=?',(status,(self.now+timedelta(minutes=5)).isoformat(),'fixture-execution'));self.db.commit()
    def test_trusted_matching_session_and_execution_bind_the_outing(self):
        run=self.begin();self.assertEqual(run['cron_execution'],{'job_id':'fixture-job','execution_id':'fixture-execution'})
        before=(self.root/'.hermes/cron/executions.db').read_bytes()
        with patch.dict(os.environ,self.env):self.assertTrue(lifecycle.current_owner(self.root,self.now))
        self.assertEqual((self.root/'.hermes/cron/executions.db').read_bytes(),before)
    def test_missing_foreign_or_unscoped_identity_never_guesses_a_running_owner(self):
        with patch.dict(os.environ,self.env):self.assertIsNone(lifecycle.current_owner(self.root,self.now))
        fish_budget.record_cron_owner(self.root,'fixture-session',self.identity)
        for env in [{'HERMES_SESSION_ID':'other-session'},{'HERMES_CRON_SESSION':''},{'HERMES_SESSION_ID':''}]:
            with patch.dict(os.environ,{**self.env,**env}):self.assertIsNone(lifecycle.current_owner(self.root,self.now))
        foreign=SimpleNamespace(job_name='fish-memory',job_id='fixture-job',execution_id='fixture-execution')
        fish_budget.record_cron_owner(self.root,'another-session',foreign)
        with patch.dict(os.environ,{**self.env,'HERMES_SESSION_ID':'another-session'}):self.assertIsNone(lifecycle.current_owner(self.root,self.now))
    def test_live_execution_is_preserved_even_when_very_old(self):
        self.begin();before=curiosity.state(self.root)
        result=lifecycle.reconcile(self.root,self.now+timedelta(days=2));self.assertEqual(result['interrupted'],0);self.assertEqual(curiosity.state(self.root),before)
    def test_each_terminal_status_marks_missing_receipt_without_inventing_outcome(self):
        for status in ['completed','failed','unknown']:
            with self.subTest(status=status):
                self.db.execute("UPDATE executions SET status='running',finished_at=NULL");self.db.commit()
                curiosity.atomic(self.root/'data/curiosity/state.json',{'threads':[],'runs':[]});run=self.begin();self.terminal(status)
                result=lifecycle.reconcile(self.root,self.now+timedelta(hours=1));self.assertEqual(result['interrupted'],1)
                saved=curiosity.state(self.root)['runs'][0];self.assertEqual(saved['status'],'interrupted');self.assertIsNone(saved['outcome']);self.assertEqual(saved['owner_evidence'],'bound')
                self.assertFalse((self.root/'reports').exists());self.assertFalse((self.root/'data/personality').exists());self.assertEqual(curiosity.recent_count(curiosity.state(self.root),self.now,self.root),1)
                self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=2))['interrupted'],0)
    def test_other_job_and_corrupt_audit_do_not_close_source(self):
        self.begin();before=curiosity.state(self.root);self.terminal();self.db.execute("UPDATE executions SET job_id='foreign-job'");self.db.commit()
        self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=1))['interrupted'],0);self.assertEqual(curiosity.state(self.root),before)
        (self.root/'.hermes/cron/jobs.json').write_text('{broken')
        with self.assertRaises(ValueError):lifecycle.reconcile(self.root,self.now+timedelta(hours=1))
        self.assertEqual(curiosity.state(self.root),before)
    def test_invalid_optional_owner_metadata_does_not_prevent_an_unbound_manual_outing(self):
        fish_budget.record_cron_owner(self.root,'fixture-session',self.identity)
        next((self.root/'data/curiosity/owners').glob('*.json')).write_text('[]')
        with patch.dict(os.environ,self.env):run=curiosity.begin(self.root,now=self.now)['run']
        self.assertNotIn('cron_execution',run)
    def test_foreign_audit_and_receipt_symlinks_are_refused_without_state_changes(self):
        self.begin();before=curiosity.state(self.root)
        with tempfile.TemporaryDirectory()as external:
            destination=Path(external)/'jobs.json';destination.write_text('{"jobs":[]}')
            file=self.root/'.hermes/cron/jobs.json';file.unlink();file.symlink_to(destination)
            with self.assertRaises(ValueError):lifecycle.reconcile(self.root,self.now+timedelta(hours=1))
            folder=self.root/'data/surf-completions';folder.symlink_to(external)
            with self.assertRaises(ValueError):surf_complete.recover(self.root)
        self.assertEqual(curiosity.state(self.root),before)
    def test_legacy_repair_is_explicit_unique_and_refuses_any_live_execution(self):
        run=curiosity.begin(self.root,now=self.now)['run'];self.assertNotIn('cron_execution',run);self.terminal()
        self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=1))['interrupted'],0)
        self.execution('another-execution',status='running')
        self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=1),legacy=True)['interrupted'],0)
        self.db.execute("DELETE FROM executions WHERE id='another-execution'");self.db.commit()
        self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=1),legacy=True)['interrupted'],1)
        self.assertEqual(curiosity.state(self.root)['runs'][0]['owner_evidence'],'legacy_time_window')
    def test_ambiguous_legacy_window_or_future_finish_is_not_terminal_proof(self):
        curiosity.begin(self.root,now=self.now);self.terminal();self.execution('duplicate',status='completed',end=self.now+timedelta(minutes=10))
        self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=1),legacy=True)['interrupted'],0)
        self.db.execute("DELETE FROM executions WHERE id='duplicate'");self.db.commit()
        self.assertEqual(lifecycle.reconcile(self.root,self.now,legacy=True)['interrupted'],0)
    def test_receipt_and_pending_plan_are_preserved_before_any_status_change(self):
        run=self.begin();self.terminal();folder=self.root/'data/surf-completions';folder.mkdir();receipt=folder/(run['id']+'.json');receipt.write_text('{"status":"committed"}')
        self.assertEqual(lifecycle.reconcile(self.root,self.now+timedelta(hours=1))['interrupted'],0)
        receipt.write_text('{"status":"prepared"}');before=curiosity.state(self.root)
        with self.assertRaises(ValueError):lifecycle.reconcile(self.root,self.now+timedelta(hours=1))
        self.assertEqual(curiosity.state(self.root),before)
    def test_gate_reconciles_before_agenda_but_dry_run_preserves_outings(self):
        self.begin();self.terminal();now=self.now+timedelta(hours=3)
        activity_gate.evaluate(self.root,'surf',now,persist=False);self.assertEqual(curiosity.state(self.root)['runs'][0]['status'],'started')
        decision=activity_gate.evaluate(self.root,'surf',now);self.assertEqual(curiosity.state(self.root)['runs'][0]['status'],'interrupted');self.assertEqual(decision['maintenance']['interrupted'],1)
    def test_budget_middleware_uses_trusted_context_not_request_payload(self):
        spec=importlib.util.spec_from_file_location('lifecycle_budget',Path(__file__).resolve().parents[1]/'plugins/fish-budget/__init__.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        guard=module.Guard(self.root,fish_budget,cron_identity=lambda:self.identity)
        response=SimpleNamespace(usage=None)
        guard.execute({'messages':[{'role':'user','content':'fictional payload claims execution=foreign'}]},lambda request:response,platform='cron',session_id='fixture-session')
        with patch.dict(os.environ,self.env):self.assertTrue(lifecycle.current_owner(self.root,self.now))
        owner_file=next((self.root/'data/curiosity/owners').glob('*.json'));self.assertNotIn('fixture-session',owner_file.read_text());self.assertEqual(set(json.loads(owner_file.read_text())),{'job_id','execution_id'})


if __name__=='__main__':unittest.main()
