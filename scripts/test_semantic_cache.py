from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from fish_journal import Journal
from fish_semantic_cache import SemanticCache,discard_cache

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
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_forgetting_removes_vectors_in_the_source_transaction_without_cache_access(self):
        old=self.publish();matches=self.cache.rank([1,0],self.now)
        self.journal.update(self.row['id'],1,forget=True)
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)
        self.assertFalse(self.cache.publish(old,[[1,0]]*len(old.texts),self.now))
        self.assertEqual(self.cache.rank([1,0],self.now),[]);self.assertEqual(self.cache.resolve(matches,self.now),[])
        self.assertEqual(self.cache.prepare(self.now),[]);self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)
        self.assertEqual(self.journal.get(self.row['id'])['status'],'deleted')

    def test_expiry_exact_boundary_and_future_source_are_not_returned(self):
        self.journal.update(self.row['id'],1,valid_until=(self.now+timedelta(hours=1)).isoformat())
        self.publish()
        future=self.journal.capture('future','未来的纸桥。','还没有发生。',(self.now+timedelta(days=1)).isoformat())
        self.assertEqual(self.cache.prepare(self.now),[])
        self.assertEqual(self.cache.rank([1,0],self.now+timedelta(hours=1)),[])
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

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

    def test_source_changes_before_taking_the_write_lock_are_rejected(self):
        job=self.cache.prepare(self.now)[0];original=self.cache._vector;calls=0
        def interleave(vector):
            nonlocal calls
            calls+=1
            if calls==1:self.journal.update(self.row['id'],1,summary='已经改为纸桥实验。')
            return original(vector)
        with patch.object(self.cache,'_vector',side_effect=interleave):self.assertFalse(self.cache.publish(job,[[1,0]]*len(job.texts),self.now))
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_source_changes_after_cache_commit_are_rechecked_and_removed(self):
        job=self.cache.prepare(self.now)[0];original=self.cache._sources;calls=0
        def interleave(now):
            nonlocal calls
            calls+=1
            if calls==3:self.journal.update(self.row['id'],1,forget=True)
            return original(now)
        with patch.object(self.cache,'_sources',side_effect=interleave):self.assertFalse(self.cache.publish(job,[[1,0]]*len(job.texts),self.now))
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_replacing_source_file_fences_existing_cache_handles_and_jobs(self):
        job=self.publish();self.journal.db.close()
        self.cache.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        source=self.root/'data/memory/episodes.sqlite3';replacement=source.with_suffix('.replacement')
        with closing(sqlite3.connect(source))as original,closing(sqlite3.connect(replacement))as clone:original.backup(clone)
        os.replace(replacement,source)
        self.assertFalse(self.cache.publish(job,[[1,0]]*len(job.texts),self.now))
        self.assertEqual(self.cache.rank([1,0],self.now),[])
        self.assertEqual(self.cache.prepare(self.now),[])
        self.cache.db.close()
        with Journal(self.root,now=self.now)as restored,SemanticCache(restored,IDENTITY)as rebuilt:
            self.assertNotEqual(rebuilt.home,self.cache.home)
            self.assertEqual(len(rebuilt.prepare(self.now)),1)
            self.assertFalse(rebuilt.publish(job,[[1,0]]*len(job.texts),self.now))

    def test_newer_cache_schema_is_refused_without_changing_its_version(self):
        self.publish();self.cache.db.execute("UPDATE fish_semantic_meta SET value='99' WHERE key='schema'");self.cache.db.commit()
        before=[tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors')]
        with self.assertRaisesRegex(ValueError,'newer'):SemanticCache(self.journal,IDENTITY)
        self.assertEqual(self.cache.db.execute("SELECT value FROM fish_semantic_meta WHERE key='schema'").fetchone()[0],'99')
        self.assertEqual(self.cache.db.execute('PRAGMA user_version').fetchone()[0],1)
        self.assertEqual([tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors')],before)

    def test_incomplete_or_nonfinite_embedding_never_replaces_current_cache(self):
        job=self.publish()
        for invalid in [[],[[0,0]],[[float('nan'),0]],[[True,0]],[[1]],[[1,float('inf')]]]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):self.cache.publish(job,invalid,self.now)
        self.assertEqual(len(self.cache.rank([1,0],self.now)),1)

    def test_partial_sql_failure_rolls_back_to_the_complete_old_cache(self):
        row=self.journal.capture('long','星云观测。'*100,'最后核对星图。')
        job=next(j for j in self.cache.prepare(self.now)if j.ident==row['id']);self.publish(job)
        before=[tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors ORDER BY chunk_no')]
        self.cache.db.execute("CREATE TRIGGER fail_chunk BEFORE INSERT ON fish_semantic_vectors WHEN new.chunk_no=1 BEGIN SELECT RAISE(ABORT,'test interruption'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.cache.publish(job,[[0,1]]*len(job.texts),self.now)
        self.assertEqual([tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors ORDER BY chunk_no')],before)

    def test_corrupt_blob_is_not_scored_and_can_be_rebuilt(self):
        self.publish();self.cache.db.execute('UPDATE fish_semantic_vectors SET vector=?',(b'broken',));self.cache.db.commit()
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
        columns={r[1]for r in self.cache.db.execute('PRAGMA table_info(fish_semantic_vectors)')}
        self.assertEqual(columns,{'model','episode_id','revision','fingerprint','chunk_no','vector'})

    def test_legacy_separate_cache_link_is_refused_without_unlinking_it(self):
        directory=self.root/'data/memory';path=directory/'semantic-cache.sqlite3'
        path.symlink_to(directory/'episodes.sqlite3')
        with self.assertRaises(ValueError):SemanticCache(self.journal,IDENTITY)
        self.assertTrue(path.is_symlink())
        self.assertEqual(self.journal.get(self.row['id']),self.row)

    def test_uncommitted_forget_and_its_vector_removal_are_visible_together_after_commit(self):
        self.publish()
        self.journal.db.execute('BEGIN IMMEDIATE')
        self.journal.db.execute("UPDATE episodes SET status='deleted',summary='',excerpt='',revision=revision+1 WHERE id=?",(self.row['id'],))
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)
        # Another connection still sees both the old committed source and its matching vectors.
        self.assertEqual(self.cache.db.execute('SELECT status FROM episodes WHERE id=?',(self.row['id'],)).fetchone()[0],'active')
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],1)
        self.journal.db.commit()
        self.assertEqual(self.cache.db.execute('SELECT status FROM episodes WHERE id=?',(self.row['id'],)).fetchone()[0],'deleted')
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_rollback_restores_source_and_its_vectors_together(self):
        self.publish();before=[tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors')]
        self.journal.db.execute('BEGIN IMMEDIATE')
        self.journal.db.execute('UPDATE episodes SET summary=? WHERE id=?',('这次修改会回滚。',self.row['id']))
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)
        self.journal.db.rollback()
        self.assertEqual(self.journal.get(self.row['id']),self.row)
        self.assertEqual([tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors')],before)

    def test_invalidation_failure_rolls_back_a_normal_journal_forget(self):
        self.publish();self.cache.db.execute("CREATE TRIGGER fail_cleanup BEFORE DELETE ON fish_semantic_vectors BEGIN SELECT RAISE(ABORT,'fixture cleanup failure'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.journal.update(self.row['id'],1,forget=True)
        self.assertEqual(self.journal.get(self.row['id']),self.row)
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],1)

    def test_meaning_and_validity_changes_remove_vectors_but_index_bookkeeping_does_not(self):
        self.publish()
        self.journal.db.execute('UPDATE episodes SET indexed_revision=indexed_revision WHERE id=?',(self.row['id'],));self.journal.db.commit()
        self.assertEqual(self.cache.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],1)
        for change in [{'summary':'实际讨论银色弹簧。'},{'aliases':['小弹簧']},{'invalidate':True}]:
            with self.subTest(change=change):
                pending=self.cache.prepare(self.now)
                if pending:self.publish(pending[0])
                self.journal.update(self.row['id'],self.journal.get(self.row['id'])['revision'],**change)
                self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_missing_invalidation_trigger_is_repaired_and_potentially_stale_vectors_discarded(self):
        self.publish();self.cache.db.execute('DROP TRIGGER fish_semantic_episode_update')
        with SemanticCache(self.journal,IDENTITY)as repaired:
            self.assertTrue(repaired._objects_ready())
            self.assertEqual(repaired.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)
            self.assertEqual(len(repaired.prepare(self.now)),1)

    def test_plain_journal_does_not_create_optional_vector_tables(self):
        with Journal(self.root/'plain',now=self.now)as plain:
            self.assertFalse(plain.db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'fish_semantic_%'").fetchone())

    def test_incomplete_source_schema_cannot_install_a_broken_trigger(self):
        with Journal(self.root/'incomplete',now=self.now)as journal:
            journal.db.execute('ALTER TABLE episodes DROP COLUMN valid_until');journal.db.commit()
            with self.assertRaisesRegex(ValueError,'columns incomplete'):SemanticCache(journal,IDENTITY)
            self.assertFalse(journal.db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'fish_semantic_%'").fetchone())

    def test_other_process_can_delete_source_without_loading_the_cache_module(self):
        self.publish();path=self.root/'data/memory/episodes.sqlite3'
        result=subprocess.run([sys.executable,'-c',"import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('DELETE FROM episodes WHERE id=?',(sys.argv[2],)); db.commit(); db.close()",str(path),self.row['id']],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIsNone(self.journal.get(self.row['id']))
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_panel_cli_forget_removes_vectors_without_importing_optional_cache(self):
        self.publish();scripts=self.root/'scripts';scripts.mkdir()
        script=scripts/'fish_journal.py';shutil.copy2(Path(__file__).with_name('fish_journal.py'),script)
        result=subprocess.run([sys.executable,str(script),'api'],input=json.dumps({'action':'update','id':self.row['id'],'revision':1,'forget':True}),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertEqual(self.journal.get(self.row['id'])['status'],'deleted')
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_primary_schema_change_before_initializer_takes_write_lock_is_refused(self):
        with Journal(self.root/'newer',now=self.now)as journal:
            def change_schema(_):
                journal.db.execute('PRAGMA user_version=99');journal.db.commit();return None
            with patch.object(SemanticCache,'_schema',change_schema):
                with self.assertRaisesRegex(ValueError,'Primary journal schema'):SemanticCache(journal,IDENTITY)
            self.assertEqual(journal.db.execute('PRAGMA user_version').fetchone()[0],99)
            self.assertFalse(journal.db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'fish_semantic_%'").fetchone())

    def test_discard_removes_only_derived_schema_and_preserves_source_history_and_search(self):
        self.publish();self.journal.update(self.row['id'],1,summary='实际讨论银色弹簧。');self.publish()
        before=self.journal.get(self.row['id']);history=self.journal.history(self.row['id']);found=self.journal.search('银色弹簧')
        self.assertTrue(discard_cache(self.journal));self.assertFalse(discard_cache(self.journal))
        self.assertFalse(self.journal.db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'fish_semantic_%'").fetchone())
        self.assertEqual(self.journal.get(self.row['id']),before);self.assertEqual(self.journal.history(self.row['id']),history)
        self.assertEqual(self.journal.search('银色弹簧'),found)
        self.assertEqual(self.cache.prepare(self.now),[]);self.assertEqual(self.cache.rank([1,0],self.now),[])
        with SemanticCache(self.journal,IDENTITY)as rebuilt:self.assertEqual(len(rebuilt.prepare(self.now)),1)

    def test_discard_failure_rolls_back_all_tables_triggers_and_vectors(self):
        self.publish();before=[tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors')]
        self.journal.db.set_authorizer(lambda action,name,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_DROP_TABLE and name=='fish_semantic_meta'else sqlite3.SQLITE_OK)
        try:
            with self.assertRaises(sqlite3.DatabaseError):discard_cache(self.journal)
        finally:self.journal.db.set_authorizer(None)
        self.assertTrue(self.cache._objects_ready())
        self.assertEqual([tuple(r)for r in self.cache.db.execute('SELECT * FROM fish_semantic_vectors')],before)
        self.journal.update(self.row['id'],1,forget=True)
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],0)

    def test_discard_refuses_foreign_schema_and_an_existing_caller_transaction(self):
        self.publish();self.journal.db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(ValueError,'caller transaction'):discard_cache(self.journal)
        self.assertTrue(self.journal.db.in_transaction);self.journal.db.rollback()
        self.journal.db.execute("UPDATE fish_semantic_meta SET value='99' WHERE key='schema'");self.journal.db.commit()
        with self.assertRaisesRegex(ValueError,'newer'):discard_cache(self.journal)
        self.assertEqual(self.journal.db.execute('SELECT COUNT(*) FROM fish_semantic_vectors').fetchone()[0],1)


if __name__=='__main__':unittest.main()
