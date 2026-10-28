from datetime import datetime,timedelta,timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import tempfile
import unittest
from unittest.mock import patch
import fish_budget as budget
import activity_gate

class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=datetime(2026,10,28,4,tzinfo=timezone.utc)
        with budget.Budget(self.root,self.now) as ledger:ledger.save({**ledger.settings(),'enabled':True,'daily_tokens':10000})
    def test_actual_settlement_counts_cache_once_and_returns_unused_reservation(self):
        with budget.Budget(self.root,self.now) as ledger:
            self.assertTrue(ledger.reserve('one',8000)['allowed'])
            ledger.settle('one',{'input_tokens':100,'cache_read_tokens':900,'cache_write_tokens':0,'output_tokens':30,'reasoning_tokens':20})
            self.assertEqual(ledger.snapshot()['used'],1030)
            ledger.settle('one',{'input_tokens':9999,'cache_read_tokens':0,'cache_write_tokens':0,'output_tokens':1})
            self.assertEqual(ledger.snapshot()['used'],1030)
    def test_concurrent_preflight_cannot_spend_the_same_allowance(self):
        def reserve(n):
            with budget.Budget(self.root,self.now) as ledger:return ledger.reserve(str(n),7000)['allowed']
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reserve,range(4)))
        self.assertEqual(sum(results),1)
        with budget.Budget(self.root,self.now) as ledger:self.assertEqual(ledger.snapshot()['used'],7000)
    def test_crash_and_unknown_usage_remain_charged_until_real_settlement(self):
        with budget.Budget(self.root,self.now) as ledger:ledger.reserve('lost',8000)
        with budget.Budget(self.root,self.now+timedelta(minutes=21)) as ledger:
            self.assertEqual(ledger.snapshot()['unknown'],8000)
            self.assertFalse(ledger.reserve('new',3000)['allowed'])
            ledger.settle('lost',None,error=True);self.assertEqual(ledger.snapshot()['used'],8000)
            ledger.settle('lost',dict(zip(budget.BUCKETS,[200,100,0,50])))
            self.assertEqual(ledger.snapshot()['used'],350)
    def test_midnight_starts_a_new_allowance_without_moving_yesterdays_request(self):
        with budget.Budget(self.root,self.now) as ledger:ledger.reserve('yesterday',10000)
        with budget.Budget(self.root,self.now+timedelta(days=1)) as ledger:
            self.assertEqual(ledger.snapshot()['remaining'],10000)
            ledger.settle('yesterday',dict(zip(budget.BUCKETS,[200,100,0,50])))
            self.assertEqual(ledger.snapshot()['used'],0)
    def test_chat_and_unattributed_auxiliary_usage_do_not_consume_background_allowance(self):
        with budget.Budget(self.root,self.now) as ledger:
            ledger.reserve('background',10000)
            self.assertTrue(ledger.reserve('human',30000,source='chat')['allowed'])
            ledger.reserve('aux',30000,source='unassigned',enforce=False)
            self.assertEqual(ledger.snapshot()['used'],10000)
            self.assertFalse(ledger.reserve('background',1)['allowed'])
    def test_auxiliary_observation_can_exceed_quota_but_stops_next_main_request(self):
        with budget.Budget(self.root,self.now) as ledger:
            ledger.reserve('aux',14000,task='aux:compression',enforce=False)
            self.assertEqual(ledger.snapshot()['used'],14000)
            self.assertFalse(ledger.reserve('main',1)['allowed'])
    def test_background_review_and_titles_count_even_when_parent_is_chat(self):
        with budget.Budget(self.root,self.now) as ledger:
            ledger.reserve('review',5000,source='chat',task='aux:background_review',enforce=False)
            ledger.reserve('title',1000,source='unassigned',task='aux:title_generation',enforce=False)
            ledger.reserve('vision',2000,source='chat',task='aux:vision',enforce=False)
            self.assertEqual(ledger.snapshot()['used'],6000)
    def test_settings_conflicts_do_not_overwrite_new_limit(self):
        with budget.Budget(self.root,self.now) as ledger:
            old=ledger.settings();ledger.save({**old,'daily_tokens':20000})
            with self.assertRaises(ValueError):ledger.save({**old,'daily_tokens':30000})
            for value in [True,9999,'10000',200000001]:
                with self.assertRaises(ValueError):ledger.save({**ledger.settings(),'daily_tokens':value})
    def test_gate_and_dry_run_skip_before_model_when_allowance_is_used(self):
        with budget.Budget(self.root,self.now) as ledger:ledger.reserve('used',10000)
        for persist in (False,True):self.assertFalse(activity_gate.evaluate(self.root,'surf',self.now,persist=persist)['wakeAgent'])
    def test_request_cap_preserves_tool_reasoning_messages_and_never_rewrites_chat(self):
        request={'messages':[{'role':'assistant','reasoning_content':'preserve me','tool_calls':[{'id':'call'}]}],'max_tokens':20000}
        prepared,estimate=budget.prepare(request)
        self.assertEqual(prepared['max_tokens'],8192);self.assertEqual(prepared['messages'],request['messages']);self.assertEqual(request['max_tokens'],20000)
        self.assertGreater(estimate,8192)

