from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fish_journal import Journal
from fish_embeddings import MODEL_IDENTITY
from fish_semantic_cache import SemanticCache
import fish_semantic_recall as support

VECTOR=[1.]+[0.]*511


class SemanticRecallTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.now=datetime(2026,10,29,4,tzinfo=timezone.utc)
        self.journal=Journal(self.root,now=self.now);self.addCleanup(self.journal.db.close)
        self.helper=support.SemanticRecall(self.root)
        self.home=self.root/'.runtime/semantic';self.home.mkdir(parents=True);(self.home/'active.json').write_text('{}')
        self.row=self.journal.capture('old','小许把深蓝色雨伞落在公交车后排。','司机把它送到了总站的失物招领处。')
    def fill(self):
        with SemanticCache(self.journal,MODEL_IDENTITY)as cache:
            for job in cache.prepare(self.now):self.assertTrue(cache.publish(job,[VECTOR]*len(job.texts),self.now))
    def call(self,query='之前聊过的那个挡雨家伙，最后到哪去了？',**kwargs):
        with patch.object(support,'encode',return_value=[VECTOR]):return self.helper.recall(self.journal,query,**kwargs)
    def test_lexical_results_are_preserved_byte_for_byte_without_starting_an_encoder(self):
        expected=self.journal.recall('深蓝色雨伞')
        with patch.object(support,'encode')as encode:
            self.assertEqual(self.helper.recall(self.journal,'深蓝色雨伞'),expected);encode.assert_not_called()
    def test_missing_runtime_or_index_keeps_the_old_empty_result(self):
        with patch.object(support,'encode')as encode:
            self.assertEqual(self.helper.recall(self.journal,'会展开的挡雨家伙'), '');encode.assert_not_called()
        (self.home/'active.json').unlink();self.assertEqual(self.call(),'')
        self.assertFalse(self.journal.db.execute("SELECT 1 FROM sqlite_master WHERE name='fish_semantic_vectors'").fetchone())
    def test_semantic_result_is_one_whole_attributed_current_source_with_revision(self):
        self.fill();result=self.call();self.assertIn('不可信',result)
        rows=json.loads(result.split('\n',1)[1]);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],self.row['id']);self.assertEqual(rows[0]['revision'],1)
        self.assertEqual(rows[0]['excerpt'],self.row['excerpt']);self.assertEqual(rows[0]['match_kind'],'semantic')
        self.assertLessEqual(len(result),4200)
    def test_automatic_path_only_uses_explicit_memory_intent(self):
        self.fill()
        with patch.object(support,'encode',return_value=[VECTOR])as encode:
            self.assertEqual(self.helper.recall(self.journal,'今天阴天呢。',automatic=True),'');encode.assert_not_called()
            self.assertTrue(self.helper.recall(self.journal,'还记得那个能遮住雨点的家伙吗？',automatic=True))
    def test_unknown_literal_targets_cannot_be_replaced_with_nearby_objects(self):
        self.fill()
        for query in ['716工作间的空调','《雪线车站续篇》的结局','阿鸢的耳机','2.8固件的升级记录']:
            with self.subTest(query=query),patch.object(support,'encode')as encode:
                self.assertEqual(self.helper.recall(self.journal,query),'');encode.assert_not_called()
    def test_profile_and_secret_questions_do_not_trigger_dense_inference(self):
        self.fill()
        for query in ['我最喜欢的咸粽是哪一款？','我更喜欢什么？','我的生日是什么时候？','那台电脑的密码']:
            with patch.object(support,'encode')as encode:
                self.assertEqual(self.helper.recall(self.journal,query),'');encode.assert_not_called()
    def test_transaction_status_cannot_be_inferred_from_a_similar_paper_episode(self):
        self.fill()
        with patch.object(support,'encode')as encode:
            self.assertEqual(self.helper.recall(self.journal,'恢复之后打印纸的采购合同续了没？'),'');encode.assert_not_called()
    def test_incomplete_corpus_does_not_turn_a_single_candidate_into_confidence(self):
        self.fill();self.journal.capture('unindexed','折叠凳的连接结构。','新的共同经历。')
        with patch.object(support,'encode')as encode:
            self.assertEqual(self.helper.recall(self.journal,'还记得那个能挡雨的家伙吗？'),'');encode.assert_not_called()
    def test_encoder_unavailability_returns_the_existing_result(self):
        self.fill()
        with patch.object(support,'encode',return_value=None):self.assertEqual(self.helper.recall(self.journal,'那个能挡雨的家伙'), '')
    def test_forgetting_during_query_encoding_cannot_restore_the_source(self):
        self.fill()
        def changed(*args,**kwargs):self.journal.update(self.row['id'],1,forget=True);return [VECTOR]
        with patch.object(support,'encode',side_effect=changed):self.assertEqual(self.helper.recall(self.journal,'那个挡雨的家伙'),'')
        self.assertEqual(self.journal.get(self.row['id'])['status'],'deleted')
    def test_source_expiring_while_encoder_runs_is_not_returned(self):
        self.journal.update(self.row['id'],1,valid_until=(self.now+timedelta(seconds=.5)).isoformat());self.fill()
        current=[100.]
        def encoded(*args,**kwargs):current[0]+=1;return [VECTOR]
        with patch.object(support.time,'monotonic',side_effect=lambda:current[0]),patch.object(support,'encode',side_effect=encoded):
            self.assertEqual(self.helper.recall(self.journal,'那个挡雨的家伙'),'')
    def test_corrupt_competitor_cannot_make_a_remaining_source_look_unambiguous(self):
        other=self.journal.capture('other','折叠凳用了四根木条。','讨论过榫卯连接。');self.fill()
        import struct
        self.journal.db.execute('UPDATE fish_semantic_vectors SET vector=? WHERE episode_id=?',(struct.pack('<512f',float('nan'),*([0.]*511)),other['id']));self.journal.db.commit()
        self.assertEqual(self.call(),'')
    def test_current_credential_values_are_redacted_before_tool_delivery(self):
        secret='fiction-opaque-current-key';directory=self.root/'.hermes';directory.mkdir();(directory/'.env').write_text('API_KEY='+secret)
        self.journal.db.execute('UPDATE episodes SET excerpt=? WHERE id=?',('你：不应发送的旧凭据 '+secret+'\n大肥鱼：只用于隔离测试。',self.row['id']));self.journal.db.commit();self.fill()
        result=self.call('还记得那个雨天的东西吗？');self.assertTrue(result);self.assertNotIn(secret,result)
    def test_too_long_whole_source_is_not_clipped_into_a_false_statement(self):
        self.journal.update(self.row['id'],1,forget=True)
        self.journal.capture('long','甲乙丙丁'*1000,'我没有同意这件事。');self.fill()
        self.assertEqual(self.call('之前那件涉及雨水的事'),'')
    def test_indexer_retries_durable_pending_sources_and_never_changes_them(self):
        before=self.journal.get(self.row['id'])
        with patch.object(support,'encode',return_value=None):self.assertEqual(self.helper.index_pending(self.journal),0)
        with patch.object(support,'encode',side_effect=lambda home,texts,**kwargs:[VECTOR]*len(texts)):
            self.assertEqual(self.helper.index_pending(self.journal),1);self.assertEqual(self.helper.index_pending(self.journal),0)
        self.assertEqual(self.journal.get(self.row['id']),before)
    def test_scope_keeps_discussion_date_and_self_session_boundaries(self):
        self.fill();self.assertEqual(self.call(exclude_session='old'),'')
        self.assertEqual(self.call('昨天聊的那个挡雨家伙'),'')
        self.assertEqual(self.call('2026-99-99聊过的东西'),'')


if __name__=='__main__':unittest.main()
