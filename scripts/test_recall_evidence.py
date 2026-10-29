from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal


class RecallEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.now=datetime(2026,10,20,4,tzinfo=timezone.utc)

    def test_progress_word_alone_does_not_supply_a_different_events_memory(self):
        with Journal(self.root,now=self.now)as store:
            store.capture('gear','讨论了齿轮卡住。','最后重新安装了齿轮。')
            store.capture('router','路由器反复重启。','换了电源后恢复正常。')
            self.assertEqual(store.recall('厨房柜子滴水，最后怎么处理的？'),'')
            self.assertEqual(store.recall('肩膀受伤后恢复得怎么样？'),'')
            self.assertTrue(store.search('最后'));self.assertTrue(store.search('恢复'))

    def test_field_name_without_the_requested_subject_is_not_recalled(self):
        with Journal(self.root,now=self.now)as store:
            store.capture('parcel','快递放到了东门。','没有保存取件密码。')
            self.assertEqual(store.recall('那个游戏账号的密码是什么？'),'')
            self.assertIn('东门',store.recall('东门快递的取件密码记了吗？'))

    def test_short_content_cue_survives_even_in_a_long_paraphrase(self):
        with Journal(self.root,now=self.now)as store:
            store.capture('keyboard','键盘换了静音轴。','深夜打字不吵室友。')
            self.assertIn('静音轴',store.recall('晚上打字的声音怎么变小'))

    def test_explicit_alias_overrides_weak_word_gate_until_source_expires(self):
        with Journal(self.root,now=self.now)as store:
            row=store.capture('alias','整理了星云观测笔记。','先留着这份资料。')
            store.update(row['id'],1,aliases=['最后','done'])
            self.assertIn('星云',store.recall('最后'));self.assertIn('星云',store.recall('done'))
            self.assertEqual(store.recall('undone'),'')
            store.update(row['id'],2,invalidate=True)
            self.assertEqual(store.recall('最后'),'');self.assertEqual(store.recall('done'),'')

    def test_correction_and_forgetting_do_not_preserve_old_alias_exceptions(self):
        with Journal(self.root,now=self.now)as store:
            row=store.capture('alias','整理了星云观测笔记。','这是旧记法。');store.update(row['id'],1,aliases=['最后'])
            store.update(row['id'],2,summary='实际讨论的是陨石标本。')
            self.assertEqual(store.recall('最后'),'');self.assertIn('陨石',store.recall('陨石标本'))
            store.update(row['id'],3,aliases=['最后']);store.update(row['id'],4,forget=True)
            self.assertEqual(store.recall('最后'),'')


if __name__=='__main__':unittest.main()
