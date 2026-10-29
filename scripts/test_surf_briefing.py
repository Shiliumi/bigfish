from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import curiosity
import surf_briefing as briefing
from test_job_tool_profiles import Store


class BriefingTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)/'project';self.root.mkdir()
        self.now=datetime(2026,10,29,12,tzinfo=ZoneInfo('Asia/Shanghai'))
        for name in briefing.DOCUMENTS:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('完整的虚构说明：'+name+'\n不得截掉最后一句。')
    def test_one_read_contains_clock_agenda_and_whole_documents_without_starting(self):
        previous=curiosity.state(self.root);result=briefing.briefing(self.root,self.now)
        self.assertTrue(result['can_go']);self.assertEqual(result['checked_at'],self.now.isoformat())
        for item in result['documents']:
            self.assertFalse(item['read_required']);self.assertEqual(item['content'],(self.root/item['path']).read_text())
        self.assertEqual(curiosity.state(self.root),previous)
        self.assertFalse((self.root/'data/curiosity/state.json').exists())
    def test_quiet_or_paused_returns_a_short_decision_without_requiring_documents(self):
        for name in briefing.DOCUMENTS:(self.root/name).unlink()
        curiosity.atomic(self.root/'data/personality/trials.json',{'invalid':'not loaded while resting'})
        result=briefing.briefing(self.root,self.now.replace(hour=23));self.assertFalse(result['can_go']);self.assertNotIn('documents',result)
        curiosity.atomic(self.root/'data/automation/settings.json',{'paused':True,'max_outings':3})
        result=briefing.briefing(self.root,self.now);self.assertFalse(result['can_go']);self.assertNotIn('documents',result)
        self.assertFalse((self.root/'data/memory/episodes.sqlite3').exists())
    def test_large_document_is_deferred_whole_and_does_not_hide_other_files(self):
        (self.root/briefing.DOCUMENTS[0]).write_text('甲'*(briefing.PER_FILE//3+1))
        result=briefing.briefing(self.root,self.now);first,*rest=result['documents']
        self.assertTrue(first['read_required']);self.assertNotIn('content',first);self.assertTrue(all(not r['read_required']for r in rest))
    def test_combined_budget_is_bounded_without_partial_protocols(self):
        for name in briefing.DOCUMENTS:(self.root/name).write_text('a'*60)
        with patch.object(briefing,'PER_FILE',100),patch.object(briefing,'TOTAL',110):result=briefing.briefing(self.root,self.now)
        self.assertEqual([r['read_required']for r in result['documents']],[False,True,True])
    def test_redaction_applies_to_documents_and_nested_agenda_material(self):
        secret='synthetic-current-opaque-credential';folder=self.root/'.hermes';folder.mkdir();(folder/'.env').write_text('API_KEY='+secret)
        (self.root/briefing.DOCUMENTS[0]).write_text('我的兴趣说明 '+secret)
        status={'can_go':True,'rest_reason':'','used_today':0,'daily_limit':3,'recent_observations':[{'observation':secret}]}
        with patch.object(curiosity,'agenda',return_value=status):result=briefing.briefing(self.root,self.now)
        self.assertNotIn(secret,json.dumps(result));self.assertIn('凭据已隐藏',json.dumps(result,ensure_ascii=False))
    def test_missing_or_symlinked_documents_cannot_silently_substitute_other_files(self):
        path=self.root/briefing.DOCUMENTS[0];path.unlink()
        with self.assertRaises(ValueError):briefing.briefing(self.root,self.now)
        target=self.root.parent/'outside.md';target.write_text('not a project instruction');path.symlink_to(target)
        with self.assertRaises(ValueError):briefing.briefing(self.root,self.now)
        self.assertFalse(curiosity.state(self.root)['runs'])
    def test_real_cli_emits_one_json_object_from_another_working_directory(self):
        scripts=self.root/'scripts';scripts.mkdir()
        for name in ['curiosity.py','surf_briefing.py','fish_journal.py','fish_conversation.py','fish_interest.py','personality.py','surf_lifecycle.py']:
            shutil.copy2(Path(__file__).with_name(name),scripts/name)
        result=subprocess.run(['python3',str(scripts/'curiosity.py'),'briefing'],cwd=self.root.parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);value=json.loads(result.stdout)
        self.assertIsInstance(value['can_go'],bool);self.assertIn('checked_at',value);self.assertFalse(curiosity.state(self.root)['runs'])


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self.prompt=briefing.INTRO+'\n'+briefing.OLD_STEP+'\n2. 保留用户手动改过的其他步骤。\n'
        self.rows=[{'id':'surf','name':'fish-surf','prompt':self.prompt,'schedule':{'kind':'cron'},'model':'fixture-model','enabled_toolsets':[]},
                   {'id':'memory','name':'fish-memory','prompt':'unchanged memory prompt'},
                   {'id':'study','name':'fish-study-buddy','prompt':'unchanged custom prompt'}]
    def test_only_known_first_step_changes_and_repeated_upgrade_is_a_noop(self):
        store=Store(self.rows);self.assertTrue(briefing.apply_update(store)['updated'])
        self.assertEqual(store.saved,[{'prompt':self.prompt.replace(briefing.OLD_STEP,briefing.NEW_STEP)}])
        self.assertEqual(store.rows[0],{**self.rows[0],**store.saved[0]});self.assertEqual(store.rows[1:],self.rows[1:])
        self.assertFalse(briefing.apply_update(store)['updated']);self.assertEqual(len(store.saved),1)
    def test_custom_first_steps_headers_and_quoted_examples_are_preserved(self):
        for text in [self.prompt.replace('一次读取','按用户规则读取'),self.prompt.replace(briefing.INTRO,'用户自定义开场'),self.prompt+'```\n'+briefing.OLD_STEP+'\n```\n']:
            with self.subTest(prompt=text):self.assertIsNone(briefing.upgrade_prompt(text))
        self.assertEqual(briefing.upgrade_prompt(self.prompt.replace('\n','\r\n')),self.prompt.replace(briefing.OLD_STEP,briefing.NEW_STEP).replace('\n','\r\n'))
    def test_duplicate_missing_and_concurrent_changes_never_reset_jobs(self):
        store=Store(self.rows+[{'id':'duplicate','name':'fish-surf'}])
        with self.assertRaises(ValueError):briefing.apply_update(store)
        self.assertFalse(store.saved);self.assertFalse(briefing.apply_update(Store(self.rows[1:]))['updated'])
        for update in [lambda rows:rows[0].update(prompt='new human choice'),lambda rows:rows[0].update(name='another-task'),lambda rows:rows.pop(0)]:
            store=Store(self.rows);store.before_apply=update
            with self.assertRaises(ValueError):briefing.apply_update(store)
            self.assertFalse(store.saved)


if __name__=='__main__':unittest.main()
