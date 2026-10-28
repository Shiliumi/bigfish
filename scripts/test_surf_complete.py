from datetime import datetime,timedelta
from pathlib import Path
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import curiosity
import personality
import surf_complete as finish

class CompleteTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=datetime(2026,10,28,12,tzinfo=ZoneInfo('Asia/Shanghai'))
        run=curiosity.begin(self.root,now=self.now)['run'];self.run=run['id']
        self.payload={'run_id':self.run,'report':{'path':'reports/2026-10-28/1205-surf.md','content':'实际阅读了 https://example.org/build ，这篇作品的机关收纳很巧妙，还想知道怎么驱动。'},
            'pages':[{'url':'https://example.org/build','title':'积木小厨房','read_at':(self.now+timedelta(minutes=2)).isoformat()}],
            'observations':[{'page_index':0,'read_depth':'body','observation':'这个作品把小机关收进了厨房的抽屉。','candidate_trait':'我似乎很喜欢有机关的小作品。','reason':'抽屉收纳的反差让我想继续看原理。'}],
            'threads':[{'question':'这个积木厨房的抽屉机关怎么驱动？','why':'实际读到收纳设计，还想知道怎么驱动。','evidence_observations':[0]}],
            'preference':{'action':'trial','id':'tiny-builds','text':'我似乎更喜欢有小机关的积木作品。','reason':'实际看到了抽屉机关，还想继续看看。','evidence_observations':[0]},
            'outcome':'want_more','reason':'作品的具体机关让我想继续看看驱动方式。',
            'share':{'page_index':0,'text':'这个小厨房居然把机关塞进抽屉里了，有点东西。','why_share':'具体的收纳反差很有意思，想一起看看。'}}
    def complete(self,data=None):return finish.complete(self.root,data or self.payload,self.now+timedelta(minutes=5))
    def test_one_submission_links_real_observation_threads_preference_and_optional_share(self):
        result=self.complete();self.assertEqual(len(result['observation_ids']),1)
        self.assertEqual(curiosity.state(self.root)['runs'][0]['status'],'finished')
        self.assertEqual(curiosity.state(self.root)['threads'][0]['evidence_ids'],result['observation_ids'])
        self.assertEqual(personality.trial_state(self.root)['trials'][0]['signals'][0]['id'],result['observation_ids'][0])
        letter=json.loads((self.root/'data/outbox'/f'{self.run}.json').read_text());self.assertEqual(letter['source_url'],self.payload['pages'][0]['url'])
        receipt=json.loads((self.root/'data/surf-completions'/f'{self.run}.json').read_text());self.assertNotIn('content',receipt['writes'][0])
    def test_identical_retry_is_idempotent_and_different_content_cannot_replace_it(self):
        self.complete();self.assertTrue(self.complete()['already_submitted'])
        self.assertEqual(len(personality.observations(self.root)),1)
        self.assertEqual(len(list((self.root/'data/outbox').glob('*.json'))),1)
        different=copy.deepcopy(self.payload);different['reason']='换一个理由也不能覆盖已经提交的记录。'
        with self.assertRaises(ValueError):self.complete(different)
    def test_user_can_stop_an_interest_during_an_outing_without_losing_the_read_report(self):
        from fish_interest import change,load_controls
        first=self.complete();thread=curiosity.state(self.root)['threads'][0]
        later=self.now+timedelta(hours=3);run=curiosity.begin(self.root,thread['id'],later)['run']
        change(self.root,{'id':thread['id'],'choice':'retire','revision':0},later+timedelta(minutes=1));saved=load_controls(self.root)
        data=copy.deepcopy(self.payload);data['run_id']=run['id'];data['report']['path']='reports/2026-10-28/1505-surf.md';data['pages'][0]['read_at']=(later+timedelta(minutes=2)).isoformat();data['preference']=None
        result=finish.complete(self.root,data,later+timedelta(minutes=5))
        self.assertFalse(result['share_queued']);self.assertEqual(result['skipped_threads'],1);self.assertTrue((self.root/data['report']['path']).exists())
        self.assertEqual(len(personality.observations(self.root)),2);self.assertEqual(load_controls(self.root),saved)
    def test_invalid_last_step_rolls_back_all_staged_changes(self):
        data=copy.deepcopy(self.payload);data['share']['page_index']=4
        with self.assertRaises(ValueError):self.complete(data)
        self.assertFalse((self.root/self.payload['report']['path']).exists());self.assertEqual(personality.observations(self.root),[])
        self.assertEqual(curiosity.state(self.root)['runs'][0]['status'],'started')
    def test_crash_after_report_write_recovers_without_duplicate_share(self):
        actual=finish.write_bytes
        def crash(path,value):
            if path==self.root/'data/personality/observations.jsonl':raise OSError('simulated interruption')
            return actual(path,value)
        with patch.object(finish,'write_bytes',side_effect=crash):
            with self.assertRaises(OSError):self.complete()
        self.assertTrue((self.root/self.payload['report']['path']).exists())
        self.assertFalse((self.root/'data/outbox'/f'{self.run}.json').exists())
        self.assertTrue(self.complete()['already_submitted']);self.assertEqual(len(personality.observations(self.root)),1)
    def test_crash_conflicting_external_edit_is_never_overwritten(self):
        actual=finish.write_bytes
        def crash(path,value):
            if path==self.root/'data/personality/observations.jsonl':raise OSError('interrupted')
            return actual(path,value)
        with patch.object(finish,'write_bytes',side_effect=crash):
            with self.assertRaises(OSError):self.complete()
        p=self.root/'data/surf-state.json';p.write_text('{"visited":[],"external":"new edit"}')
        with self.assertRaises(ValueError):self.complete()
        self.assertIn('new edit',p.read_text())
    def test_recovery_preserves_a_choice_made_after_the_prepared_receipt(self):
        from fish_interest import change,load_controls
        self.complete();thread=curiosity.state(self.root)['threads'][0];later=self.now+timedelta(hours=3)
        run=curiosity.begin(self.root,thread['id'],later)['run'];data=copy.deepcopy(self.payload);data['run_id']=run['id'];data['report']['path']='reports/2026-10-28/1505-surf.md';data['pages'][0]['read_at']=(later+timedelta(minutes=2)).isoformat();data['preference']=None
        actual=finish.write_bytes
        def crash(path,value):
            if path==self.root/'data/personality/observations.jsonl':raise OSError('interrupted before observations')
            return actual(path,value)
        with patch.object(finish,'write_bytes',side_effect=crash):
            with self.assertRaises(OSError):finish.complete(self.root,data,later+timedelta(minutes=5))
        change(self.root,{'id':thread['id'],'choice':'retire','revision':0},later+timedelta(minutes=6));saved=load_controls(self.root)
        result=finish.complete(self.root,data,later+timedelta(minutes=7));self.assertTrue(result['already_submitted']);self.assertEqual(load_controls(self.root),saved)
        letter=json.loads((self.root/'data/outbox'/f'{run["id"]}.json').read_text());self.assertEqual(letter['interest_id'],thread['id'])
    def test_blocked_read_creates_no_observation_or_share(self):
        data=copy.deepcopy(self.payload);data.update(pages=[],observations=[],threads=[],preference=None,share=None,outcome='blocked',reason='公开入口目前要求登录，没有实际读到正文。')
        result=self.complete(data);self.assertEqual(result['observation_ids'],[]);self.assertFalse(result['share_queued'])
    def test_old_evidence_title_only_and_report_overwrite_are_rejected(self):
        data=copy.deepcopy(self.payload);data['pages'][0]['read_at']=(self.now-timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):self.complete(data)
        data=copy.deepcopy(self.payload);data['observations'][0]['read_depth']='title'
        with self.assertRaises(ValueError):self.complete(data)
        p=self.root/self.payload['report']['path'];p.parent.mkdir(parents=True);p.write_text('existing report')
        with self.assertRaises(ValueError):self.complete()
        self.assertEqual(p.read_text(),'existing report')
    def test_sources_cannot_escape_project_via_report_symlink(self):
        outside=self.root/'external';outside.mkdir();(self.root/'reports').symlink_to(outside)
        # An internal directory is permitted, but an external symlink is not.
        with tempfile.TemporaryDirectory() as other:
            (self.root/'reports').unlink();(self.root/'reports').symlink_to(other)
            with self.assertRaises(ValueError):self.complete()
    def test_real_followup_letter_carries_verified_existing_thread_and_run(self):
        first=self.complete();thread=first['thread_ids'][0];later=self.now+timedelta(hours=3)
        second=curiosity.begin(self.root,thread,later)['run'];data=copy.deepcopy(self.payload)
        data.update(run_id=second['id'],threads=[],preference=None)
        data['report']={'path':'reports/2026-10-28/1505-surf.md','content':'继续实际阅读 https://example.org/next ，终于看到抽屉转动机构。'}
        data['pages'][0].update(url='https://example.org/next',read_at=(later+timedelta(minutes=2)).isoformat())
        finish.complete(self.root,data,later+timedelta(minutes=5))
        letter=json.loads((self.root/'data/outbox'/f"{second['id']}.json").read_text())
        self.assertEqual(letter['thread_id'],thread);self.assertEqual(letter['browse_run_id'],second['id'])
        self.assertIn('抽屉机关',letter['thread_question'])

if __name__=='__main__':unittest.main()
