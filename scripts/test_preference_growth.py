from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import personality as growth
from fish_journal import Journal

class PreferenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.now=datetime(2026,10,1,12,tzinfo=timezone.utc)
        (self.root/'.hermes').mkdir();self.soul='手动身份与边界\n'+growth.START+'\n旧区\n'+growth.END+'\n手动尾部';(self.root/'.hermes/SOUL.md').write_text(self.soul)
        self.text='我似乎更愿意看有具体机关和小巧思的积木作品。';self.ids=[]
    def episode(self,n,repeat=False):
        with Journal(self.root,now=self.now+timedelta(days=n)) as store:row=store.capture('chat-'+str(n),'一起看看积木厨房'+('同一段'if repeat else str(n)),'这个机关'+('完全一样'if repeat else str(n))+'的小巧思很吸引我。')
        self.ids.append(row['id']);return row
    def start(self):
        row=self.episode(0);return growth.propose_trial(self.root,{'id':'tiny-builds','text':self.text,'kind':'interest','reason':'这次真正看到具体机关，还想继续看看。','evidence_ids':[row['id']]},self.now)
    def follow(self,trial,n,outcome='enjoyed'):
        row=self.episode(n);return growth.trial_feedback(self.root,{'id':trial['id'],'revision':trial['revision'],'evidence_ids':[row['id']],'outcome':outcome,'reason':'后续这个作品的具体机关让我又想多看一会儿。'},self.now+timedelta(days=n))
    def ready(self):
        trial=self.start();trial=self.follow(trial,1);trial=self.follow(trial,2);return trial
    def proposal(self,trial):return {'traits':[{'id':trial['id'],'trial_id':trial['id'],'trial_revision':trial['revision'],'text':trial['text'],'evidence_ids':self.ids.copy()}]}
    def test_followups_and_observation_period_required(self):
        trial=self.ready()
        with self.assertRaises(ValueError):growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=2))
        growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=3))['trials'][0]['stage'],'stable')
        soul=(self.root/'.hermes/SOUL.md').read_text();self.assertTrue(soul.startswith('手动身份与边界'));self.assertTrue(soul.endswith('手动尾部'))
    def test_repeated_evidence_does_not_create_more_support(self):
        trial=self.start();data={'id':trial['id'],'revision':trial['revision'],'evidence_ids':self.ids.copy(),'outcome':'enjoyed','reason':'同一段内容再说一次，不应变成更多经历。'}
        first=growth.trial_feedback(self.root,data,self.now+timedelta(days=1));data['revision']=first['revision'];second=growth.trial_feedback(self.root,data,self.now+timedelta(days=2))
        self.assertTrue(second['already_recorded']);self.assertEqual(len(second['signals']),1)
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=4))['trials'][0]['stage'],'trying')
    def test_blocked_access_does_not_overwrite_positive_reaction(self):
        trial=self.start();value=growth.trial_feedback(self.root,{'id':trial['id'],'revision':trial['revision'],'evidence_ids':self.ids.copy(),'outcome':'blocked','reason':'平台当前要求登录，因此没有新的观看内容。'},self.now+timedelta(hours=1))
        self.assertEqual(value['signals'][0]['outcome'],'interested');self.assertFalse(growth.preference_snapshot(self.root,self.now+timedelta(days=1))['trials'][0]['needs_review'])
    def test_negative_does_not_disappear_just_by_waiting(self):
        trial=self.ready();growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3));self.follow(trial,4,'not_for_me')
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=20))['trials'][0]['stage'],'reconsidering')
    def test_corrected_support_invalidates_stable_trait(self):
        trial=self.ready();growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
        with Journal(self.root,now=self.now+timedelta(days=4)) as store:store.update(self.ids[1],1,summary='那次其实没读到作品，只看到了入口。')
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=4))['trials'][0]['stage'],'reconsidering')
        self.assertEqual(growth.preference_context(self.root,'积木厨房',now=self.now+timedelta(days=4))[0]['stage'],'reconsidering')
    def test_trials_fade_without_model_calls(self):
        self.start();self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=22))['trials'][0]['stage'],'faded')
    def test_retire_withdraws_only_owned_style_and_stale_requests_fail(self):
        trial=self.ready();growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
        with self.assertRaises(ValueError):growth.retire_trial(self.root,{'id':trial['id'],'revision':1},self.now+timedelta(days=4))
        growth.retire_trial(self.root,{'id':trial['id'],'revision':trial['revision']},self.now+timedelta(days=4))
        soul=(self.root/'.hermes/SOUL.md').read_text();self.assertNotIn(self.text,soul);self.assertTrue(soul.endswith('手动尾部'))
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=4))['trials'][0]['stage'],'retired')
    def test_cannot_skip_trial_or_change_wording_at_promotion(self):
        trial=self.ready();data=self.proposal(trial);data['traits'][0].pop('trial_id')
        with self.assertRaises(ValueError):growth.apply(self.root,data,self.now+timedelta(days=4))
        data=self.proposal(trial);data['traits'][0]['text']='我是永远不会变的另外一种人格。'
        with self.assertRaises(ValueError):growth.apply(self.root,data,self.now+timedelta(days=4))
    def test_identical_conversations_are_not_independent(self):
        rows=[self.episode(n,repeat=True)for n in range(3)]
        trial=growth.propose_trial(self.root,{'id':'tiny-builds','text':self.text,'reason':'确实喜欢具体机关，但这些其实是同一段话。','evidence_ids':[rows[0]['id']]},self.now)
        for n in (1,2):trial=growth.trial_feedback(self.root,{'id':trial['id'],'revision':trial['revision'],'outcome':'followed','evidence_ids':[rows[n]['id']],'reason':'重复同一对话不应该被看成三个独立内容。'},self.now+timedelta(days=n))
        with self.assertRaises(ValueError):growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
    def test_profile_write_failure_restores_manual_soul(self):
        trial=self.ready();original=growth.atomic
        def fail_profile(path,text):
            if path.name=='profile.json':raise OSError('simulated disk failure')
            return original(path,text)
        with patch.object(growth,'atomic',side_effect=fail_profile):
            with self.assertRaises(OSError):growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
        self.assertEqual((self.root/'.hermes/SOUL.md').read_text(),self.soul)

    def test_old_evidence_and_waiting_alone_never_promote(self):
        rows=[self.episode(n)for n in range(3)]
        trial=growth.propose_trial(self.root,{'id':'tiny-builds','text':self.text,'reason':'这些旧作品都很有意思，但还没有试行后的选择。','evidence_ids':[row['id']for row in rows]},self.now+timedelta(days=3))
        with self.assertRaises(ValueError):growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=7))
    def test_expired_episode_is_not_preference_support(self):
        trial=self.ready();growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
        with Journal(self.root,now=self.now+timedelta(days=3)) as store:store.update(self.ids[0],1,valid_until=(self.now+timedelta(days=4)).isoformat())
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=5))['trials'][0]['stage'],'reconsidering')
    def test_retire_rolls_back_style_when_profile_write_fails(self):
        trial=self.ready();growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3));soul=(self.root/'.hermes/SOUL.md').read_text();original=growth.atomic
        def fail_profile(path,text):
            if path.name=='profile.json':raise OSError('simulated profile write failure')
            return original(path,text)
        with patch.object(growth,'atomic',side_effect=fail_profile):
            with self.assertRaises(OSError):growth.retire_trial(self.root,{'id':trial['id'],'revision':trial['revision']},self.now+timedelta(days=4))
        self.assertEqual((self.root/'.hermes/SOUL.md').read_text(),soul)
        self.assertEqual(growth.preference_snapshot(self.root,self.now+timedelta(days=4))['trials'][0]['stage'],'stable')

    def test_long_lived_trial_can_read_more_than_twelve_signals(self):
        trial=self.start()
        for n in range(1,15):trial=self.follow(trial,n)
        row=growth.preference_snapshot(self.root,self.now+timedelta(days=15))['trials'][0]
        self.assertEqual(len(row['evidence']),15);self.assertEqual(row['stage'],'ready')

    def test_stable_trial_cannot_be_overwritten_and_review_guard_does_not_expire(self):
        trial=self.ready();growth.apply(self.root,self.proposal(trial),self.now+timedelta(days=3))
        with self.assertRaises(ValueError):growth.propose_trial(self.root,{'id':trial['id'],'text':self.text,'reason':'不应该覆盖已经稳定的原始尝试与证据。','evidence_ids':[self.ids[0]]},self.now+timedelta(days=30))
        with Journal(self.root,now=self.now+timedelta(days=4)) as store:store.update(self.ids[1],1,invalidate=True)
        context=growth.preference_context(self.root,'今天天气',now=self.now+timedelta(days=40))
        self.assertEqual(context[0]['stage'],'reconsidering')

if __name__=='__main__':unittest.main()
