"""Fictional topic references; an earlier conversation is not a new recommendation."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import fish_conversation as talk
from fish_journal import Journal,tokens


class InterestFollowupTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.now=datetime(2026,10,31,12,tzinfo=timezone.utc)
        (self.root/'scripts').mkdir();shutil.copy2(Path(talk.__file__).with_name('curiosity.py'),self.root/'scripts/curiosity.py')
        self.threads=[];observations=[];visited=[]
        for index,name in enumerate(('纸齿轮','玻璃花盆')):
            ident='cur-'+str(index)*12;url=f'https://example.org/item-{index}';seen=self.now-timedelta(hours=4-index)
            report=f'reports/2026-10-31/{index:04d}-surf.md';path=self.root/report;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(url)
            observations.append({'id':f'obs-{index}','url':url,'seen_at':seen.isoformat(),'report_path':report,'read_depth':'body','observation':name+'的具体结构。'})
            visited.append({'url':url,'report':report,'read_at':seen.isoformat()})
            self.threads.append({'id':ident,'question':name+'后来怎么做出来？','why':'还想看看它的结构。','status':'open','expires_at':(self.now+timedelta(days=7)).isoformat(),'source_urls':[url],'evidence_ids':[f'obs-{index}']})
        path=self.root/'data/personality/observations.jsonl';path.parent.mkdir(parents=True);path.write_text(''.join(json.dumps(row)+'\n'for row in observations))
        self.write('data/surf-state.json',{'visited':visited});self.write('data/curiosity/state.json',{'threads':self.threads})
    def write(self,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def mention(self,index=0,session='chat',at=None):
        talk.note_chat_links(self.root,'[这件作品]('+self.threads[index]['source_urls'][0]+')',at or self.now-timedelta(hours=1),session_id=session)
    def chosen(self,query='上次那个后来怎样了？',session='chat'):
        return [row['id']for row in talk.interest_material(self.root,query,now=self.now,session_id=session)]
    def test_followup_selects_discussed_topic_instead_of_the_new_unseen_interest(self):
        self.mention();self.assertEqual(self.chosen(),[self.threads[0]['id']])
        self.assertEqual(self.chosen('那后来怎么样了？'),[self.threads[0]['id']])
        self.assertEqual(self.chosen('上次那个还有后续吗？'),[self.threads[0]['id']])
        # A new invitation still prefers something not already shared.
        self.assertEqual(self.chosen('最近看到了什么好玩的？'),[self.threads[1]['id']])
    def test_named_topic_overrides_the_implicit_pointer_and_ambiguous_names_abstain(self):
        self.mention();self.assertEqual(self.chosen('上次那个玻璃花盆后来怎样了？'),[self.threads[1]['id']])
        self.assertEqual(self.chosen('上次那个“玻璃花盆”后来怎样了？'),[self.threads[1]['id']])
        self.assertEqual(self.chosen('上次那个纸齿轮和玻璃花盆后来怎样了？'),[])
        self.assertEqual(self.chosen('上次那个木头大象后来怎样了？'),[])
        self.assertEqual(self.chosen('上次那个猫后来怎样了？'),[])
    def test_explicitly_rejecting_the_old_topic_does_not_resume_it(self):
        self.mention();self.assertFalse(talk.followup_invitation('别说上次那个，最近刷到什么新东西？'))
        self.assertEqual(self.chosen('别说上次那个，最近刷到什么新东西？'),[self.threads[1]['id']])
        self.assertFalse(talk.followup_invitation('上次那个不聊了，看看新的。'))
    def test_user_pause_keeps_the_previous_topic_from_being_replaced_by_another(self):
        from fish_interest import change
        shutil.copy2(Path(talk.__file__).with_name('fish_interest.py'),self.root/'scripts/fish_interest.py')
        self.mention(0,at=self.now-timedelta(minutes=5));self.mention(1,at=self.now-timedelta(minutes=2))
        result=change(self.root,{'id':self.threads[1]['id'],'choice':'pause','revision':0},self.now)
        self.assertEqual(self.chosen(),[]);self.assertEqual(self.chosen('最近看到了什么好玩的？'),[self.threads[0]['id']])
        change(self.root,{'id':self.threads[1]['id'],'choice':'resume','revision':result['revision']},self.now)
        self.assertEqual(self.chosen(),[self.threads[1]['id']])
    def test_no_session_or_legacy_global_reference_does_not_guess_an_old_topic(self):
        self.write('data/curiosity/chat-references.json',{self.threads[0]['id']:{'last_chatted_at':(self.now-timedelta(hours=1)).isoformat()}})
        self.assertEqual(self.chosen(),[]);self.assertEqual(self.chosen(session=''),[])
        self.assertEqual(self.chosen('上次那个纸齿轮后来怎样了？'),[self.threads[0]['id']])
    def test_unread_letter_is_not_a_conversation_anchor(self):
        self.write('data/inbox.json',{'messages':[{'source_url':self.threads[0]['source_urls'][0],'sent_at':(self.now-timedelta(minutes=5)).isoformat(),'read_at':None}]})
        self.assertEqual(self.chosen(),[])
    def test_sessions_keep_their_own_last_topic_even_when_the_same_thread_is_reused(self):
        self.mention(0,'a',self.now-timedelta(minutes=5));self.mention(1,'b',self.now-timedelta(minutes=4))
        self.mention(0,'b',self.now-timedelta(minutes=3))
        self.assertEqual(self.chosen(session='a'),[self.threads[0]['id']]);self.assertEqual(self.chosen(session='b'),[self.threads[0]['id']])
        self.mention(1,'b',self.now-timedelta(minutes=2))
        self.assertEqual(self.chosen(session='a'),[self.threads[0]['id']]);self.assertEqual(self.chosen(session='b'),[self.threads[1]['id']])
        self.assertEqual(self.chosen(session='unrelated'),[])
    def test_expired_closed_paused_or_lost_latest_topic_never_falls_back_to_an_older_one(self):
        self.mention(0,at=self.now-timedelta(minutes=5));self.mention(1,at=self.now-timedelta(minutes=2))
        for change in ({'status':'closed'},{'expires_at':(self.now-timedelta(seconds=1)).isoformat()},{'snoozed_until':(self.now+timedelta(days=1)).isoformat()},{'evidence_ids':['missing']}):
            with self.subTest(change=change):
                self.write('data/curiosity/state.json',{'threads':[self.threads[0],{**self.threads[1],**change}]});self.assertEqual(self.chosen(),[])
    def test_ambiguous_reply_and_later_unrelated_link_clear_the_pointer(self):
        self.mention()
        talk.note_chat_links(self.root,' '.join(self.threads[i]['source_urls'][0]for i in (0,1)),self.now-timedelta(minutes=5),session_id='chat')
        self.assertEqual(self.chosen(),[])
        self.mention();talk.note_chat_links(self.root,'https://example.org/unrelated',self.now-timedelta(minutes=1),session_id='chat')
        self.assertEqual(self.chosen(),[])
        self.mention();talk.note_chat_links(self.root,self.threads[0]['source_urls'][0]+' https://example.org/unrelated',self.now-timedelta(minutes=1),session_id='chat')
        self.assertEqual(self.chosen(),[])
    def test_stale_future_and_malformed_pointer_is_not_injected(self):
        for at in (self.now-timedelta(days=7),self.now+timedelta(seconds=1)):
            self.mention(at=at);self.assertEqual(self.chosen(),[])
        self.write('data/curiosity/chat-references.json',{'_sessions':{'chat':{'thread_ids':'invalid','last_chatted_at':'invalid'}}})
        self.assertEqual(self.chosen(),[])
    def test_lookup_is_read_only_and_context_receives_the_current_session(self):
        self.mention();files=[self.root/'data/curiosity/chat-references.json',self.root/'data/curiosity/state.json',self.root/'data/personality/observations.jsonl']
        before=[p.read_bytes()for p in files]
        with Journal(self.root,now=self.now)as journal:
            result=talk.context(self.root,'上次那个后来怎样了？',journal=journal,session_id='chat',tokenize=tokens,now=self.now)
        self.assertIn(self.threads[0]['id'],result);self.assertNotIn(self.threads[1]['id'],result)
        self.assertEqual([p.read_bytes()for p in files],before);self.assertFalse((self.root/'.hermes/SOUL.md').exists())
    def test_reference_metadata_is_bounded_and_normal_legacy_marks_remain(self):
        self.mention()
        for index in range(85):self.mention(session='fiction-'+str(index),at=self.now-timedelta(seconds=100-index))
        value=talk.read(self.root/'data/curiosity/chat-references.json',{})
        self.assertLessEqual(len(value['_sessions']),80);self.assertIn('last_chatted_at',value[self.threads[0]['id']])
        self.assertNotIn('fiction-0',value['_sessions']);self.assertEqual(self.chosen(session='fiction-84'),[self.threads[0]['id']])
        # Browsing does not mistake a follow-up phrase for a mandatory topic.
        material=talk.interest_material(self.root,'上次那个',now=self.now,for_browsing=True)
        self.assertEqual(len(material),2)


if __name__=='__main__':unittest.main()
