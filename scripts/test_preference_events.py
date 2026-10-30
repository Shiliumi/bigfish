"""Source-bound personality events for automatic review; fictional state only."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
import shutil
import subprocess
from unittest.mock import patch
import personality as growth
import activity_gate as gate
from fish_journal import Journal


class PreferenceEventTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.now=datetime.now(timezone.utc)-timedelta(minutes=5)
        self.text='我似乎喜欢从黑糖火山这个小反差里接一句。';self.reason='黑糖火山这个虚构画面让我确实想再接一句。'
        with Journal(self.root,now=self.now)as journal:self.source=journal.capture('fiction','一起看看黑糖火山。','这个纸片机关有一个小反差。')
        self.trial=growth.propose_trial(self.root,{'id':'paper-reaction','kind':'expression','text':self.text,'reason':self.reason,'evidence_ids':[self.source['id']]},self.now)
    def selected(self):
        return {row['id']:growth.event_fingerprint(row)for row in growth.trial_state(self.root)['events']}
    def view(self):return growth.review_events(self.root,self.selected())
    def change_source(self,action):
        with Journal(self.root,now=self.now)as journal:
            if action=='forgotten':journal.update(self.source['id'],1,forget=True)
            elif action=='corrected':journal.update(self.source['id'],1,summary='更正：前面只是给角色写的台词，不是实际兴趣。')
            elif action=='expired':journal.update(self.source['id'],1,invalidate=True)
            elif action=='future':
                journal.db.execute('UPDATE episodes SET valid_from=? WHERE id=?',((datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),self.source['id']));journal.db.commit()
    def batch(self):
        batch=gate.pending(self.root);gate.write(self.root/f"data/automation/reviews/{batch['id']}.json",batch);return batch
    def finish(self,batch):
        name=f"reports/2026-10-31/memory-review-{batch['id'][:12]}.md";path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Review-Snapshot: '+batch['id'])
        return gate.commit(self.root,batch['id'],name)
    def test_new_event_records_only_source_ids_and_meaning_fingerprints(self):
        event=growth.trial_state(self.root)['events'][0];self.assertEqual(event['evidence_version'],1)
        with Journal(self.root,now=self.now)as journal:proof=growth.resolve_evidence(self.root,[self.source['id']],self.now,journal)[0]
        self.assertEqual(event['evidence'],[{'id':proof['id'],'fingerprint':proof['fingerprint']}]);self.assertNotIn('excerpt',event['evidence'][0])
        item=self.view()[0];self.assertEqual(item['source_state'],'verified');self.assertEqual(item['text'],self.text);self.assertEqual(item['reason'],self.reason)
    def test_each_source_invalidation_withholds_both_old_text_and_reason(self):
        # Each action gets an independent copy of the same prepared fictional state.
        import shutil
        for action in ('forgotten','corrected','expired','future'):
            with self.subTest(action=action),tempfile.TemporaryDirectory()as directory:
                clone=Path(directory);shutil.copytree(self.root,clone,dirs_exist_ok=True);original=self.root;self.root=clone
                try:
                    self.change_source(action);item=self.view()[0]
                    self.assertEqual(item['source_state'],'unavailable');self.assertNotIn('text',item);self.assertNotIn('reason',item)
                    self.assertNotIn('黑糖火山',json.dumps(item,ensure_ascii=False))
                finally:self.root=original
    def test_legacy_events_are_metadata_only_without_guessing_their_source_version(self):
        state=growth.trial_state(self.root);state['events'][0].pop('evidence');state['events'][0].pop('evidence_version');growth.save_trials(self.root,state)
        before=(self.root/'data/personality/trials.json').read_bytes();item=self.view()[0]
        self.assertEqual(item['source_state'],'unbound');self.assertEqual(item['action'],'started');self.assertNotIn('text',item)
        self.assertEqual((self.root/'data/personality/trials.json').read_bytes(),before)
    def test_fresh_feedback_does_not_restore_the_forgotten_event(self):
        self.change_source('forgotten')
        with Journal(self.root,now=self.now+timedelta(minutes=1))as journal:fresh=journal.capture('fiction-fresh','再看看另一件折纸作品。','这个结构确实又让我想试试短接话。')
        growth.trial_feedback(self.root,{'id':self.trial['id'],'revision':self.trial['revision'],'outcome':'enjoyed','reason':'新的折纸结构提供了另一件确实读到的反差。','evidence_ids':[fresh['id']]},self.now+timedelta(minutes=1))
        old,new=self.view();self.assertNotIn('text',old);self.assertEqual(new['source_state'],'verified')
        self.assertIn('新的折纸',new['reason']);self.assertNotIn(self.reason,json.dumps(self.view(),ensure_ascii=False))
        with Journal(self.root)as journal:self.assertEqual(journal.get(self.source['id'])['status'],'deleted')
    def test_retirement_keeps_the_action_without_republishing_an_unbound_old_phrase(self):
        self.change_source('forgotten');growth.retire_trial(self.root,{'id':self.trial['id'],'revision':self.trial['revision'],'reason':'明确放下这个尝试，不恢复旧的措辞。'},self.now+timedelta(minutes=1))
        item=self.view()[-1];self.assertEqual(item['action'],'retired');self.assertNotIn('text',item);self.assertNotIn('reason',item)
        self.assertEqual(growth.trial_state(self.root)['events'][-1]['text'],self.text)
    def test_malformed_proofs_or_future_events_do_not_expose_their_body(self):
        original=growth.trial_state(self.root)
        for proofs in ([{'id':self.source['id'],'fingerprint':'invalid'}],[{'id':[],'fingerprint':'a'*64}],[],None):
            state=json.loads(json.dumps(original));state['events'][0]['evidence']=proofs;growth.save_trials(self.root,state)
            self.assertNotIn('text',self.view()[0]);self.assertNotIn('reason',self.view()[0])
        state=json.loads(json.dumps(original));state['events'][0]['at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat();growth.save_trials(self.root,state)
        self.assertNotIn('text',self.view()[0])
        state=json.loads(json.dumps(original));state['events'][0]['evidence_version']=True;growth.save_trials(self.root,state)
        self.assertNotIn('text',self.view()[0])
    def test_snapshot_event_mutation_is_rejected_before_returning_a_different_body(self):
        selected=self.selected();state=growth.trial_state(self.root);state['events'][0]['reason']='修改后的事件理由，不能当旧版本返回。';growth.save_trials(self.root,state)
        with self.assertRaises(ValueError):growth.review_events(self.root,selected)
        with self.assertRaises(ValueError):growth.review_events(self.root,{'pref-missing':'a'*64})
    def test_gate_review_does_not_bring_back_a_forgotten_event_body(self):
        self.change_source('forgotten');batch=self.batch();packet=gate.review(self.root,batch['id'])
        self.assertEqual(packet['episodes'],[]);self.assertNotIn('黑糖火山',json.dumps(packet,ensure_ascii=False))
        self.assertEqual(packet['preference_events'][0]['source_state'],'unavailable')
        self.assertIn('独立新经历',packet['preference_boundary']);self.assertTrue(self.finish(batch)['ok'])
    def test_event_body_view_must_be_delivered_before_commit(self):
        batch=self.batch();gate.review(self.root,batch['id'],self.source['id'])
        with self.assertRaises(ValueError):self.finish(batch)
        self.assertFalse((self.root/'data/automation/review-cursor.json').exists())
        gate.review(self.root,batch['id']);self.assertTrue(self.finish(batch)['ok'])
    def test_source_changed_after_review_blocks_commit_even_when_event_bytes_are_unchanged(self):
        # The source was reviewed in an earlier batch; only the event is pending now.
        for action in ('forgotten','corrected'):
            with self.subTest(action=action),tempfile.TemporaryDirectory()as directory:
                clone=Path(directory);shutil.copytree(self.root,clone,dirs_exist_ok=True);original=self.root;self.root=clone
                try:
                    gate.write(self.root/'data/automation/review-cursor.json',{'episodes':{self.source['id']:1}})
                    batch=self.batch();self.assertEqual(batch['selected']['episodes'],{})
                    gate.review(self.root,batch['id']);selected_before=dict(batch['selected']['preference_events'])
                    self.change_source(action);self.assertEqual(self.selected(),selected_before)
                    with self.assertRaises(ValueError):self.finish(batch)
                    packet=gate.review(self.root,batch['id']);self.assertNotIn('text',packet['preference_events'][0]);self.assertTrue(self.finish(batch)['ok'])
                    if action=='corrected':self.assertEqual(gate.pending(self.root)['selected']['episodes'],{self.source['id']:2})
                finally:self.root=original
    def test_late_event_error_never_acknowledges_episode_delivery(self):
        batch=self.batch()
        with patch('personality.review_events',side_effect=ValueError('fictional event view failure')):
            with self.assertRaises(ValueError):gate.review(self.root,batch['id'])
        value=gate.snapshot(self.root,batch['id']);self.assertNotIn('delivered_episodes',value);self.assertNotIn('delivered_preference_events',value)
    def test_current_review_is_read_only_for_trials_and_shared_journal(self):
        before=(self.root/'data/personality/trials.json').read_bytes()
        with Journal(self.root)as journal:
            changes=journal.db.total_changes;growth.review_events(self.root,self.selected(),journal=journal);self.assertEqual(journal.db.total_changes,changes)
        self.assertEqual((self.root/'data/personality/trials.json').read_bytes(),before)
    def cli(self,*args):
        scripts=self.root/'scripts';scripts.mkdir(exist_ok=True)
        for name in ('personality.py','fish_journal.py'):shutil.copy2(Path(growth.__file__).with_name(name),scripts/name)
        result=subprocess.run(['python3',str(scripts/'personality.py'),*args],capture_output=True,text=True,cwd=self.root.parent)
        self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
    def test_automatic_trials_view_does_not_leak_through_the_state_or_history(self):
        self.change_source('forgotten');before=(self.root/'data/personality/trials.json').read_bytes()
        view=self.cli('trials');self.assertNotIn('黑糖火山',json.dumps(view,ensure_ascii=False))
        self.assertEqual(view['trials'][0]['stage'],'reconsidering');self.assertNotIn('last_reason',view['trials'][0])
        human=growth.preference_snapshot(self.root);self.assertEqual(human['trials'][0]['text'],self.text);self.assertEqual(human['history'][0]['reason'],self.reason)
        self.assertEqual((self.root/'data/personality/trials.json').read_bytes(),before)
    def test_current_trial_survives_a_legacy_event_without_reviving_its_unbound_reason(self):
        state=growth.trial_state(self.root);state['events'][0].pop('evidence_version');state['events'][0].pop('evidence');growth.save_trials(self.root,state)
        view=growth.trial_review(self.root);self.assertEqual(view['trials'][0]['text'],self.text);self.assertNotIn('last_reason',view['trials'][0])
        self.assertNotIn('reason',view['history'][0]);self.assertNotIn('text',view['history'][0])
    def test_trial_and_feedback_cli_acknowledge_revision_without_dumping_old_signals(self):
        candidate=self.root/'trial.json';candidate.write_text(json.dumps({'id':'another-reaction','text':'我似乎喜欢再看纸片结构的小机关。','kind':'interest','reason':'这个实际见过的小机关让我想继续看看。','evidence_ids':[self.source['id']]}))
        started=self.cli('trial',str(candidate));self.assertTrue(started['ok']);self.assertEqual(started['revision'],1);self.assertNotIn('signals',started);self.assertNotIn('text',started)
        self.change_source('forgotten')
        with Journal(self.root)as journal:fresh=journal.capture('fresh-cli','新的折纸作品展开了。','这次的小反差又让我想再看看。')
        feedback=self.root/'feedback.json';feedback.write_text(json.dumps({'id':self.trial['id'],'revision':self.trial['revision'],'outcome':'enjoyed','reason':'新作品的具体反差支持再次试一试。','evidence_ids':[fresh['id']]}))
        result=self.cli('feedback',str(feedback));self.assertTrue(result['ok']);self.assertEqual(result['revision'],2);self.assertNotIn('黑糖火山',json.dumps(result,ensure_ascii=False))
        saved=next(row for row in growth.trial_state(self.root)['trials']if row['id']==self.trial['id']);self.assertEqual(len(saved['signals']),2)
    def test_apply_cli_returns_an_ack_and_preserves_the_full_profile_on_disk(self):
        soul=self.root/'.hermes/SOUL.md';soul.parent.mkdir(exist_ok=True);soul.write_text('手动身份\n'+growth.START+'\n原区\n'+growth.END+'\n手动结尾')
        when=self.now-timedelta(days=4);ids=[];trial=None
        for index in range(3):
            at=when+timedelta(days=index)
            with Journal(self.root,now=at)as journal:row=journal.capture('promotion-'+str(index),'独立折纸作品'+str(index),'这个机关带来另一种具体反差'+str(index))
            ids.append(row['id'])
            if trial is None:trial=growth.propose_trial(self.root,{'id':'growing-interest','kind':'interest','text':'我似乎喜欢追看折纸结构中的具体机关。','reason':'这个具体机关让我想继续看看独立作品。','evidence_ids':[row['id']]},at)
            else:trial=growth.trial_feedback(self.root,{'id':trial['id'],'revision':trial['revision'],'outcome':'enjoyed','reason':'另一次实际经历又提供了新的独立结构。','evidence_ids':[row['id']]},at)
        candidate=self.root/'promotion.json';candidate.write_text(json.dumps({'traits':[{'id':trial['id'],'trial_id':trial['id'],'trial_revision':trial['revision'],'text':trial['text'],'evidence_ids':ids}]}))
        result=self.cli('apply',str(candidate));self.assertTrue(result['ok']);self.assertEqual(result['updated_ids'],[trial['id']]);self.assertNotIn('traits',result)
        profile=growth.load(self.root/'data/personality/profile.json',{});self.assertEqual(profile['traits'][0]['text'],trial['text']);self.assertEqual(len(profile['traits'][0]['evidence_fingerprints']),3)
        self.assertTrue(soul.read_text().startswith('手动身份'));self.assertTrue(soul.read_text().endswith('手动结尾'))


if __name__=='__main__':unittest.main()
