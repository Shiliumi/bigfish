from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
import fish_interest as control


class InterestControlTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.now=datetime(2026,10,28,4,tzinfo=timezone.utc);self.ident='cur-123456789abc';self.url='https://example.org/folding'
        self.path=self.root/'data/curiosity/state.json';self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'threads':[{'id':self.ident,'question':'折叠凳的机关为什么能够锁住？','status':'open','expires_at':(self.now+timedelta(days=7)).isoformat(),'source_urls':[self.url]}],'runs':[]}))
        self.original=self.path.read_bytes()
    def change(self,choice,revision=0,**more):
        return control.change(self.root,{'id':self.ident,'choice':choice,'revision':revision,**more},self.now)
    def test_pause_last_exactly_three_days_and_applies_to_id_and_associated_source(self):
        result=self.change('pause');value=control.load_controls(self.root);self.assertEqual(result['revision'],1)
        for when in [self.now,self.now+timedelta(days=3,microseconds=-1)]:
            self.assertTrue(control.blocked(value,self.ident,now=when));self.assertTrue(control.blocked(value,'cur-abcdef123456',[self.url],when))
        self.assertFalse(control.blocked(value,self.ident,now=self.now+timedelta(days=3)))
        self.assertFalse(control.blocked(value,'cur-abcdef123456',['https://example.org/unrelated'],self.now))
        self.assertEqual(self.path.read_bytes(),self.original);self.assertFalse((self.root/'data/memory').exists())
    def test_retire_is_durable_and_resume_does_not_rewrite_expired_or_closed_threads(self):
        self.change('retire');self.assertTrue(control.blocked(control.load_controls(self.root),self.ident,now=self.now+timedelta(days=100)))
        self.change('resume',1);self.assertEqual(control.load_controls(self.root)['items'],[]);self.assertEqual(self.path.read_bytes(),self.original)
        self.assertTrue(self.change('resume',2)['unchanged'])
    def test_stale_version_cannot_override_a_newer_choice(self):
        self.change('retire')
        with self.assertRaises(ValueError):self.change('resume',0)
        self.assertTrue(control.blocked(control.load_controls(self.root),self.ident,now=self.now))
    def test_bad_store_never_silently_clears_user_choices(self):
        file=self.root/'data/curiosity/controls.json';file.write_text('{broken')
        with self.assertRaises(ValueError):self.change('pause')
        self.assertEqual(file.read_text(),'{broken')
    def test_invalid_operation_and_absent_thread_never_write_controls(self):
        for data in [{'choice':'erase'},{'id':'../outside'},{'id':'cur-abcdef123456'},{'revision':True}]:
            with self.assertRaises(ValueError):self.change('pause',**data) if 'choice'not in data else control.change(self.root,{'id':self.ident,'revision':0,**data},self.now)
        self.assertFalse((self.root/'data/curiosity/controls.json').exists())
    def test_private_key_in_question_or_source_is_not_copied(self):
        secret='fictional-private-key-without-prefix';env=self.root/'.hermes/.env';env.parent.mkdir();env.write_text('API_KEY='+secret)
        state=json.loads(self.path.read_text());state['threads'][0]['question']='折叠凳的机关'+secret;state['threads'][0]['source_urls']=[self.url+'/'+secret];self.path.write_text(json.dumps(state))
        self.change('retire');self.assertNotIn(secret,(self.root/'data/curiosity/controls.json').read_text())


if __name__=='__main__':unittest.main()
