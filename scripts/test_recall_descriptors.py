"""Generic descriptors are not event identities; corpus controls still reject unrelated hits."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal
from eval_semantic_recall import corpus_cases,metrics


class DescriptorEvidenceTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=Journal(Path(temp.name),now=datetime(2026,10,31,12,tzinfo=timezone.utc));self.addCleanup(self.store.db.close)
    def test_generic_sound_or_place_does_not_identify_a_different_subject(self):
        self.store.capture('bell','门口挂着一个木铃。','它的声音柔和。')
        self.store.capture('route','旧地图上圈了山谷入口。','我们标出了徒步要经过的地方。')
        for query in ('你还记得电钻的声音吗？','投影仪有声音吗？','药箱收在什么地方？','车站寄存行李的地方呢？'):
            with self.subTest(query=query):self.assertEqual(self.store.recall(query),'')
        self.assertTrue(self.store.search('声音'));self.assertTrue(self.store.search('地方'))
    def test_concrete_cue_and_source_rows_survive_the_descriptor_gate(self):
        self.store.capture('keyboard','键盘换了静音轴。','深夜打字不吵室友。')
        self.store.capture('bell','木铃挂在门口。','声音柔和。')
        english=self.store.capture('english','整理了英语词汇卡片。','不用一晚上全背完。')
        before=[tuple(row)for row in self.store.db.execute('SELECT * FROM episodes ORDER BY id')]
        result=self.store.recall('晚上打字的声音怎么变小');self.assertIn('静音轴',result);self.assertNotIn(english['id'],result)
        self.assertTrue(self.store.search('晚上'))
        self.assertIn('木铃',self.store.recall('木铃声音怎么样'))
        self.assertEqual([tuple(row)for row in self.store.db.execute('SELECT * FROM episodes ORDER BY id')],before)
    def test_explicit_descriptor_alias_is_current_and_invalidated_with_source(self):
        row=self.store.capture('alias','整理了门口的木铃。','留着这件小物的笔记。')
        self.store.update(row['id'],1,aliases=['声音','地方','晚上'])
        self.assertIn('木铃',self.store.recall('声音'));self.assertIn('木铃',self.store.recall('地方'));self.assertIn('木铃',self.store.recall('晚上'))
        self.store.update(row['id'],2,summary='更正：实际讨论的是纸风车。')
        self.assertEqual(self.store.recall('声音'),'');self.assertEqual(self.store.recall('地方'),'');self.assertEqual(self.store.recall('晚上'),'')
        self.store.update(row['id'],3,aliases=['声音']);self.store.update(row['id'],4,forget=True)
        self.assertEqual(self.store.recall('声音'),'')


class MergedCorpusTest(unittest.TestCase):
    def fixture(self):
        return {'a.json':{'episodes':[{'key':'bell'},{'key':'fan'},{'key':'printer'}], 'queries':[{'query':'声音呢？','expected':[]}]}}
    def annotation(self):
        return {'group':'a.json','query':'声音呢？','kind':'ambiguous_subject','expected':[],'related':['bell','fan'],'reason':'合并后有两件会发声的对象，允许核对但不能替用户选定。'}
    def test_controls_only_allow_their_declared_related_sources(self):
        rows=[{'expected':[],'kind':'missing_detail','related':['bell'],'found':['printer']},
              {'expected':[],'kind':'ambiguous_subject','related':['bell','fan'],'found':['bell','fan']},
              {'expected':[],'found':[]},{'expected':['bell'],'found':['bell','printer']}]
        result=metrics(rows,'found');self.assertEqual(result['negative_cases'],1);self.assertEqual(result['false_positives'],0)
        self.assertEqual(result['control_cases'],2);self.assertEqual(result['control_unrelated_contexts'],1)
        self.assertEqual(result['unexpected_contexts'],2);self.assertEqual(result['positive_any'],1)
    def test_annotation_retains_original_queries_and_is_visible_in_the_result(self):
        fixtures=self.fixture();before=json.dumps(fixtures,sort_keys=True);rows=corpus_cases(fixtures,[self.annotation()])['a.json']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['query'],'声音呢？');self.assertEqual(rows[0]['related'],['bell','fan'])
        self.assertIn('corpus_annotation',rows[0]);self.assertEqual(json.dumps(fixtures,sort_keys=True),before)
    def test_unknown_sources_missing_queries_and_duplicate_or_unexplained_annotations_fail(self):
        for change in ({'related':['missing']},{'query':'missing'},{'reason':''},{'kind':'unknown'},{'expected':['bell']}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):corpus_cases(self.fixture(),[{**self.annotation(),**change}])
        with self.assertRaises(ValueError):corpus_cases(self.fixture(),[self.annotation(),self.annotation()])
        fixture=self.fixture();fixture['a.json']['episodes'].append({'key':'bell'})
        with self.assertRaises(ValueError):corpus_cases(fixture,[])
    def test_full_merged_fixture_labels_and_added_queries_are_not_silently_dropped(self):
        root=Path(__file__).resolve().parents[1]/'tests/fixtures';names=['memory_replay.json','semantic_transfer.json','lexical_precision.json','memory_constraints.json','recall_descriptors.json']
        fixtures={name:json.loads((root/name).read_text())for name in names};annotations=json.loads((root/'semantic_corpus_annotations.json').read_text())['annotations']
        cases=corpus_cases(fixtures,annotations);self.assertEqual(sum(map(len,cases.values())),189)
        row=next(row for row in cases['semantic_transfer.json']if row['query']=='蓝牙耳机的固件升级了没？')
        self.assertEqual(row['kind'],'ambiguous_subject');self.assertEqual(set(row['related']),{'ming-headphones','qiao-headphones'})
        self.assertNotIn('printer',row['related'])


if __name__=='__main__':unittest.main()
