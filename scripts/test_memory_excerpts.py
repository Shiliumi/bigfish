"""Source-window regressions over fictional text; no model or private memory."""
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal,source_window,sentence_spans,tokens


class MemoryExcerptTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.store=Journal(Path(temporary.name),now=datetime(2026,10,29,4,tzinfo=timezone.utc))
        self.addCleanup(self.store.db.close)

    def payload(self,query):
        context=self.store.recall(query)
        self.assertLessEqual(len(context),4200)
        return json.loads(context.split('\n',1)[1])if context else []

    def test_a_quoted_preference_keeps_its_speaker_and_disclaimer(self):
        user='背景说明。'*60+'下面只是小说角色的台词，不是我的真实偏好：「'+'备选条目、'*45+'我最喜欢红茶。」'
        row=self.store.capture('fiction',user,'收到。');before=self.store.get(row['id'])
        item=self.payload('我最喜欢红茶')[0]
        self.assertIn('不是我的真实偏好',item['excerpt']);self.assertIn('我最喜欢红茶。',item['excerpt'])
        self.assertIn('你：',item['excerpt']);self.assertIn('大肥鱼：收到。',item['excerpt'])
        self.assertTrue(item['excerpted']);self.assertNotIn('summary',item)
        self.assertEqual(self.store.get(row['id']),before)

    def test_a_following_correction_is_not_cut_off_after_the_attractive_fact(self):
        source='背景说明。'*60+'铜色齿轮已经修好了。刚才说错了，其实还在等替换件。'
        self.store.capture('repair',source,'先保留实际进度。')
        excerpt=self.payload('铜色齿轮修好了吗')[0]['excerpt']
        self.assertIn('铜色齿轮已经修好了。刚才说错了，其实还在等替换件。',excerpt)

    def test_conditions_in_a_single_long_sentence_stay_with_the_claim(self):
        source='背景说明。'*60+'只有月底之前把'+'待处理材料、'*30+'补齐，灰色耳机才可能获批；目前没有通过。'
        self.store.capture('conditional',source,'仍以实际审批为准。')
        excerpt=self.payload('灰色耳机获批了吗')[0]['excerpt']
        self.assertIn('只有月底之前',excerpt);self.assertIn('目前没有通过。',excerpt)

    def test_quotes_parentheses_and_fenced_code_are_not_split_on_internal_punctuation(self):
        for source in ['他说「有。还有『更多！』」但我不同意。之后再聊。',
                       '示例（第一句。第二句！）仍然只是举例。之后再聊。',
                       '例子：```python\nprint("已批准。")\n```并未实际运行。之后再聊。',
                       'He said "approved. really!" but I disagree. Next sentence.',
                       'He said "a \\"tiny. !\\" example" but not confirmed. Next sentence.',
                       "John's note says 'done. maybe!' but not confirmed. Next sentence."]:
            with self.subTest(source=source):
                spans=sentence_spans(source)
                self.assertEqual(len(spans),2)
                self.assertEqual(''.join(source[a:b]for a,b in spans),source)

    def test_an_oversized_relevant_unit_is_not_clipped_or_rescued_by_a_prefix_summary(self):
        source='背景说明。'*60+'这段是假设：「'+'备选条目、'*900+'我最喜欢乌龙茶。」'
        row=self.store.capture('too-long','你猜我喜欢什么茶？',source)
        self.assertEqual(self.store.recall('我最喜欢乌龙茶'),'')
        self.assertTrue(self.store.search('我最喜欢乌龙茶'))
        self.assertEqual(self.store.get(row['id'])['excerpt'],'你：你猜我喜欢什么茶？\n大肥鱼：'+source)

    def test_a_whole_statement_can_expand_beyond_the_preferred_small_window(self):
        source='背景说明。'*60+'这只是小说角色的偏好：「'+'备选条目、'*170+'我最喜欢普洱茶。」不代表我的选择。'
        self.store.capture('long-but-fits',source,'知道了。')
        item=self.payload('我最喜欢普洱茶')[0]
        self.assertIn('这只是小说角色的偏好',item['excerpt']);self.assertIn('不代表我的选择。',item['excerpt'])

    def test_a_whole_record_over_budget_does_not_evict_a_smaller_useful_source(self):
        huge=self.store.capture('huge','这段只是举例：「'+'条目、'*900+'青色风扇已启动。」','尚未实测：「'+'条目、'*900+'青色风扇已启动。」')
        small=self.store.capture('small','青色风扇还没有启动。','以这次实测为准。')
        self.store.update(huge['id'],1,pinned=True)
        self.assertEqual(self.store.search('青色风扇已启动',strict_evidence=True)[0]['id'],huge['id'])
        items=self.payload('青色风扇已启动')
        self.assertIn(small['id'],[row['id']for row in items]);self.assertNotIn(huge['id'],[row['id']for row in items])
        self.assertIn('还没有启动',str(items))

    def test_short_sources_remain_whole_without_redundant_auto_summaries(self):
        row=self.store.capture('short','小禾把蓝色耳机放在门边。','先放好，不是弄丢了。')
        item=self.payload('蓝色耳机')[0]
        self.assertEqual(item['excerpt'],row['excerpt']);self.assertNotIn('excerpted',item);self.assertNotIn('summary',item)

    def test_long_auto_summary_is_removed_by_comparing_the_original_source(self):
        self.store.capture('late','无关背景。'*80+'铜色齿轮偏心了。','重新安装后恢复转动。')
        item=self.payload('铜色齿轮')[0];self.assertTrue(item['excerpted']);self.assertNotIn('summary',item)
        self.assertNotIn('无关背景。'*20,item['excerpt'])

    def test_current_correction_replaces_raw_source_even_if_old_source_was_quoted(self):
        row=self.store.capture('old','他说「最喜欢青茶。」这不是我的偏好。','知道了。')
        self.store.update(row['id'],1,summary='用户更正：刚才只是小说对话，不代表本人的茶饮偏好。')
        item=self.payload('茶饮偏好')[0]
        self.assertEqual(item['excerpt'],'用户更正：刚才只是小说对话，不代表本人的茶饮偏好。')
        self.assertNotIn('青茶',item['excerpt']);self.assertNotIn('summary',item)
        self.assertEqual(item['revision'],2)

    def test_original_capture_limit_is_visible_separately_from_display_excerpting(self):
        self.store.capture('capture-limit','铜色齿轮卡住了。'+'背景说明。'*900,'先检查装配。')
        item=self.payload('铜色齿轮')[0];self.assertTrue(item['source_truncated']);self.assertTrue(item['excerpted'])

    def test_omission_marks_do_not_change_the_selected_verbatim_source(self):
        source='之前的背景。'*60+'后来小禾换了铜色齿轮。之后还没试机。'+'后续背景。'*60
        fragment=source_window(source,set(tokens('铜色齿轮')))
        self.assertTrue(fragment.startswith('…'));self.assertTrue(fragment.endswith('…'))
        self.assertIn(fragment[1:-1],source)
        self.assertIn('后来小禾换了铜色齿轮。之后还没试机。',fragment)


if __name__=='__main__':unittest.main()
