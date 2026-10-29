from contextlib import closing
from datetime import datetime,timedelta,timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fish_journal import Journal
from fish_semantic_cache import SemanticCache

IDENTITY={'repo':'fiction/encoder','revision':'c'*40,'weight_sha256':'a'*64,'tokenizer_sha256':'b'*64,
          'dimension':2,'pooling':'normalized CLS','query_instruction':True}


class SemanticCacheTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.now=datetime(2026,10,29,4,tzinfo=timezone.utc)
        self.journal=Journal(self.root,now=self.now);self.addCleanup(self.journal.db.close)
        self.row=self.journal.capture('fiction-source','讨论铜色齿轮。','重新装正后不再卡住。')
        self.cache=SemanticCache(self.journal,IDENTITY);self.addCleanup(self.cache.db.close)
    def publish(self,job=None):
        job=job or self.cache.prepare(self.now)[0]
        self.assertTrue(self.cache.publish(job,[[1.,0.]]*len(job.texts),self.now));return job

    def test_warm_reopen_and_lookup_have_no_cache_writes_or_reencoding(self):
        self.publish()
        with SemanticCache(self.journal,IDENTITY)as cache:
            self.assertEqual(cache.prepare(self.now),[])
            matches=cache.rank([1,0],self.now);self.assertEqual(matches[0]['id'],self.row['id'])
            self.assertIn('铜色',cache.resolve(matches,self.now)[0]['excerpt'])
            self.assertEqual(cache.db.total_changes,0)

    def test_warm_lookup_can_read_committed_cache_while_another_writer_is_active(self):
        self.publish();connect=sqlite3.connect
        self.cache.db.execute('BEGIN IMMEDIATE')
        self.addCleanup(self.cache.db.rollback)
        def immediate(*args,**kwargs):
            kwargs['timeout']=0
            return connect(*args,**kwargs)
        with patch('fish_semantic_cache.sqlite3.connect',side_effect=immediate):
            with SemanticCache(self.journal,IDENTITY)as reader:
                self.assertEqual(reader.prepare(self.now),[])
                self.assertIn('铜色',reader.resolve(reader.rank([1,0],self.now),self.now)[0]['excerpt'])
                self.assertEqual(reader.db.total_changes,0)

    def test_correction_during_encoding_rejects_the_old_result(self):
        old=self.cache.prepare(self.now)[0]
        self.journal.update(self.row['id'],1,summary='实际讨论银色弹簧。')
        self.assertFalse(self.cache.publish(old,[[1,0]]*len(old.texts),self.now))
        current=self.cache.prepare(self.now)[0];self.assertEqual(current.texts,('实际讨论银色弹簧。',))
        self.publish(current);text=self.cache.resolve(self.cache.rank([1,0],self.now),self.now)[0]['excerpt']
        self.assertEqual(text,'实际讨论银色弹簧。');self.assertNotIn('铜色',text)

    def test_change_after_ranking_is_rechecked_at_materialization(self):
        self.publish();matches=self.cache.rank([1,0],self.now)
        self.journal.update(self.row['id'],1,summary='实际讨论银色弹簧。')
        self.assertEqual(self.cache.resolve(matches,self.now),[])
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0],0)

    def test_forgetting_blocks_late_publish_and_removes_vectors_on_next_access(self):
        old=self.publish();matches=self.cache.rank([1,0],self.now)
        self.journal.update(self.row['id'],1,forget=True)
        self.assertFalse(self.cache.publish(old,[[1,0]]*len(old.texts),self.now))
        self.assertEqual(self.cache.rank([1,0],self.now),[]);self.assertEqual(self.cache.resolve(matches,self.now),[])
        self.assertEqual(self.cache.prepare(self.now),[]);self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0],0)
        self.assertEqual(self.journal.get(self.row['id'])['status'],'deleted')

    def test_expiry_exact_boundary_and_future_source_are_not_returned(self):
        self.journal.update(self.row['id'],1,valid_until=(self.now+timedelta(hours=1)).isoformat())
        self.publish()
        future=self.journal.capture('future','未来的纸桥。','还没有发生。',(self.now+timedelta(days=1)).isoformat())
        self.assertEqual(self.cache.prepare(self.now),[])
        self.assertEqual(self.cache.rank([1,0],self.now+timedelta(hours=1)),[])
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0],0)

    def test_alias_changes_invalidate_the_prepared_meaning(self):
        old=self.cache.prepare(self.now)[0];self.journal.update(self.row['id'],1,aliases=['小铜轮'])
        self.assertFalse(self.cache.publish(old,[[1,0]]*len(old.texts),self.now))
        self.assertIn('小铜轮',self.cache.prepare(self.now)[0].texts[0])

    def test_model_switch_rejects_old_workers_without_deleting_new_generation(self):
        old=self.publish()
        with SemanticCache(self.journal,{**IDENTITY,'weight_sha256':'d'*64})as newer:
            job=newer.prepare(self.now)[0];self.assertTrue(newer.publish(job,[[0,1]]*len(job.texts),self.now))
            self.assertFalse(self.cache.publish(old,[[1,0]]*len(old.texts),self.now))
            self.assertEqual(self.cache.rank([1,0],self.now),[]);self.assertEqual(self.cache.prepare(self.now),[])
            self.assertEqual(newer.rank([0,1],self.now)[0]['id'],self.row['id'])

    def test_same_text_in_another_home_cannot_accept_the_job(self):
        old=self.cache.prepare(self.now)[0]
        with Journal(self.root/'other',now=self.now)as other:
            other.capture('fiction-source','讨论铜色齿轮。','重新装正后不再卡住。')
            with SemanticCache(other,IDENTITY)as cache:self.assertFalse(cache.publish(old,[[1,0]]*len(old.texts),self.now))

    def test_source_changes_right_before_cache_commit_are_rejected(self):
        job=self.cache.prepare(self.now)[0];original=self.cache._sources;calls=0
        def interleave(now):
            nonlocal calls
            calls+=1
            if calls==2:self.journal.update(self.row['id'],1,summary='已经改为纸桥实验。')
            return original(now)
        with patch.object(self.cache,'_sources',side_effect=interleave):self.assertFalse(self.cache.publish(job,[[1,0]]*len(job.texts),self.now))
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0],0)

    def test_source_changes_after_cache_commit_are_rechecked_and_removed(self):
        job=self.cache.prepare(self.now)[0];original=self.cache._sources;calls=0
        def interleave(now):
            nonlocal calls
            calls+=1
            if calls==3:self.journal.update(self.row['id'],1,forget=True)
            return original(now)
        with patch.object(self.cache,'_sources',side_effect=interleave):self.assertFalse(self.cache.publish(job,[[1,0]]*len(job.texts),self.now))
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0],0)

    def test_replacing_source_file_fences_existing_cache_handles_and_jobs(self):
        job=self.publish();self.journal.db.close()
        source=self.root/'data/memory/episodes.sqlite3';replacement=source.with_suffix('.replacement')
        with closing(sqlite3.connect(source))as original,closing(sqlite3.connect(replacement))as clone:original.backup(clone)
        os.replace(replacement,source)
        self.assertFalse(self.cache.publish(job,[[1,0]]*len(job.texts),self.now))
        self.assertEqual(self.cache.rank([1,0],self.now),[])
        self.assertEqual(self.cache.prepare(self.now),[])
        with Journal(self.root,now=self.now)as restored,SemanticCache(restored,IDENTITY)as rebuilt:
            self.assertNotEqual(rebuilt.home,self.cache.home)
            self.assertEqual(len(rebuilt.prepare(self.now)),1)
            self.assertFalse(rebuilt.publish(job,[[1,0]]*len(job.texts),self.now))

    def test_newer_cache_schema_is_refused_without_changing_its_version(self):
        self.publish();self.cache.db.execute('PRAGMA user_version=99');self.cache.db.commit()
        before=[tuple(r)for r in self.cache.db.execute('SELECT * FROM vectors')]
        with self.assertRaisesRegex(ValueError,'newer'):SemanticCache(self.journal,IDENTITY)
        self.assertEqual(self.cache.db.execute('PRAGMA user_version').fetchone()[0],99)
        self.assertEqual([tuple(r)for r in self.cache.db.execute('SELECT * FROM vectors')],before)

    def test_incomplete_or_nonfinite_embedding_never_replaces_current_cache(self):
        job=self.publish()
        for invalid in [[],[[0,0]],[[float('nan'),0]],[[True,0]],[[1]],[[1,float('inf')]]]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):self.cache.publish(job,invalid,self.now)
        self.assertEqual(len(self.cache.rank([1,0],self.now)),1)

    def test_partial_sql_failure_rolls_back_to_the_complete_old_cache(self):
        row=self.journal.capture('long','星云观测。'*100,'最后核对星图。')
        job=next(j for j in self.cache.prepare(self.now)if j.ident==row['id']);self.publish(job)
        before=[tuple(r)for r in self.cache.db.execute('SELECT * FROM vectors ORDER BY chunk_no')]
        self.cache.db.execute("CREATE TRIGGER fail_chunk BEFORE INSERT ON vectors WHEN new.chunk_no=1 BEGIN SELECT RAISE(ABORT,'test interruption'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.cache.publish(job,[[0,1]]*len(job.texts),self.now)
        self.assertEqual([tuple(r)for r in self.cache.db.execute('SELECT * FROM vectors ORDER BY chunk_no')],before)

    def test_corrupt_blob_is_not_scored_and_can_be_rebuilt(self):
        self.publish();self.cache.db.execute('UPDATE vectors SET vector=?',(b'broken',));self.cache.db.commit()
        self.assertEqual(self.cache.rank([1,0],self.now),[])
        self.assertEqual(len(self.cache.prepare(self.now)),1)

    def test_active_source_transaction_is_not_mistaken_for_committed_truth(self):
        self.journal.db.execute('BEGIN IMMEDIATE')
        self.journal.db.execute('UPDATE episodes SET summary=? WHERE id=?',('尚未提交的修改。',self.row['id']))
        self.assertNotIn('尚未提交',self.cache.prepare(self.now)[0].texts[0])
        self.journal.db.rollback()

    def test_self_session_and_scope_filters_are_applied_before_ranking(self):
        self.publish();self.assertEqual(self.cache.rank([1,0],self.now,exclude_session='fiction-source'),[])
        self.assertEqual(self.cache.rank([1,0],self.now,allowed_ids=set()),[])

    def test_cache_contains_no_source_text_and_never_mutates_source_rows(self):
        before=self.journal.get(self.row['id']);self.publish();self.cache.rank([1,0],self.now)
        self.assertEqual(self.journal.get(self.row['id']),before)
        columns={r[1]for r in self.cache.db.execute('PRAGMA table_info(vectors)')}
        self.assertEqual(columns,{'model','episode_id','revision','fingerprint','chunk_no','vector'})

    def test_cache_path_cannot_alias_the_primary_database(self):
        directory=self.root/'data/memory';self.cache.db.close();path=directory/'semantic-cache.sqlite3'
        path.unlink();path.symlink_to(directory/'episodes.sqlite3')
        with self.assertRaises(ValueError):SemanticCache(self.journal,IDENTITY)
        self.assertEqual(self.journal.get(self.row['id']),self.row)


if __name__=='__main__':unittest.main()
