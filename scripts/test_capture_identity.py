from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import sqlite3
import tempfile
import unittest
from fish_journal import Journal


class CaptureIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=datetime(2026,11,1,4,tzinfo=timezone.utc)
    def test_equal_text_in_distinct_native_turns_keeps_times_and_retry_is_idempotent(self):
        with Journal(self.root,now=self.now)as journal:
            first=journal.capture('chat','回来看看。','在呢。',self.now-timedelta(hours=1),source_event='a'*64)
            second=journal.capture('chat','回来看看。','在呢。',self.now,source_event='b'*64)
            retried=journal.capture('rotated','回来看看。','在呢。',self.now+timedelta(minutes=1),source_event='a'*64)
            self.assertNotEqual(first['id'],second['id']);self.assertEqual(first,retried)
            self.assertEqual(journal.status()['total'],2)
            self.assertEqual(first['recorded_at'],(self.now-timedelta(hours=1)).isoformat())
            self.assertEqual(journal.db.execute('SELECT count(*) FROM episode_capture_sources').fetchone()[0],2)
    def test_distinct_native_turns_stay_distinct_even_if_delivery_order_is_reversed(self):
        with Journal(self.root,now=self.now)as journal:
            later=journal.capture('chat','回来看看。','在呢。',self.now,source_event='a'*64)
            earlier=journal.capture('chat','回来看看。','在呢。',self.now-timedelta(hours=1),source_event='b'*64)
            self.assertNotEqual(later['id'],earlier['id']);self.assertEqual(journal.status()['total'],2)
    def test_legacy_replay_alias_keeps_id_and_later_equal_turn_is_new(self):
        with Journal(self.root,now=self.now)as journal:
            legacy=journal.capture('chat','回来看看。','在呢。')
            replay=journal.capture('chat','回来看看。','在呢。',self.now-timedelta(seconds=1),source_event='a'*64)
            self.assertEqual(legacy,replay)
            later=journal.capture('chat','回来看看。','在呢。',self.now+timedelta(days=1),source_event='b'*64)
            self.assertNotEqual(later['id'],legacy['id'])
            self.assertEqual(journal.capture('copy','回来看看。','在呢。',source_event='a'*64),legacy)
    def test_native_receipts_keep_correction_and_forget_without_relearning(self):
        with Journal(self.root,now=self.now)as journal:
            row=journal.capture('chat','聊聊积木机关。','可以。',source_event='a'*64)
            corrected=journal.update(row['id'],1,summary='更正：只是看到积木，没有聊机关。')['episode']
            self.assertEqual(journal.capture('chat','不同回放文本。','变化。',source_event='a'*64),corrected)
            journal.update(row['id'],corrected['revision'],forget=True)
            self.assertEqual(journal.capture('copy','聊聊积木机关。','可以。',source_event='a'*64)['excerpt'],'')
            self.assertEqual(journal.status()['total'],0)
            self.assertEqual(journal.capture('chat','聊聊积木机关。','可以。')['excerpt'],'')
            self.assertEqual(journal.status()['total'],0)
    def test_legacy_tombstone_is_not_revived_by_new_identity_receipt(self):
        with Journal(self.root,now=self.now)as journal:
            old=journal.capture('chat','聊聊积木机关。','可以。');journal.update(old['id'],1,forget=True)
            replay=journal.capture('chat','聊聊积木机关。','可以。',self.now-timedelta(seconds=1),source_event='a'*64)
            self.assertEqual(replay['id'],old['id']);self.assertEqual(replay['excerpt'],'')
            self.assertEqual(journal.status()['total'],0)
    def test_concurrent_duplicate_receipts_publish_once(self):
        with Journal(self.root):pass
        def capture(_):
            with Journal(self.root,now=self.now)as journal:return journal.capture('chat','回来看看。','在呢。',source_event='a'*64)['id']
        with ThreadPoolExecutor(max_workers=4)as pool:ids=list(pool.map(capture,range(4)))
        self.assertEqual(len(set(ids)),1)
        with Journal(self.root)as journal:
            self.assertEqual(journal.status()['total'],1)
            self.assertEqual(journal.db.execute('SELECT count(*) FROM episode_capture_sources').fetchone()[0],1)
    def test_failed_index_does_not_leave_half_a_source_receipt(self):
        with Journal(self.root,now=self.now)as journal:
            with patch.object(journal,'_index',side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):journal.capture('chat','回来看看。','在呢。',source_event='a'*64)
            self.assertEqual(journal.status()['total'],0)
            self.assertEqual(journal.db.execute('SELECT count(*) FROM episode_capture_sources').fetchone()[0],0)
            self.assertIsNotNone(journal.capture('chat','回来看看。','在呢。',source_event='a'*64))
    def test_additive_identity_bootstrap_preserves_existing_rows_and_schema_version(self):
        with Journal(self.root,now=self.now)as journal:
            journal.capture('chat','回来看看。','在呢。');before=[tuple(r)for r in journal.db.execute('SELECT * FROM episodes')]
            version=journal.db.execute('PRAGMA user_version').fetchone()[0]
            journal.db.execute('DROP TABLE episode_capture_sources');journal.db.execute("DELETE FROM journal_meta WHERE key='capture_version'");journal.db.commit()
        with Journal(self.root,now=self.now)as journal:
            self.assertEqual(before,[tuple(r)for r in journal.db.execute('SELECT * FROM episodes')])
            self.assertEqual(version,journal.db.execute('PRAGMA user_version').fetchone()[0])
            self.assertEqual(journal.db.execute('SELECT count(*) FROM episode_capture_sources').fetchone()[0],0)
    def test_invalid_identity_is_not_written(self):
        with Journal(self.root,now=self.now)as journal:
            for value in ('invalid','A'*64,True,[]):
                with self.subTest(value=value),self.assertRaises(ValueError):journal.capture('chat','回来看看。','在呢。',source_event=value)
            self.assertEqual(journal.status()['total'],0)
    def test_equal_turns_do_not_duplicate_recall_context_or_personality_support_groups(self):
        from personality import resolve_evidence
        with Journal(self.root,now=self.now)as journal:
            first=journal.capture('chat','又来看看折纸机关。','先看看怎样折叠。',self.now-timedelta(days=1),source_event='a'*64)
            second=journal.capture('chat','又来看看折纸机关。','先看看怎样折叠。',self.now,source_event='b'*64)
            self.assertEqual(len(journal.search('折纸机关')),1)
            self.assertEqual(journal.search('昨天折纸机关')[0]['id'],first['id'])
            self.assertEqual(journal.search('今天折纸机关')[0]['id'],second['id'])
            evidence=resolve_evidence(self.root,[first['id'],second['id']],self.now,journal)
            self.assertEqual(len({r['group']for r in evidence}),1)


if __name__=='__main__':unittest.main()
