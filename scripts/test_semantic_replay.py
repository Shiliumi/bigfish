from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from eval_semantic_memory import Encoder,choose,metrics,sample,scope_ids
from fish_journal import Journal


class LocalSemanticReplayTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.now=datetime(2026,10,20,4,tzinfo=timezone.utc)

    def test_ambiguous_nearest_neighbour_is_not_confident_recall(self):
        row={'lexical':[],'dense':[{'key':'one','score':.8},{'key':'two','score':.79}],'margin':.01}
        self.assertEqual(choose(row,.55,.06),[])
        row['margin']=.07;self.assertEqual(choose(row,.55,.06),['one'])
        row['dense'][0]['score']=.4;self.assertEqual(choose(row,.55,.06),[])

    def test_related_missing_attributes_do_not_count_as_false_event_recall(self):
        rows=[{'expected':[],'kind':'missing_detail','retrieved':['glasses']},
              {'expected':[],'retrieved':[]},{'expected':['leak'],'retrieved':['leak']}]
        result=metrics(rows,lambda r:r['retrieved'])
        self.assertEqual(result['negative_cases'],1);self.assertEqual(result['negative_abstention'],1)
        self.assertEqual(result['positive_first'],1);self.assertEqual(result['false_positive_cases'],0)

    def test_model_bytes_are_verified_before_importing_optional_dependencies(self):
        (self.root/'model_optimized.onnx').write_bytes(b'not the public model')
        with self.assertRaisesRegex(ValueError,'pinned public weight'):Encoder(self.root)

    def test_semantic_candidates_share_explicit_chat_date_scope_and_invalid_date_refusal(self):
        with Journal(self.root,now=self.now)as journal:
            old=journal.capture('old','讨论了静音键盘。','晚上打字更安静。',(self.now-timedelta(days=1)).isoformat())
            today=journal.capture('today','昨天买的静音键盘。','今天才聊到它。',self.now.isoformat())
            rows=[old,today]
            self.assertEqual(scope_ids(journal,'昨天聊过的静音键盘',rows),{old['id']})
            self.assertEqual(scope_ids(journal,'昨天买的静音键盘',rows),{old['id'],today['id']})
            self.assertEqual(scope_ids(journal,'2026-99-99聊键盘',rows),set())

    def test_only_current_meaning_is_encoded_from_active_source_snapshot(self):
        class Matrix:
            def __init__(self,count):self.count=count
            def __matmul__(self,query):return [.8]*self.count
        class FakeEncoder:
            def encode(self,texts,query=False):
                if query:return [None]*len(texts)
                self.passages=texts;return Matrix(len(texts))
        with Journal(self.root,now=self.now)as journal:
            corrected=journal.capture('correction','阿蓝住在旧地址广州。','旧地址的描述。')
            journal.update(corrected['id'],1,summary='阿蓝现居杭州。')
            expired=journal.capture('expired','已经过期的临时安排。','已经没有效力。');journal.update(expired['id'],1,invalidate=True)
            erased=journal.capture('deleted','被遗忘的纸风车。','不应重新出现。');journal.update(erased['id'],1,forget=True)
            future=journal.capture('future','未来尚未发生的放映。','不当作已发生。',(self.now+timedelta(days=1)).isoformat())
            encoder=FakeEncoder();mapping={corrected['id']:'correction'}
            cases=[{'query':'阿蓝在杭州的住处','expected':['correction']}]
            result,timing=sample(encoder,journal,cases,mapping)
            self.assertEqual(timing['source_rows'],1);self.assertEqual(encoder.passages,['阿蓝现居杭州。'])
            self.assertEqual(result[0]['dense'][0]['key'],'correction')


if __name__=='__main__':unittest.main()
