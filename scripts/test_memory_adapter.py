import importlib.util
import json
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
        shutil.copy2(source/'plugins/fish-episodes/__init__.py',plugin/'__init__.py');shutil.copy2(source/'scripts/fish_journal.py',plugin/'journal.py');shutil.copy2(source/'scripts/personality.py',plugin/'growth.py')
        shutil.copy2(source/'scripts/fish_conversation.py',plugin/'conversation.py')
        stub=types.ModuleType('agent.memory_provider');stub.MemoryProvider=type('MemoryProvider',(),{})
        with patch.dict(sys.modules,{'agent.memory_provider':stub}):
            spec=importlib.util.spec_from_file_location('test_fish_adapter',plugin/'__init__.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.provider=module.FishEpisodes()
    def initialize(self,scope='primary'):
        self.provider.initialize('chat-new',hermes_home=str(self.root/'.hermes'),agent_context=scope)
    def test_tool_routes_are_advertised_before_initialization_but_cannot_execute(self):
        self.assertEqual({s['name']for s in self.provider.get_tool_schemas()},{'fish_recall','fish_correct_memory'})
        self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_recall',{'query':'积木'})))
    def test_primary_turn_records_once_and_recall_excludes_current_conversation(self):
        self.initialize();self.provider.on_turn_start(1,'旧话题');self.provider.sync_turn('还记得阿蓝的积木厨房吗','上次加了升降台。')
        self.provider.sync_turn('还记得阿蓝的积木厨房吗','上次加了升降台。')
        self.assertNotIn('升降台',self.provider.prefetch('阿蓝'))
        self.provider.on_session_switch('chat-later')
        self.assertIn('升降台',self.provider.prefetch('阿蓝'))
        with Journal(self.root) as journal:self.assertEqual(journal.status()['total'],1)
    def test_cron_and_bot_inputs_do_not_become_shared_memories(self):
        self.initialize('cron');self.provider.sync_turn('自动任务','任务完成');self.assertEqual(self.provider.get_tool_schemas(),[])
        self.initialize();self.provider.on_turn_start(1,'自动投递',author_is_bot=True);self.provider.sync_turn('自动投递','自动回答')
        with Journal(self.root) as journal:self.assertEqual(journal.status()['total'],0)
    def test_foreign_home_never_binds_to_project_memory(self):
        with self.assertRaises(ValueError):self.provider.initialize('other',hermes_home=str(self.root/'foreign'))

    def test_installed_growth_helper_supplies_only_local_trying_context(self):
        from datetime import datetime,timezone
        import personality as growth
        now=datetime.now(timezone.utc)
        with Journal(self.root,now=now) as store:item=store.capture('old-chat','一起看看积木厨房','这个机关让我想继续看。')
        growth.propose_trial(self.root,{'id':'builds','text':'我似乎喜欢有巧妙机关的积木厨房作品。','reason':'实际看到机关，想再跟着看看后续。','evidence_ids':[item['id']]},now)
        self.initialize();context=self.provider.prefetch('积木厨房')
        self.assertIn('trying',context);self.assertNotIn('signals',context);self.assertFalse((self.root/'.hermes/memories/USER.md').exists())

    def episode(self):
        with Journal(self.root) as store:return store.capture('old-chat','周末一起看积木厨房','你最喜欢红色机关。')

    def test_explicit_correction_uses_current_words_and_preserves_history(self):
        item=self.episode();self.initialize();message='你记错啦，我最喜欢的是蓝色机关。'
        self.provider.on_turn_start(1,message)
        result=json.loads(self.provider.handle_tool_call('fish_correct_memory',{'id':item['id'],'revision':1}))
        self.assertTrue(result['ok'])
        with Journal(self.root) as store:
            self.assertEqual(store.get(item['id'])['summary'],'用户更正：'+message)
            self.assertEqual(store.get(item['id'])['correction_source'],'session:chat-new')
            self.assertIn('红色机关',store.history(item['id'])[0]['excerpt'])
            self.assertNotIn('红色机关',store.recall('蓝色机关'))
        self.assertFalse((self.root/'.hermes/memories/USER.md').exists())

    def test_correction_requires_explicit_live_human_quote_and_current_revision(self):
        item=self.episode();self.initialize();args={'id':item['id'],'revision':1}
        for message,extra in [('今天看蓝色机关',{}),('你记错了，我喜欢蓝色机关。',{'author_is_bot':True})]:
            self.provider.on_turn_start(1,message,**extra)
            self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_correct_memory',args)))
        self.provider.on_turn_start(2,'你记错了，我喜欢蓝色机关。')
        self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_correct_memory',{**args,'quote':'我喜欢黄色机关。'})))
        self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_correct_memory',{**args,'revision':2})))
        self.provider.sync_turn('你记错了，我喜欢蓝色机关。','好，我重新记。')
        self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_correct_memory',args)))
        with Journal(self.root) as store:self.assertEqual(store.get(item['id'])['revision'],1)

    def test_expired_episode_cannot_be_renewed_by_correction_tool(self):
        item=self.episode()
        with Journal(self.root) as store:store.update(item['id'],1,invalidate=True)
        self.initialize();self.provider.on_turn_start(1,'你记错了，我喜欢蓝色机关。')
        self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_correct_memory',{'id':item['id'],'revision':2})))

    def test_failed_capture_clears_correction_authorization(self):
        self.initialize();self.provider.on_turn_start(1,'你记错了，我喜欢蓝色机关。')
        with patch.object(self.provider,'journal',side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):self.provider.sync_turn('你记错了，我喜欢蓝色机关。','收到')
        self.assertEqual(self.provider.current_user,'')

    def test_delayed_previous_sync_cannot_clear_new_human_correction(self):
        self.initialize();self.provider.on_turn_start(1,'先聊积木机关。')
        message='你记错了，我喜欢蓝色机关。';self.provider.on_turn_start(2,message)
        self.provider.sync_turn('先聊积木机关。','这次看到一个抽屉机关。')
        self.assertEqual(self.provider.current_user,message)
    def test_async_sync_uses_the_completed_turn_author_not_the_next_turn(self):
        self.initialize();self.provider.on_turn_start(1,'自动投递',author_is_bot=True)
        self.provider.on_turn_start(2,'真人想聊积木机关。')
        self.provider.sync_turn('自动投递','自动回复',turn_author={'is_bot':True})
        self.provider.on_turn_start(3,'另一个自动投递',author_is_bot=True)
        self.provider.sync_turn('真人想聊积木机关。','这个抽屉机关很有趣。',turn_author={'is_bot':False})
        with Journal(self.root)as store:
            self.assertEqual(store.status()['total'],1);self.assertIn('抽屉机关',store.recall('积木机关'))
    def test_provider_supplies_bounded_rhythm_hints_but_no_unrelated_surfing_to_serious_turn(self):
        self.initialize();self.provider.on_turn_start(1,'帮我排查代码报错。')
        packet=self.provider.prefetch('帮我排查代码报错。')
        self.assertIn('focused',packet);self.assertNotIn('"interest":',packet);self.assertLessEqual(len(packet),6800)
    def test_failed_interest_metadata_does_not_lose_the_completed_human_turn(self):
        self.initialize();self.provider.on_turn_start(1,'这个折叠机关是怎么做的？')
        with patch.object(self.provider.conversation,'note_chat_links',side_effect=ValueError('invalid source metadata')):
            self.provider.sync_turn('这个折叠机关是怎么做的？','来源：https://example.org/folding')
        with Journal(self.root)as store:self.assertEqual(store.status()['total'],1)
        self.assertEqual(self.provider.current_user,'')

if __name__=='__main__':unittest.main()
