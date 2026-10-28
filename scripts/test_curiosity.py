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
if __name__=='__main__':unittest.main()
