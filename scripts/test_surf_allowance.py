from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from zoneinfo import ZoneInfo
import importlib.util
import json
import tempfile
import unittest
import activity_gate
import fish_budget as budget


class SurfCloseoutTest(unittest.TestCase):
    def setUp(self):
        self.identity=SimpleNamespace(job_name='fish-surf',job_id='surf',execution_id='fire')
        self.context={'platform':'cron','api_mode':'chat_completions','api_call_count':13}
        self.request={'tools':[{'type':'function','function':{'name':n}}for n in ('browser_exec','web_search','web_extract','terminal','write_file','read_file','patch')],
            'messages':[{'role':'assistant','reasoning_content':'synthetic reason','tool_calls':[{'id':'call-1'}]},
                        {'role':'tool','tool_call_id':'call-1','content':'synthetic actual reading'}],
            'model':'example-model','max_tokens':3000,'parallel_tool_calls':True}
    def test_closeout_preserves_local_tools_history_reasoning_and_original_request(self):
        before=deepcopy(self.request);result=budget.surf_closeout(self.request,self.identity,self.context)
        self.assertEqual(self.request,before)
        self.assertEqual([t['function']['name']for t in result['tools']],['terminal','write_file','read_file','patch'])
        self.assertEqual(result['messages'][:-1],before['messages'])
        self.assertEqual(result['messages'][-1],{'role':'user','content':budget.SURF_CLOSEOUT})
        self.assertEqual(result['max_tokens'],3000);self.assertTrue(result['parallel_tool_calls'])
        self.assertIn('blocked',budget.SURF_CLOSEOUT);self.assertIn('不表示结果已保存',budget.SURF_CLOSEOUT)
    def test_only_trusted_surf_identity_and_real_call_count_select_closeout(self):
        for identity,context in [(None,self.context),(SimpleNamespace(job_name='fish-memory'),self.context),
                (SimpleNamespace(job_name='fish-study-buddy'),self.context),(self.identity,{**self.context,'api_call_count':12}),
                (self.identity,{**self.context,'api_call_count':'13'}),(self.identity,{**self.context,'api_call_count':True}),
                (self.identity,{**self.context,'api_mode':'codex_responses'})]:
            with self.subTest(identity=identity,context=context):self.assertIs(budget.surf_closeout(self.request,identity,context),self.request)
    def test_toolless_fallback_and_already_narrowed_requests_are_not_rewritten(self):
        for tools in ([],self.request['tools'][3:],self.request['tools'][:3]):
            request={**self.request,'tools':tools}
            self.assertIs(budget.surf_closeout(request,self.identity,self.context),request)
    def test_forced_network_choice_is_released_but_local_choice_is_preserved(self):
        for name in ('browser_exec','terminal'):
            choice={'type':'function','function':{'name':name}}
            result=budget.surf_closeout({**self.request,'tool_choice':choice},self.identity,self.context)
            self.assertEqual(result['tool_choice'],'auto'if name=='browser_exec'else choice)
    def test_guard_accounts_for_the_changed_request_and_does_not_touch_chat(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);path=Path(__file__).resolve().parents[1]/'plugins/fish-budget/__init__.py'
            spec=importlib.util.spec_from_file_location('closeout_guard',path);plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)
            guard=plugin.Guard(root,budget,cron_identity=lambda:self.identity);downstream=Mock(return_value=object())
            with patch.object(guard,'usage',return_value=dict(zip(budget.BUCKETS,[10,20,0,5]))):
                guard.execute(self.request,downstream,session_id='cron_surf',**self.context)
            changed=downstream.call_args.args[0];self.assertEqual(changed['messages'][-1]['content'],budget.SURF_CLOSEOUT)
            with budget.Budget(root)as ledger:
                row=ledger.db.execute("select reserved,charged from requests where task='main'").fetchone()
                self.assertEqual(row['reserved'],budget.estimate_request(changed)+changed['max_tokens']);self.assertEqual(row['charged'],35)
            downstream.reset_mock()
            with patch.object(guard,'usage',return_value=None):guard.execute(self.request,downstream,platform='bigfish',session_id='chat',api_call_count=20)
            self.assertEqual(downstream.call_args.args[0],self.request)


class SurfAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=datetime(2026,11,1,15,tzinfo=ZoneInfo('Asia/Shanghai'))
        self.jobs=[{'name':'fish-surf','id':'surf','enabled':True},
                   {'name':'fish-memory','id':'memory','enabled':True,'next_run_at':self.now.replace(hour=22,minute=30).isoformat()},
                   {'name':'fish-study-buddy','id':'buddy','enabled':True}]
        self.save_jobs();self.snapshot={'settings':{'enabled':True},'remaining':1_200_000}
    def save_jobs(self):
        file=self.root/'.hermes/cron/jobs.json';file.parent.mkdir(parents=True,exist_ok=True);file.write_text(json.dumps({'jobs':self.jobs}))
    def audit(self,rows):
        file=self.root/'.hermes/cron/usage_audit.jsonl';file.write_text('\n'.join(json.dumps(r)for r in rows))
    def row(self,name,cost,hours=1,**extra):
        return {'job_id':name,'total_tokens':cost,'ts':(self.now-timedelta(hours=hours)).isoformat(),**extra}
    def test_recent_costs_leave_later_memory_headroom_without_changing_ledger_or_jobs(self):
        self.audit([self.row('surf',736245,6),self.row('surf',666559,3),self.row('surf',444594),self.row('memory',408354,17),self.row('memory',44538,16)])
        before=(self.root/'.hermes/cron/jobs.json').read_bytes();self.snapshot['remaining']=1_000_000
        result=budget.surf_admission(self.root,self.snapshot,self.now)
        self.assertEqual(result['outing_estimate'],736245);self.assertEqual(result['later_memory_estimate'],408354)
        self.assertFalse(result['allowed']);self.assertEqual(before,(self.root/'.hermes/cron/jobs.json').read_bytes())
        self.assertFalse((self.root/'data/automation/requests.sqlite3').exists())
    def test_floor_ignores_bad_future_stale_wrong_job_and_old_fourth_sample(self):
        self.audit([self.row('surf',900000,4),self.row('surf',100,3),self.row('surf',200,2),self.row('surf',300),
                    self.row('surf',9999999,-1),self.row('surf',9999999,24*15),self.row('surf',True),self.row('buddy',9999999),{'ts':'bad'},[],{'ts':42}])
        result=budget.surf_admission(self.root,self.snapshot,self.now)
        self.assertEqual(result['required'],800000);self.assertTrue(result['allowed'])
    def test_disabled_unlimited_or_tomorrows_memory_does_not_hold_headroom(self):
        self.assertIsNone(budget.surf_admission(self.root,{'settings':{'enabled':False}},self.now))
        for change in ({'enabled':False},{'next_run_at':(self.now+timedelta(days=1)).isoformat()},{'next_run_at':(self.now-timedelta(hours=1)).isoformat()}):
            original=self.jobs[1].copy();self.jobs[1].update(change);self.save_jobs()
            self.assertEqual(budget.surf_admission(self.root,self.snapshot,self.now)['later_memory_estimate'],0)
            self.jobs[1]=original
    def test_no_history_still_rejects_a_token_sliver_and_accepts_the_boundary(self):
        for remaining,allowed in ((799999,False),(800000,True)):
            self.snapshot['remaining']=remaining;result=budget.surf_admission(self.root,self.snapshot,self.now);self.assertEqual(result['allowed'],allowed)
    def test_duplicate_identity_and_ambiguous_schedule_are_not_guessed(self):
        self.jobs.append(self.jobs[0].copy());self.save_jobs()
        with self.assertRaises(ValueError):budget.surf_admission(self.root,self.snapshot,self.now)
        self.jobs.pop();self.jobs[1]['next_run_at']='2026-11-01T22:30:00';self.save_jobs()
        with self.assertRaises(ValueError):budget.surf_admission(self.root,self.snapshot,self.now)
    def test_gate_skips_before_model_without_consuming_outing_or_review_sources(self):
        with budget.Budget(self.root,self.now)as ledger:
            ledger.save({**ledger.settings(),'enabled':True,'daily_tokens':1_000_000});ledger.reserve('used',300_000)
        with patch('curiosity.agenda',return_value={'can_go':True,'rest_reason':'','used_today':0,'daily_limit':3}):
            value=activity_gate.evaluate(self.root,'surf',self.now,persist=False)
        self.assertFalse(value['wakeAgent']);self.assertEqual(value['admission']['required'],800000)
        self.assertIn('今晚记忆整理',value['reason']);self.assertFalse((self.root/'data/curiosity/state.json').exists())
        self.assertFalse((self.root/'data/automation/review-cursor.json').exists());self.assertFalse((self.root/'data/automation/gates.json').exists())


if __name__=='__main__':unittest.main()