class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        spec=importlib.util.spec_from_file_location('budget_plugin',Path(__file__).resolve().parents[1]/'plugins/fish-budget/__init__.py')
        plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin);self.guard=plugin.Guard(self.root,budget)
        with budget.Budget(self.root) as ledger:ledger.save({**ledger.settings(),'enabled':True,'daily_tokens':10000})
    def test_block_is_a_completed_local_response_without_downstream_call(self):
        with budget.Budget(self.root) as ledger:ledger.reserve('used',10000)
        with patch.object(self.guard,'usage',return_value=None):
            downstream=unittest.mock.Mock();response=self.guard.execute({'messages':[]},downstream,platform='cron')
        downstream.assert_not_called();self.assertEqual(response.choices[0].finish_reason,'stop');self.assertEqual(response.model,'local-budget')
    def test_storage_failure_is_closed_for_background_and_open_for_human_chat(self):
        downstream=unittest.mock.Mock(return_value='real reply')
        with patch.object(budget,'Budget',side_effect=OSError('private error')):
            self.assertEqual(self.guard.execute({},downstream,platform='cron').model,'local-budget')
            self.assertEqual(self.guard.execute({},downstream,platform='bigfish'),'real reply')
        downstream.assert_called_once()
    def test_provider_failure_remains_unknown_and_is_not_retried_by_guard(self):
        downstream=unittest.mock.Mock(side_effect=RuntimeError('provider failed'))
        with self.assertRaises(RuntimeError):self.guard.execute({},downstream,platform='cron')
        downstream.assert_called_once()
        with budget.Budget(self.root) as ledger:self.assertGreater(ledger.snapshot()['unknown'],0)

    def test_success_settles_only_once_and_never_persists_prompt_or_key(self):
        secret='synthetic-private-prompt-value';request={'messages':[{'role':'user','content':secret}],'max_tokens':20000}
        usage=dict(zip(budget.BUCKETS,[100,900,0,30]));downstream=unittest.mock.Mock(return_value=object())
        with patch.object(self.guard,'usage',return_value=usage):self.guard.execute(request,downstream,platform='cron',session_id=secret)
        downstream.assert_called_once();self.assertLessEqual(downstream.call_args.args[0]['max_tokens'],8192)
        with budget.Budget(self.root) as ledger:
            self.assertEqual(ledger.snapshot()['used'],1030)
            self.assertNotIn(secret,str([dict(r)for r in ledger.db.execute('SELECT * FROM requests')]))

    def test_auxiliary_attempt_pairs_include_retries_and_maintain_unknown_usage(self):
        context={'api_request_id':'aux-id','retry_count':0,'started_at':1000,'platform':'cron','aux_task':'compression','request_messages':[],'max_tokens':1000}
        self.guard.pre_auxiliary(**context);self.guard.post_auxiliary(**context,usage=dict(zip(budget.BUCKETS,[100,900,0,30])))
        retry={**context,'retry_count':1,'started_at':1001};self.guard.pre_auxiliary(**retry);self.guard.post_auxiliary(**retry,usage=None,error='failure')
        with budget.Budget(self.root) as ledger:
            value=ledger.snapshot();self.assertGreater(value['used'],1030);self.assertGreater(value['unknown'],0)
            self.assertEqual(sum(r['calls']for r in value['groups']),2)

if __name__=='__main__':unittest.main()
