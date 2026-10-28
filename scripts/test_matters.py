from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal,tokens
from fish_matters import Matters


class MattersTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=datetime(2026,10,28,5,tzinfo=timezone.utc);self.store=Journal(self.root,now=self.now);self.addCleanup(self.store.db.close);self.matters=Matters(self.store,tokens)
        self.user='我准备写毕业论文，先把文献综述做好。';self.title='准备写毕业论文'
    def add(self):return self.matters.live({'action':'remember','title':self.title,'kind':'goal','quote':self.user},self.user,'chat-fixture')['item']
    def test_live_add_is_source_bound_idempotent_and_survives_reopen(self):
        first=self.add();self.assertEqual(self.add()['id'],first['id']);self.assertEqual(len(self.matters.list()),1)
        with Journal(self.root,now=self.now+timedelta(days=1))as store:
            item=Matters(store,tokens).list('毕业论文')[0];self.assertEqual(item['quote'],self.user);self.assertEqual(item['source_ref'],'session:chat-fixture')
        self.assertFalse((self.root/'.hermes/memories/USER.md').exists())
    def test_update_uses_user_words_and_cas_while_history_preserves_source(self):
        item=self.add();user='毕业论文已经提交了。'
        result=self.matters.live({'action':'update','id':item['id'],'revision':1,'status':'done','quote':user},user,'chat-fixture')['item']
        self.assertEqual(result['effective_status'],'done');self.assertEqual(result['quote'],user);self.assertEqual(len(self.matters.events(item['id'])),2)
        with self.assertRaises(ValueError):self.matters.update(item['id'],1,'paused')
        self.assertIn('done',self.matters.context('毕业论文后来怎么样'))
        self.assertEqual(self.matters.context('我最近在忙什么'), '')
    def test_negated_completion_and_unrelated_target_are_rejected(self):
        item=self.add()
        for user in ['毕业论文还没完成。','驾照考试已经通过了。','这件事已经完成了。']:
            with self.subTest(user=user),self.assertRaises(ValueError):self.matters.live({'action':'update','id':item['id'],'revision':1,'status':'done','quote':user},user,'chat-fixture')
        self.assertEqual(self.matters.get(item['id'])['revision'],1)
    def test_quoted_web_post_and_refusal_do_not_create_a_goal(self):
        for user in ['帖子说“我准备写毕业论文”，你觉得呢。','> 我准备写毕业论文\n这句话是什么意思？','不要帮我记录，我准备写毕业论文。']:
            with self.subTest(user=user),self.assertRaises(ValueError):self.matters.live({'action':'remember','title':self.title,'kind':'goal','quote':'我准备写毕业论文'},user,'chat-fixture')
        with self.assertRaises(ValueError):self.matters.live({'action':'remember','title':self.title,'kind':'goal','quote':'我准备写毕业论文。'},self.user,'chat-fixture')
        self.assertEqual(self.matters.list(),[])
    def test_unrelated_personal_intent_cannot_launder_a_quoted_goal(self):
        user='我准备吃饭，帖子里写“我准备写毕业论文”。';quote='我准备写毕业论文'
        with self.assertRaises(ValueError):self.matters.live({'action':'remember','title':'准备写毕业论文','kind':'goal','quote':quote},user,'chat-fixture')
        user='```\n我准备写毕业论文'
        with self.assertRaises(ValueError):self.matters.live({'action':'remember','title':'准备写毕业论文','kind':'goal','quote':quote},user,'chat-fixture')
    def test_relevant_context_is_bounded_and_unrelated_chat_stays_empty(self):
        self.add();self.assertIn(self.title,self.matters.context('毕业论文的文献综述还差什么？'))
        self.assertEqual(self.matters.context('今天吃什么？'),'');self.assertEqual(self.matters.context('你好'),'')
        self.assertIn(self.title,self.matters.context('我最近在忙什么？'))
        for n in range(6):self.matters.add('准备写毕业论文第'+str(n)+'章','goal','我准备写毕业论文第'+str(n)+'章','local:editor')
        context=self.matters.context('毕业论文');self.assertEqual(len(json.loads(context.split('\n',1)[1])),2);self.assertLess(len(context),2400)
    def test_default_expiry_requires_explicit_panel_renewal(self):
        item=self.add()
        with Journal(self.root,now=self.now+timedelta(days=90))as store:
            matters=Matters(store,tokens);self.assertEqual(matters.context('毕业论文'),'');self.assertEqual(matters.list('毕业论文',history=True)[0]['effective_status'],'expired')
            with self.assertRaises(ValueError):matters.update(item['id'],1,'open')
            renewed=matters.update(item['id'],1,'open',renew=True)['item'];self.assertEqual(renewed['effective_status'],'open')
    def test_episode_changes_require_review_but_pin_changes_do_not(self):
        item=self.add();episode=self.store.capture('chat-fixture',self.user,'好，先收好这个目标。');self.matters.bind_episode('chat-fixture',self.user,episode)
        self.store.update(episode['id'],1,pinned=True);self.assertEqual(self.matters.state(self.matters.get(item['id'])),'open')
        self.store.update(episode['id'],2,summary='更正：当时只是转述朋友的毕业论文计划。')
        self.assertEqual(self.matters.context('毕业论文'),'');self.assertEqual(self.matters.describe(self.matters.get(item['id']))['effective_status'],'review')
        with self.assertRaises(ValueError):self.matters.live({'action':'update','id':item['id'],'revision':1,'status':'open','quote':self.user},self.user,'chat-fixture')
        self.matters.update(item['id'],1,'open','我确认这是自己现在的目标。');self.assertIn(self.title,self.matters.context('毕业论文'))
    def test_forgetting_episode_erases_linked_matters_and_all_event_quotes(self):
        item=self.add();episode=self.store.capture('chat-fixture',self.user,'好。');self.matters.bind_episode('chat-fixture',self.user,episode)
        self.store.update(episode['id'],1,forget=True);self.assertEqual(self.matters.get(item['id'])['status'],'deleted');self.assertEqual(self.matters.events(item['id']),[]);self.assertEqual(self.matters.get(item['id'])['title'],'')
        with self.assertRaises(ValueError):self.add()
    def test_late_binding_to_a_deleted_episode_cannot_restore_its_text(self):
        item=self.add();episode=self.store.capture('chat-fixture',self.user,'好。');self.store.update(episode['id'],1,forget=True)
        self.matters.bind_episode('chat-fixture',self.user,self.store.get(episode['id']));self.assertEqual(self.matters.get(item['id'])['status'],'deleted');self.assertEqual(self.matters.events(item['id']),[])
    def test_panel_forget_allows_deliberate_fresh_reentry(self):
        item=self.matters.add('准备写毕业论文','goal','准备写毕业论文','local:editor')['item'];self.matters.update(item['id'],1,'open',forget=True)
        fresh=self.matters.add('准备写毕业论文','goal','准备写毕业论文','local:editor')['item'];self.assertNotEqual(fresh['id'],item['id']);self.assertEqual(self.matters.get(item['id'])['title'],'')
        self.assertEqual(self.matters.add('准备写毕业论文','goal','准备写毕业论文','local:editor')['item']['id'],fresh['id'])
    def test_credentials_are_rejected_without_saving_or_echoing_them(self):
        (self.root/'.hermes').mkdir();secret='synthetic-api-credential-without-prefix';(self.root/'.hermes/.env').write_text('API_KEY='+secret)
        with self.assertRaises(ValueError):self.matters.add('准备写论文'+secret,'goal','准备写论文'+secret,'local:editor')
        self.assertEqual(self.matters.list(),[])
    def test_paused_goals_do_not_enter_general_unfinished_list(self):
        item=self.add();self.matters.update(item['id'],1,'paused')
        self.assertEqual(self.matters.context('我最近在忙什么'),'');self.assertIn('paused',self.matters.context('毕业论文后来怎么样'))
    def test_direct_unresolved_problem_and_shared_promise_can_be_recorded(self):
        for user,title,kind in [('我的电脑老是蓝屏，还没修好。','电脑老是蓝屏','issue'),('我们约好下周一起检查纸桥结构。','下周一起检查纸桥结构','promise')]:
            result=self.matters.live({'action':'remember','title':title,'kind':kind,'quote':user},user,'chat-fixture');self.assertEqual(result['item']['kind'],kind)
    def test_short_but_specific_goal_titles_are_valid(self):
        user='我准备学吉他，先练基础和弦。'
        result=self.matters.live({'action':'remember','title':'学吉他','kind':'goal','quote':user},user,'chat-fixture');self.assertEqual(result['item']['title'],'学吉他')
    def test_pending_limit_does_not_count_completed_matters(self):
        for n in range(20):self.matters.add('准备写第'+str(n)+'个项目','goal','准备写第'+str(n)+'个项目','local:editor')
        with self.assertRaises(ValueError):self.add()
        item=self.matters.list()[0];self.matters.update(item['id'],1,'done');self.assertEqual(self.add()['effective_status'],'open')


if __name__=='__main__':unittest.main()
