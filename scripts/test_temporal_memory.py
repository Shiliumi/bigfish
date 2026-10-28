from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fish_journal import Journal

class TemporalMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.now=datetime(2026,10,1,12,tzinfo=timezone.utc)
    def capture(self):
        with Journal(self.root,now=self.now) as store:return store.capture('chat-a','阿蓝以前在广州工作','阿蓝的旧工作地是广州。')
    def test_correction_replaces_original_meaning_in_index_and_recall(self):
        row=self.capture()
        with Journal(self.root,now=self.now+timedelta(hours=1)) as store:
            store.update(row['id'],1,summary='阿蓝现在在杭州工作。')
            self.assertEqual(store.search('广州'),[]);context=store.recall('阿蓝');self.assertIn('杭州',context);self.assertNotIn('广州',context)
            self.assertIn('广州',store.get(row['id'])['excerpt']);self.assertEqual(len(store.history(row['id'])),1)
    def test_expiry_exact_boundary_and_pinning_never_bypass_it(self):
        row=self.capture();expiry=self.now+timedelta(days=1)
        with Journal(self.root,now=self.now) as store:store.update(row['id'],1,pinned=True,valid_until=expiry.isoformat())
        with Journal(self.root,now=expiry) as store:
            self.assertEqual(store.search('阿蓝'),[]);self.assertEqual(store.recall('阿蓝'),'');self.assertEqual(store.status()['historical'],1)
            self.assertEqual(len(store.search(scope='history')),1);self.assertEqual(store.revisions(),{})
    def test_impressions_default_to_thirty_days_and_can_be_retired(self):
        row=self.capture()
        with Journal(self.root,now=self.now) as store:
            updated=store.update(row['id'],1,kind='impression')['episode'];self.assertEqual(updated['valid_until'],(self.now+timedelta(days=30)).isoformat())
            store.update(row['id'],2,invalidate=True);self.assertEqual(store.recall('阿蓝'),'')
    def test_expired_record_needs_explicit_new_validity(self):
        row=self.capture()
        with Journal(self.root,now=self.now) as store:store.update(row['id'],1,invalidate=True)
        with Journal(self.root,now=self.now+timedelta(hours=1)) as store:
            with self.assertRaises(ValueError):store.update(row['id'],2,summary='阿蓝现在在成都。')
            store.update(row['id'],2,summary='阿蓝现在在成都。',valid_until=None)
            self.assertIn('成都',store.recall('阿蓝'));self.assertNotIn('广州',store.recall('阿蓝'))
    def test_invalid_time_and_stale_edits_are_atomic(self):
        row=self.capture()
        with Journal(self.root,now=self.now) as store:
            for invalid in ['2026-10-02T12:00:00',42,'not-a-date']:
                with self.assertRaises(ValueError):store.update(row['id'],1,summary='阿蓝现在改成别的情况。',valid_until=invalid)
            self.assertEqual(store.get(row['id'])['revision'],1);self.assertEqual(store.history(row['id']),[])
            store.update(row['id'],1,pinned=True)
            with self.assertRaises(ValueError):store.update(row['id'],1,summary='stale overwrite')
    def test_forgetting_erases_version_text_and_prevents_replay(self):
        row=self.capture()
        with Journal(self.root,now=self.now+timedelta(hours=1)) as store:
            store.update(row['id'],1,summary='阿蓝现在在杭州工作。');store.update(row['id'],2,forget=True)
            self.assertEqual(store.history(row['id']),[]);self.assertEqual(store.search('阿蓝',scope='history'),[])
            store.capture('chat-a','阿蓝以前在广州工作','阿蓝的旧工作地是广州。');self.assertEqual(store.status()['total'],0)
    def test_v17_edited_summary_migration_stops_recalling_old_excerpt(self):
        directory=self.root/'data/memory';directory.mkdir(parents=True)
        with sqlite3.connect(directory/'episodes.sqlite3') as db:
            db.executescript("CREATE TABLE episodes(id TEXT PRIMARY KEY, session_id TEXT,source_ref TEXT,recorded_at TEXT,summary TEXT,excerpt TEXT,status TEXT,revision INTEGER,pinned INTEGER,truncated INTEGER);CREATE VIRTUAL TABLE episode_search USING fts5(id UNINDEXED,terms)")
            db.execute('INSERT INTO episodes VALUES(?,?,?,?,?,?,?,?,?,?)',('ep-legacy','chat','session:chat',self.now.isoformat(),'阿蓝目前在杭州工作。','你：阿蓝在广州\n大肥鱼：以前是广州。','active',2,0,0))
        with Journal(self.root,now=self.now) as store:
            self.assertIsNotNone(store.get('ep-legacy')['corrected_at']);self.assertNotIn('广州',store.recall('阿蓝'));self.assertIn('杭州',store.recall('阿蓝'))

if __name__=='__main__':unittest.main()
