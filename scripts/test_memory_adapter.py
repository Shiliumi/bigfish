import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from fish_journal import Journal

class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'scripts').mkdir();(self.root/'scripts/fish_journal.py').write_text('# project marker')
        plugin=self.root/'.hermes/plugins/fish-episodes';plugin.mkdir(parents=True)
        source=Path(__file__).resolve().parents[1]
        shutil.copy2(source/'plugins/fish-episodes/__init__.py',plugin/'__init__.py');shutil.copy2(source/'scripts/fish_journal.py',plugin/'journal.py')
        stub=types.ModuleType('agent.memory_provider');stub.MemoryProvider=type('MemoryProvider',(),{})
        with patch.dict(sys.modules,{'agent.memory_provider':stub}):
            spec=importlib.util.spec_from_file_location('test_fish_adapter',plugin/'__init__.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.provider=module.FishEpisodes()
    def initialize(self,scope='primary'):
        self.provider.initialize('chat-new',hermes_home=str(self.root/'.hermes'),agent_context=scope)
    def test_primary_turn_records_once_and_recall_excludes_current_conversation(self):
        self.initialize();self.provider.on_turn_start(1,'旧话题');self.provider.sync_turn('还记得阿蓝的积木厨房吗','上次加了升降台。')
        self.provider.sync_turn('还记得阿蓝的积木厨房吗','上次加了升降台。')
        self.assertEqual(self.provider.prefetch('阿蓝'),'')
        self.provider.on_session_switch('chat-later')
        self.assertIn('升降台',self.provider.prefetch('阿蓝'))
        with Journal(self.root) as journal:self.assertEqual(journal.status()['total'],1)
    def test_cron_and_bot_inputs_do_not_become_shared_memories(self):
        self.initialize('cron');self.provider.sync_turn('自动任务','任务完成');self.assertEqual(self.provider.get_tool_schemas(),[])
        self.initialize();self.provider.on_turn_start(1,'自动投递',author_is_bot=True);self.provider.sync_turn('自动投递','自动回答')
        with Journal(self.root) as journal:self.assertEqual(journal.status()['total'],0)
    def test_foreign_home_never_binds_to_project_memory(self):
        with self.assertRaises(ValueError):self.provider.initialize('other',hermes_home=str(self.root/'foreign'))

if __name__=='__main__':unittest.main()
