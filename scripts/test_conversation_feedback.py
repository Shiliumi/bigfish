"""Temporary style feedback from the current conversation; no model or private state."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal
import fish_conversation as talk


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.now=datetime(2026,10,29,4,tzinfo=timezone.utc)
        self.store=Journal(self.root,now=self.now);self.addCleanup(self.store.db.close)
    def record(self,text,session='chat',assistant='好，接着聊。',minutes=-1):
        return self.store.capture(session,text,assistant,recorded_at=(self.now+timedelta(minutes=minutes)).isoformat())
    def active(self,query='',session='chat',now=None):
        return talk.recent_feedback(self.store,session,query,now or self.now)
    def test_recent_explicit_requests_continue_without_copying_the_old_message(self):
        original='后面别老喊爸爸，也别每次都用问题收尾。聊天简短一点，别一直解释。说话太正经了。'
        row=self.record(original);before=self.store.get(row['id'])
        self.assertEqual(self.active(),['address','brief','questions','relaxed'])
        context=talk.context(self.root,'那我回来了。',journal=self.store,session_id='chat',now=self.now)
        payload=json.loads(context.split('\n',1)[1]);self.assertEqual(len(payload['recent_feedback']),4)
        self.assertNotIn(original,context);self.assertLess(len(context),700)
        self.assertEqual(self.store.get(row['id']),before)
        self.assertFalse((self.root/'.hermes/SOUL.md').exists())
    def test_each_request_can_be_released_without_erasing_the_other_ones(self):
        self.record('后面别老喊爸爸，也别每次都用问题收尾。聊天简短一点。')
        self.assertEqual(self.active('以后不可以正常叫爸爸。'),['address','brief','questions'])
        self.assertEqual(self.active('现在可以正常叫爸爸了。'),['brief','questions'])
        self.record('现在可以正常叫爸爸了。',minutes=-.5)
        self.assertEqual(self.active('不用再刻意简短，想问就问。'),[])
        self.assertEqual(talk.style_events('后面别老喊爸爸，现在可以叫爸爸了。'),[('address',True),('address',False)])
        self.assertEqual(talk.style_events('现在可以叫爸爸了，但以后别每句都叫爸爸。'),[('address',False),('address',True)])
        self.assertEqual(talk.style_events('现在可以叫爸爸了不过后面别每次都喊爸爸。'),[('address',False),('address',True)])
        self.assertEqual(self.active('不要想问就问。'),['brief','questions'])
    def test_a_one_off_task_does_not_release_or_create_a_global_style_request(self):
        self.record('后面说话简短一点。')
        self.assertEqual(self.active('这道题详细解释，给我完整推导。'),['brief'])
        for query in ['这次回复简短一点。','这道题不要再分析了。','这个例子不用解释。','这一句先别喊爸爸。']:
            with self.subTest(query=query):self.assertEqual(talk.style_events(query),[])
    def test_a_later_explicit_tone_choice_replaces_the_earlier_one(self):
        self.record('你说话太正经了，后面别像客服。')
        self.assertEqual(self.active(),['relaxed'])
        self.assertEqual(self.active('后面说话正式一点。'),['formal'])
        self.record('后面说话正式一点。',minutes=-.5)
        self.assertEqual(self.active('后面别像客服。'),['relaxed'])
        self.assertEqual(self.active('不用再刻意正式。'),[])
        self.assertEqual(self.active('这道题严肃一点，帮我分析。'),['formal'])
    def test_feedback_is_scoped_to_recent_turns_and_the_same_conversation(self):
        self.record('后面别老喊爸爸。',minutes=-5)
        self.assertEqual(self.active(session='other'),[])
        self.assertEqual(self.active(now=self.now+timedelta(minutes=25)),[])
        for i in range(3):self.record('随口第'+str(i)+'句话。',minutes=-4+i)
        self.assertEqual(self.active(),['address'])
        self.record('再说一句新的。',minutes=-.5);self.assertEqual(self.active(),[])
    def test_quoted_reported_conditional_and_code_text_cannot_change_local_style(self):
        for query in ['他说“后面别老喊爸爸”，你怎么看。','翻译：后面别老喊爸爸。','我看到帖子写：以后说话简短一点。','假如有人说以后别老喊爸爸，应该怎么回。','```text\n后面别老喊爸爸\n```\n这是测试材料。','> 后面别老喊爸爸\n这是别人的留言。']:
            with self.subTest(query=query):self.assertEqual(talk.style_events(query),[])
    def test_only_user_words_can_provide_feedback(self):
        self.record('我回来了。',assistant='后面别老喊爸爸，别每次都用问题收尾。')
        self.assertEqual(self.active(),[])
    def test_deleted_corrected_expired_and_future_versions_cannot_supply_feedback(self):
        for index,change in enumerate(["status='deleted'","corrected_at='2026-10-29T03:59:00+00:00'","valid_until='2026-10-29T03:59:00+00:00'","recorded_at='2026-10-29T04:01:00+00:00'","valid_from='2026-10-29T04:01:00+00:00'"]):
            session='scope-'+str(index);row=self.record('后面别老喊爸爸。',session=session)
            self.store.db.execute('UPDATE episodes SET '+change+' WHERE id=?',(row['id'],));self.store.db.commit()
            with self.subTest(change=change):self.assertEqual(self.active(session=session),[])
    def test_future_outputs_cannot_create_repetition_hints_or_playful_setups(self):
        for i in range(3):self.record('你今天有种电饭锅气质。',assistant='爹，脑子缓冲中，你觉得呢？',minutes=i+1)
        self.assertEqual(talk.recent_voice(self.store,'chat',self.now),[])
        self.assertEqual(talk.turn_mode('那就叫你锅锅吧。',self.store,'chat',self.now),'neutral')
    def test_stop_requests_are_feedback_and_a_new_real_task_still_wins(self):
        for query in ['不用解释了。','别再分析我了。','这段代码不用解释了。','不要继续讲解了。']:
            with self.subTest(query=query):self.assertEqual(talk.classify(query),'feedback')
        for query in ['不用解释，帮我修这个 bug。','后面别老喊爸爸，现在解释这段代码。','不用解释旧例子，讲解新的证明。','别再分析这个例子，直接修复代码。']:
            with self.subTest(query=query):self.assertEqual(talk.classify(query),'focused')


if __name__=='__main__':unittest.main()
