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
        shutil.copy2(source/'scripts/fish_matters.py',plugin/'matters.py')
        semantic=plugin/'semantic';semantic.mkdir();(semantic/'__init__.py').write_text('')
        for name in ('fish_journal.py','fish_semantic_cache.py','fish_embeddings.py','fish_embedding_process.py','fish_embedding_worker.py','fish_semantic_recall.py'):
            shutil.copy2(source/'scripts'/name,semantic/name)
        stub=types.ModuleType('agent.memory_provider');stub.MemoryProvider=type('MemoryProvider',(),{})
        with patch.dict(sys.modules,{'agent.memory_provider':stub}):
            spec=importlib.util.spec_from_file_location('test_fish_adapter',plugin/'__init__.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.provider=module.FishEpisodes()
    def initialize(self,scope='primary'):
        self.provider.initialize('chat-new',hermes_home=str(self.root/'.hermes'),agent_context=scope)
    def test_tool_routes_are_advertised_before_initialization_but_cannot_execute(self):
        self.assertEqual({s['name']for s in self.provider.get_tool_schemas()},{'fish_recall','fish_correct_memory','fish_matters'})
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
    def test_cron_and_subagents_do_not_advertise_unavailable_shared_memory_tools(self):
        self.initialize();primary=self.provider.system_prompt_block();self.assertIn('fish_recall',primary)
        for scope in ['cron','subagent']:
            self.initialize(scope);self.assertEqual(self.provider.system_prompt_block(),'');self.assertEqual(self.provider.get_tool_schemas(),[])
        self.initialize();self.assertEqual(self.provider.system_prompt_block(),primary)
    def test_foreign_home_never_binds_to_project_memory(self):
        with self.assertRaises(ValueError):self.provider.initialize('other',hermes_home=str(self.root/'foreign'))

    def test_familiar_hint_and_literal_detour_repair_reach_primary_prefetch(self):
        self.initialize()
        packet=self.provider.prefetch('你是不是很方啊？')
        self.assertIn('"mode":"personal"',packet);self.assertIn('关心、夸奖',packet)
        self.provider.sync_turn('你是不是很方啊？','方是几何形状，与紧张是两码事。')
        packet=self.provider.prefetch('看你方方正正的，去门口当门墩吧。')
        self.assertIn('"mode":"playful"',packet);self.assertIn('不维护旧解释',packet)
        self.assertNotIn('方是几何形状',packet)
        self.assertIn('"mode":"focused"',self.provider.prefetch('认真说，帮我修这个报错。'))
        self.assertIn('"mode":"gentle"',self.provider.prefetch('今天很难受，先别闹了。'))
        self.assertNotIn('"mode":"personal"',self.provider.prefetch('你是不是支持图片？'))

    def test_synced_interest_link_is_bound_to_the_actual_conversation(self):
        from datetime import datetime,timezone,timedelta
        now=datetime.now(timezone.utc);self.initialize()
        source=Path(__file__).resolve().parents[1]
        shutil.copy2(source/'scripts/curiosity.py',self.root/'scripts/curiosity.py')
        url='https://example.org/paper-gears';report='reports/2026-10-31/1200-surf.md';ident='cur-123456789abc'
        path=self.root/report;path.parent.mkdir(parents=True);path.write_text(url)
        (self.root/'data/personality').mkdir(parents=True,exist_ok=True)
        (self.root/'data/personality/observations.jsonl').write_text(json.dumps({'id':'obs-fiction','url':url,'seen_at':now.isoformat(),'report_path':report,'read_depth':'body','observation':'实际读到了纸齿轮的结构。'})+'\n')
        (self.root/'data/surf-state.json').write_text(json.dumps({'visited':[{'url':url,'report':report,'read_at':now.isoformat()}]}))
        path=self.root/'data/curiosity/state.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'threads':[{'id':ident,'question':'纸齿轮怎样保持啮合？','why':'想继续看纸片的连接处。','status':'open','expires_at':(now+timedelta(days=7)).isoformat(),'evidence_ids':['obs-fiction'],'source_urls':[url]}]}))
        self.provider.on_turn_start(1,'刚才说到的那个作品。')
        self.provider.sync_turn('刚才说到的那个作品。','[纸齿轮]('+url+')',session_id='actual-conversation')
        self.assertIn(ident,self.provider.prefetch('上次那个后来怎么样了？',session_id='actual-conversation'))
        unresolved=self.provider.prefetch('上次那个后来怎么样了？',session_id='different-conversation')
        self.assertNotIn(ident,unresolved);self.assertIn('followup_boundary',unresolved)

    def test_unpromoted_trial_losing_its_source_does_not_return_through_prefetch(self):
        from datetime import datetime,timezone
        now=datetime.now(timezone.utc);text='我似乎喜欢从具体的小反差里接一句短话。'
        with Journal(self.root,now=now)as journal:row=journal.capture('fiction-seed','这次纸盒展开很好笑。','还想试试一句短反应。')
        self.initialize()
        self.provider.growth.propose_trial(self.root,{'id':'small-reaction','kind':'expression','text':text,'reason':'这个具体的小反差确实让我想再接一句。','evidence_ids':[row['id']]},now)
        self.assertIn(text,self.provider.prefetch('随便说一句。'))
        with Journal(self.root)as journal:journal.update(row['id'],1,forget=True)
        packet=self.provider.prefetch('随便说一句。')
        self.assertNotIn(text,packet);self.assertIn('"stage": "reconsidering"',packet);self.assertIn('先暂停',packet)

    def test_playful_personal_and_callback_share_mode_before_trial_selection(self):
        from datetime import datetime,timezone,timedelta
        now=datetime.now(timezone.utc);self.initialize();text='评价作品时，我似乎更愿意先列出可核对参数，再给结论。'
        with Journal(self.root,now=now)as journal:
            row=journal.capture('fiction-seed','一起看键盘规格。','先核对参数，再评价做法。')
            journal.capture('chat-new','你今天有种微波炉土豆的气质。','烫嘴是吧。',recorded_at=(now-timedelta(minutes=1)).isoformat())
        self.provider.growth.propose_trial(self.root,{'id':'careful-review','kind':'expression','text':text,'reason':'这次规格核对让我确实想试试这种评价方式。','evidence_ids':[row['id']]},now)
        for query,mode in [('你是不是很方啊？','personal'),('看把你得意的。','playful'),('那就叫你薯熟吧。','playful')]:
            with self.subTest(query=query),patch.object(self.provider.conversation,'resolve_mode',wraps=self.provider.conversation.resolve_mode)as choose:
                packet=self.provider.prefetch(query);self.assertIn('"mode":"'+mode+'"',packet);self.assertNotIn(text,packet);self.assertEqual(choose.call_count,1)
        self.assertIn(text,self.provider.prefetch('平常你怎么看小工具。'))
        self.assertIn(text,self.provider.prefetch('那就叫你薯熟吧。',session_id='another-conversation'))

    def test_budget_fallback_reuses_the_same_resolved_mode(self):
        self.initialize();oversized='引用来源\n'+json.dumps([{'id':'fiction-large','excerpt':'甲'*3500}],ensure_ascii=False)
        with patch.object(self.provider,'_recall',return_value=oversized),patch.object(self.provider,'matters')as matters:
            matters.return_value.context.return_value='乙'*4200
            with patch.object(self.provider.conversation,'resolve_mode',wraps=self.provider.conversation.resolve_mode)as choose,patch.object(self.provider.conversation,'context',wraps=self.provider.conversation.context)as context:
                packet=self.provider.prefetch('你是不是很方啊？')
                self.assertEqual(choose.call_count,1);self.assertEqual(context.call_count,2)
                self.assertTrue(all(call.kwargs['mode']=='personal'for call in context.call_args_list))
                self.assertIn('"mode":"personal"',packet);self.assertNotIn('fiction-large',packet)

    def test_optional_semantic_route_is_bound_and_keeps_existing_tool_names(self):
        before=list(sys.path);self.initialize();self.assertEqual(sys.path,before)
        self.assertEqual(self.provider.semantic.root,self.root.resolve())
        with patch.object(self.provider.semantic,'recall',return_value='fictional source')as recall:
            self.assertEqual(json.loads(self.provider.handle_tool_call('fish_recall',{'query':'换个说法找回旧事'}))['context'],'fictional source')
            self.assertEqual(recall.call_args.args[1],'换个说法找回旧事')
        self.assertEqual({r['name']for r in self.provider.get_tool_schemas()},{'fish_recall','fish_correct_memory','fish_matters'})

    def test_broken_optional_package_cannot_disable_lexical_memory(self):
        (self.root/'.hermes/plugins/fish-episodes/semantic/fish_embeddings.py').unlink();self.initialize()
        self.assertIsNone(self.provider.semantic);self.provider.sync_turn('一起看纸风车。','四个叶片。')
        self.assertIn('四个叶片',self.provider.prefetch('纸风车',session_id='another'))

    def test_indexing_runs_after_authorization_cleanup_and_never_for_bot_turns(self):
        self.initialize();self.provider.on_turn_start(1,'先聊纸风车。')
        def index(journal,**kwargs):
            self.assertEqual(self.provider.current_user,'')
            self.provider.on_turn_start(2,'你记错了，是蓝色叶片。')
        with patch.object(self.provider.semantic,'index_pending',side_effect=index)as indexed:
            self.provider.sync_turn('先聊纸风车。','有四个叶片。',turn_author={'is_bot':False})
            self.assertEqual(indexed.call_count,1)
            self.assertEqual(self.provider.current_user,'你记错了，是蓝色叶片。')
            self.provider.sync_turn('自动投递','自动回复',turn_author={'is_bot':True})
            self.assertEqual(indexed.call_count,1)

    def test_optional_index_or_lookup_failure_does_not_hide_captured_lexical_memory(self):
        self.initialize();self.provider.on_turn_start(1,'一起看纸风车。')
        with patch.object(self.provider.semantic,'index_pending',side_effect=RuntimeError('fixture failure')):
            self.provider.sync_turn('一起看纸风车。','有四个叶片。')
        self.assertEqual(self.provider.current_user,'')
        with patch.object(self.provider.semantic,'recall',side_effect=RuntimeError('fixture failure')):
            result=json.loads(self.provider.handle_tool_call('fish_recall',{'query':'纸风车'}))
            self.assertIn('四个叶片',result['context'])

    def test_installed_growth_helper_supplies_only_local_trying_context(self):
        from datetime import datetime,timezone
        import personality as growth
        now=datetime.now(timezone.utc)
        with Journal(self.root,now=now) as store:item=store.capture('old-chat','一起看看积木厨房','这个机关让我想继续看。')
        growth.propose_trial(self.root,{'id':'builds','text':'我似乎喜欢有巧妙机关的积木厨房作品。','reason':'实际看到机关，想再跟着看看后续。','evidence_ids':[item['id']]},now)
        self.initialize();context=self.provider.prefetch('积木厨房')
        self.assertIn('trying',context);self.assertNotIn('signals',context);self.assertFalse((self.root/'.hermes/memories/USER.md').exists())

    def test_recent_user_feedback_defers_expression_trials_but_keeps_related_interest(self):
        from datetime import datetime,timezone
        import personality as growth
        now=datetime.now(timezone.utc)
        with Journal(self.root,now=now)as journal:row=journal.capture('seed','一起看看折纸机关。','那个翻折结构还想再看。')
        for ident,kind,text in [('wordplay','expression','我似乎喜欢拿每句话的称呼开个玩笑。'),('folding','interest','我似乎喜欢有翻折巧思的折纸机关。')]:
            growth.propose_trial(self.root,{'id':ident,'kind':kind,'text':text,'reason':'这次确实有具体结构想再试试。','evidence_ids':[row['id']]},now)
        self.initialize();self.assertIn('拿每句话的称呼',self.provider.prefetch('折纸机关'))
        self.provider.sync_turn('后面别老喊爸爸，也别每次都用问题收尾。','好，接着聊。')
        result=self.provider.prefetch('折纸机关')
        self.assertIn('recent_feedback',result);self.assertNotIn('拿每句话的称呼',result);self.assertIn('有翻折巧思',result)
        self.assertFalse((self.root/'.hermes/memories/USER.md').exists())
        release='现在可以正常叫爸爸了，想问就问。'
        self.assertNotIn('recent_feedback',self.provider.prefetch(release))
        self.provider.sync_turn(release,'好。')
        self.assertIn('拿每句话的称呼',self.provider.prefetch('折纸机关'))

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
    def test_live_matter_tool_records_progress_and_binds_to_the_actual_human_episode(self):
        self.initialize();user='我准备写毕业论文，先看文献。';self.provider.on_turn_start(1,user)
        args={'action':'remember','title':'准备写毕业论文','kind':'goal','quote':user}
        result=json.loads(self.provider.handle_tool_call('fish_matters',args));self.assertTrue(result['ok']);ident=result['item']['id']
        self.provider.sync_turn(user,'好，先把文献收一收。')
        with self.provider.journal(self.root)as store:
            item=self.provider.matters(store,self.provider.tokenize).describe(self.provider.matters(store,self.provider.tokenize).get(ident),history=True)
            self.assertTrue(item['source_episode_id']);self.assertEqual(item['history'][0]['quote'],user)
        self.provider.on_session_switch('chat-next');self.provider.on_turn_start(1,'毕业论文后来怎么样？');self.assertIn(ident,self.provider.prefetch('毕业论文后来怎么样？'))
        update='毕业论文已经提交了。';self.provider.on_turn_start(2,update)
        result=json.loads(self.provider.handle_tool_call('fish_matters',{'action':'update','id':ident,'revision':1,'status':'done','quote':update}));self.assertEqual(result['item']['status'],'done')
    def test_matters_cannot_be_written_by_cron_bot_or_completed_turn(self):
        user='我准备写毕业论文，先看文献。';args={'action':'remember','title':'准备写毕业论文','kind':'goal','quote':user}
        self.initialize('cron');self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_matters',args)))
        self.initialize();self.provider.on_turn_start(1,user,author_is_bot=True);self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_matters',args)))
        self.provider.on_turn_start(2,user);self.provider.sync_turn(user,'好。');self.assertIn('error',json.loads(self.provider.handle_tool_call('fish_matters',args)))
    def test_failed_interest_metadata_does_not_lose_the_completed_human_turn(self):
        self.initialize();self.provider.on_turn_start(1,'这个折叠机关是怎么做的？')
        with patch.object(self.provider.conversation,'note_chat_links',side_effect=ValueError('invalid source metadata')):
            self.provider.sync_turn('这个折叠机关是怎么做的？','来源：https://example.org/folding')
        with Journal(self.root)as store:self.assertEqual(store.status()['total'],1)
        self.assertEqual(self.provider.current_user,'')

if __name__=='__main__':unittest.main()
