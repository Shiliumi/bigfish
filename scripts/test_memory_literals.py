import json
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal,recall_query


class MemoryLiteralTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.store=Journal(Path(temporary.name));self.addCleanup(self.store.db.close)
        self.a=self.store.capture('a','小乔的白色耳机升级到固件2.8。','没有更换耳罩。')
        self.b=self.store.capture('b','我们读过《雪线车站》，主角是狐狸。','谈过结尾那封信。')
        self.c=self.store.capture('c','614工作间装好门禁。','下午四点取物。')
    def ids(self,query):
        result=self.store.recall(query)
        return [r['id']for r in json.loads(result.split('\n',1)[1])]if result else []
    def test_unknown_names_titles_ids_and_versions_are_not_near_matches(self):
        for query in ['阿鸢的白色耳机升级了没？','《雪线车站续篇》的主角是谁？','716工作间门禁','小乔的耳机刷到9.9了？']:
            with self.subTest(query=query):self.assertEqual(self.ids(query),[])
    def test_a_shared_name_alone_does_not_answer_a_different_object(self):
        self.assertEqual(self.ids('小乔那台笔记本电脑的主板换过吗？'),[])
        self.assertEqual(self.ids('小乔'),[self.a['id']])
    def test_literal_ids_titles_and_current_aliases_continue_working(self):
        self.assertEqual(self.ids('614工作间的取物时间'),[self.c['id']])
        self.assertEqual(self.ids('《雪线车站》的结尾那封信'),[self.b['id']])
        self.store.update(self.b['id'],1,aliases=['《狐狸送信》'])
        self.assertEqual(self.ids('《狐狸送信》的结尾'),[self.b['id']])
    def test_contrast_focus_does_not_rewrite_fact_negation(self):
        self.assertEqual(recall_query('不是问《雾色山谷》，我想回想《雪线车站》那封信。'),'我想回想《雪线车站》那封信。')
        self.assertEqual(self.ids('不是问《雾色山谷》，我想回想《雪线车站》那封信。'),[self.b['id']])
        self.assertEqual(recall_query('我没有说喜欢甜粽，只是想试一口。'),'我没有说喜欢甜粽，只是想试一口。')
    def test_multiple_explicit_targets_can_retrieve_separate_records(self):
        other=self.store.capture('d','742工作间门禁修好了。','下午三点取物。')
        self.assertEqual(set(self.ids('614和742工作间的门禁取物时间')),{self.c['id'],other['id']})
    def test_manual_search_remains_available_for_broad_or_partial_terms(self):
        self.assertTrue(self.store.search('《雪线车站续篇》的主角是谁？'))
        self.assertTrue(self.store.search('716工作间门禁'))


if __name__=='__main__':unittest.main()
