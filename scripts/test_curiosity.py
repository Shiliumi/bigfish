import importlib.util
from pathlib import Path
import tempfile
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import json
import unittest
s=importlib.util.spec_from_file_location('curiosity',Path(__file__).with_name('curiosity.py'));c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class CuriosityTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.now=datetime(2026,10,27,12,tzinfo=ZoneInfo('Asia/Shanghai'));p=self.root/'data/personality';p.mkdir(parents=True);self.obs={'id':'obs-real','url':'https://example.org/read','observation':'一件实际读到的有趣事情','seen_at':(self.now-timedelta(days=1)).isoformat(),'report_path':'reports/2026-10-26/new-surf.md'};(p/'observations.jsonl').write_text(json.dumps(self.obs)+'\n');self.proposal={'question':'他怎么把积木做成会动的厨房？','why':'实际读到有人改厨房，还想知道机关怎么收纳','evidence_ids':['obs-real']}
  self.obs['read_depth']='body';(p/'observations.jsonl').write_text(json.dumps(self.obs)+'\n');report=self.root/self.obs['report_path'];report.parent.mkdir(parents=True);report.write_text('真实阅读记录 '+self.obs['url']);(self.root/'data/surf-state.json').write_text(json.dumps({'visited':[{'url':self.obs['url'],'read_at':self.obs['seen_at'],'report':self.obs['report_path']}]}))
 def test_questions_require_observed_evidence_and_stay_separate_from_personality(self):
  with self.assertRaises(ValueError):c.remember(self.root,{**self.proposal,'evidence_ids':['invented']},self.now)
  thread=c.remember(self.root,self.proposal,self.now)[0];self.assertEqual(c.agenda(self.root,self.now)['threads'][0]['id'],thread['id']);self.assertFalse((self.root/'.hermes/SOUL.md').exists())
 def test_three_real_outings_not_five_mandatory_tasks_and_quiet_hours(self):
  self.assertFalse(c.agenda(self.root,self.now.replace(hour=23))['can_go'])
  self.assertTrue(c.begin(self.root,now=self.now)['started']);self.assertFalse(c.begin(self.root,now=self.now+timedelta(minutes=10))['started'])
  self.assertTrue(c.begin(self.root,now=self.now+timedelta(hours=2))['started']);self.assertTrue(c.begin(self.root,now=self.now+timedelta(hours=4))['started']);self.assertFalse(c.begin(self.root,now=self.now+timedelta(hours=6))['started'])
 def test_old_real_reports_count_against_daily_budget_after_upgrade(self):
  p=self.root/'reports/2026-10-27';p.mkdir(parents=True)
  for i in range(3):(p/f'{i}-surf.md').write_text('real previous report')
  self.assertFalse(c.agenda(self.root,self.now)['can_go'])
 def test_boredom_closes_a_thread_and_blocks_immediate_reopening(self):
  thread=c.remember(self.root,self.proposal,self.now)[0];run=c.begin(self.root,thread['id'],self.now)['run'];p=self.root/self.obs['report_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_text('visited public content')
  c.finish(self.root,{'run_id':run['id'],'outcome':'bored','reason':'这次读完觉得不想继续追了','report_path':self.obs['report_path']},self.now+timedelta(minutes=5));self.assertEqual(c.agenda(self.root,self.now+timedelta(hours=3))['threads'],[])
  with self.assertRaises(ValueError):c.remember(self.root,self.proposal,self.now+timedelta(hours=3))
 def test_want_more_requires_this_runs_fresh_evidence(self):
  thread=c.remember(self.root,self.proposal,self.now)[0];run=c.begin(self.root,thread['id'],self.now+timedelta(hours=3))['run'];p=self.root/self.obs['report_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_text('old report')
  with self.assertRaises(ValueError):c.finish(self.root,{'run_id':run['id'],'outcome':'want_more','reason':'还想继续追他这个有意思的机关','report_path':self.obs['report_path'],'evidence_ids':['obs-real']},self.now+timedelta(hours=3,minutes=5))
 def pair(self):
  one=c.remember(self.root,self.proposal,self.now)[0]
  two=c.remember(self.root,{**self.proposal,'question':'他怎样让积木柜子的门自己弹开？'},self.now)[0]
  return one,two
 def reading(self,thread):
  start=self.now+timedelta(hours=3);seen=start+timedelta(minutes=2);end=start+timedelta(minutes=5)
  name='reports/2026-10-27/1505-surf.md';path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('真实虚构夹具阅读 https://example.org/followup')
  page={'report':name,'url':'https://example.org/followup','read_at':seen.isoformat()}
  visited=c.load(self.root/'data/surf-state.json',{'visited':[]})['visited'];c.atomic(self.root/'data/surf-state.json',{'visited':[*visited,page]})
  return {'id':'browse-fiction','thread_id':thread['id'],'status':'finished','outcome':'satisfied','started_at':start.isoformat(),'finished_at':end.isoformat(),'report_path':name},page
 def test_failed_and_unfinished_attempts_do_not_lower_interest_order(self):
  one,two=self.pair();value=c.state(self.root)
  value['threads'][0].update(visits=3,last_followed_at=(self.now+timedelta(hours=3)).isoformat())
  value['runs']=[{'id':'failed-'+status,'thread_id':one['id'],'status':status,'started_at':(self.now+timedelta(hours=3)).isoformat(),**({'outcome':'blocked'}if status=='finished'else{})}for status in ('interrupted','started','finished')]
  c.atomic(self.root/'data/curiosity/state.json',value);before=(self.root/'data/curiosity/state.json').read_bytes()
  agenda=c.agenda(self.root,self.now+timedelta(hours=6));self.assertEqual([r['id']for r in agenda['threads']],[one['id'],two['id']])
  self.assertEqual(agenda['threads'][0]['read_visits'],0);self.assertIsNone(agenda['threads'][0]['last_read_at'])
  self.assertEqual(agenda['threads'][0]['visits'],3);self.assertEqual(before,(self.root/'data/curiosity/state.json').read_bytes())
 def test_completed_registered_reading_affects_order_and_counts_once_per_run(self):
  one,two=self.pair();run,page=self.reading(one);value=c.state(self.root)
  value['runs']=[run,run.copy()];c.atomic(self.root/'data/curiosity/state.json',value)
  visited=c.load(self.root/'data/surf-state.json',{'visited':[]})['visited'];c.atomic(self.root/'data/surf-state.json',{'visited':[*visited,page.copy(),{'report':page['report'],'url':page['url'],'read_at':'bad'}]})
  history=c.reading_followups(self.root,value,self.now+timedelta(hours=6));self.assertEqual(history[one['id']]['read_visits'],1)
  agenda=c.agenda(self.root,self.now+timedelta(hours=6));self.assertEqual(agenda['threads'][0]['id'],two['id'])
  self.assertEqual(agenda['threads'][1]['last_read_at'],page['read_at'])
 def test_unconfirmed_report_or_old_future_private_and_mismatched_page_do_not_count(self):
  one,_=self.pair();run,page=self.reading(one);value={'threads':[],'runs':[run]};now=self.now+timedelta(hours=6)
  cases=[{**page,'read_at':(self.now-timedelta(days=1)).isoformat()},
         {**page,'read_at':(now+timedelta(minutes=1)).isoformat()},
         {**page,'read_at':'2026-10-27T15:02:00'},
         {**page,'url':'http://127.0.0.1/private'},
         {**page,'report':'reports/2026-10-27/other-surf.md'},
         {**page,'url':'https://example.org/not-in-report'}]
  for p in cases:
   with self.subTest(page=p):
    c.atomic(self.root/'data/surf-state.json',{'visited':[p]});self.assertEqual(c.reading_followups(self.root,value,now),{})
  (self.root/run['report_path']).unlink();c.atomic(self.root/'data/surf-state.json',{'visited':[page]})
  self.assertEqual(c.reading_followups(self.root,value,now),{})
 def test_blocked_outcome_and_future_completion_do_not_count_as_reading(self):
  one,_=self.pair();run,_=self.reading(one);now=self.now+timedelta(hours=6)
  for change in ({'outcome':'blocked'},{'status':'interrupted'},{'finished_at':(now+timedelta(minutes=1)).isoformat()},{'finished_at':'2026-10-27T15:05:00'}):
   with self.subTest(change=change):self.assertEqual(c.reading_followups(self.root,{'runs':[{**run,**change}]},now),{})
 def test_existing_submission_clock_tolerance_is_kept_without_reading_the_future(self):
  one,_=self.pair();run,page=self.reading(one);end=datetime.fromisoformat(run['finished_at']);page['read_at']=(end+timedelta(seconds=45)).isoformat()
  c.atomic(self.root/'data/surf-state.json',{'visited':[page]})
  self.assertEqual(c.reading_followups(self.root,{'runs':[run]},end+timedelta(seconds=30)),{})
  self.assertEqual(c.reading_followups(self.root,{'runs':[run]},end+timedelta(minutes=1))[one['id']]['read_visits'],1)
 def test_internal_report_alias_is_supported_but_external_report_root_is_not(self):
  one,_=self.pair();run,_=self.reading(one);now=self.now+timedelta(hours=6)
  (self.root/'reports').rename(self.root/'archived-reports');(self.root/'reports').symlink_to(self.root/'archived-reports',target_is_directory=True)
  self.assertEqual(c.reading_followups(self.root,{'runs':[run]},now)[one['id']]['read_visits'],1)
  with tempfile.TemporaryDirectory()as external:
   (self.root/'reports').unlink();(self.root/'reports').symlink_to(external,target_is_directory=True)
   self.assertEqual(c.reading_followups(self.root,{'runs':[run]},now),{})
 def test_real_block_and_boredom_still_keep_the_existing_cooldown_and_stop(self):
  one,_=self.pair();run=c.begin(self.root,one['id'],self.now)['run']
  c.finish(self.root,{'run_id':run['id'],'outcome':'blocked','reason':'公开入口目前要求登录，未能继续阅读。','report_path':self.obs['report_path']},self.now+timedelta(minutes=5))
  self.assertNotIn(one['id'],[r['id']for r in c.agenda(self.root,self.now+timedelta(hours=3))['threads']])
  self.assertIn(one['id'],[r['id']for r in c.agenda(self.root,self.now+timedelta(hours=9))['threads']])
if __name__=='__main__':unittest.main()
