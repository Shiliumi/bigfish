from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from fish_journal import Journal,INDEX_VERSION
from eval_memory import evaluate


class RetrievalTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=datetime(2026,10,20,4,tzinfo=timezone.utc)
    def test_replay_recall_precision_conflicts_and_context_are_measured_together(self):
        result=evaluate()
        self.assertGreaterEqual(result['cases'],60);self.assertGreaterEqual(result['top5_recall'],.95)
        self.assertGreaterEqual(result['top1_accuracy'],.95);self.assertGreaterEqual(result['context_recall'],.95)
        self.assertEqual(result['negative_abstention'],1);self.assertEqual(result['unsafe_contexts'],0)
        self.assertEqual(result['missing_snippets'],0);self.assertLessEqual(result['max_context_chars'],4200)
    def test_numbers_and_full_width_spellings_are_retrievable(self):
        with Journal(self.root,now=self.now) as store:
            room=store.capture('room','我们约在 808 房间等维修师傅。','房间号是808，不保存门锁密码。')
            code=store.capture('code','小舟用 Python 整理照片。','按日期分好文件夹。')
            self.assertEqual(store.search('808')[0]['id'],room['id'])
            self.assertEqual(store.search('ＰＹＴＨＯＮ')[0]['id'],code['id'])
    def test_pinning_never_outranks_a_strong_topic_with_an_unrelated_shared_word(self):
        with Journal(self.root,now=self.now) as store:
            real=store.capture('topic','Python脚本整理照片。','我们按日期分类了。')
            noise=store.capture('noise','上次聊的照片挺多。','还没选好想看哪个作品。');store.update(noise['id'],1,pinned=True)
            self.assertEqual(store.search('Python整理照片')[0]['id'],real['id'])
    def test_dates_filter_the_record_clock_in_beijing_even_for_legacy_offsets(self):
        with Journal(self.root,now=self.now) as store:
            old=store.capture('old','路由器天线摆正了。','这次没换电源。','2026-10-01T12:00:00+08:00')
            recent=store.capture('recent','给路由器换电源。','不再反复重启。','2026-10-19T23:30:00+08:00')
            store.db.execute('UPDATE episodes SET recorded_at=? WHERE id=?',('2026-10-19T23:30:00+08:00',recent['id']));store.db.commit()
            self.assertEqual([r['id']for r in store.search('昨天路由器')],[recent['id']])
            self.assertEqual(store.search('2026-10-01 路由器')[0]['id'],old['id'])
            self.assertEqual(store.search('10月19日')[0]['id'],recent['id'])
            self.assertEqual(store.search('2026-99-99路由器'),[])
            self.assertEqual(store.recall('2026-99-99聊过的路由器'),'')
    def test_aliases_are_explicit_revision_safe_and_not_model_instructions(self):
        with Journal(self.root,now=self.now) as store:
            item=store.capture('maker','看了木间实验室的榫卯凳子。','那个折叠结构很巧妙。')
            store.update(item['id'],1,aliases=['木头哥','MuJianLab','ＭｕＪｉａｎＬａｂ'])
            self.assertEqual(store.describe(store.get(item['id']))['aliases'],['木头哥','MuJianLab'])
            self.assertEqual(store.search('MuJianLab')[0]['match_kind'],'alias')
            self.assertIn('榫卯',store.recall('木头哥'));self.assertNotIn('木头哥',store.recall('木头哥'))
            with self.assertRaises(ValueError):store.update(item['id'],1,aliases=['stale-alias'])
            for invalid in ['bad',['x'],['https://example.org'],['a\nb'],['a'*41],['aa']*9,['🐟🐟']]:
                with self.assertRaises(ValueError):store.update(item['id'],2,aliases=invalid)
            store.update(item['id'],2,summary='那次实际看的是另一位作者的折叠凳。')
            self.assertEqual(store.describe(store.get(item['id']))['aliases'],[]);self.assertEqual(store.search('MuJianLab'),[])
    def test_expiry_and_forgetting_apply_to_aliases_and_rebuilds(self):
        with Journal(self.root,now=self.now) as store:
            item=store.capture('forget','一起看折叠木凳。','这个结构真巧。');store.update(item['id'],1,aliases=['木头哥'])
            store.update(item['id'],2,forget=True)
            store.db.execute('UPDATE episodes SET index_version=0');store.db.commit()
        with Journal(self.root,now=self.now) as store:
            self.assertEqual(store.search('木头哥',scope='history'),[]);self.assertEqual(store.get(item['id'])['aliases'],'[]')
    def test_stale_derived_index_rebuilds_from_current_meaning_not_raw_old_text(self):
        with Journal(self.root,now=self.now) as store:
            item=store.capture('edit','阿蓝住在广州。','之前聊了通勤。')
            # Simulate an older writer that advanced the record but left an old derived index.
            store.db.execute('UPDATE episodes SET summary=?,revision=revision+1 WHERE id=?',('阿蓝现在在杭州工作。',item['id']));store.db.commit()
        with Journal(self.root,now=self.now+timedelta(hours=1)) as store:
            self.assertIn('杭州',store.recall('阿蓝'));self.assertNotIn('广州',store.recall('阿蓝'))
            row=store.get(item['id']);self.assertEqual(row['index_version'],INDEX_VERSION);self.assertEqual(row['indexed_revision'],row['revision'])
    def test_long_source_windows_keep_speaker_attribution_and_json_budget(self):
        with Journal(self.root,now=self.now) as store:
            store.capture('late','开头都是背景。'*400+'后来小禾提到了铜色齿轮。','修复办法是重新安装偏心的铜色齿轮。')
            context=store.recall('铜色齿轮');payload=json.loads(context.split('\n',1)[1])
            self.assertIn('你：',payload[0]['excerpt']);self.assertIn('大肥鱼：',payload[0]['excerpt']);self.assertIn('小禾',payload[0]['excerpt'])
            self.assertLessEqual(len(context),4200)
    def test_vague_social_or_preference_questions_do_not_inject_random_episodes(self):
        with Journal(self.root,now=self.now) as store:
            store.capture('random','我喜欢看电影。','记得先取快递。')
            for query in ['','  ','你还记得我吗','帮我回忆一下','我喜欢什么','早安呀','未知的量子霍尔效应']:
                self.assertEqual(store.recall(query),'',query)
    def test_long_query_keeps_specific_anchors_after_background_clauses(self):
        with Journal(self.root,now=self.now) as store:
            item=store.capture('actual','一起修铜色齿轮。','重新安装后就能转了。')
            query='；'.join('背景'+''.join(chr(0x4e00+i*4+n)for n in range(4))for i in range(40))+'；铜色齿轮'
            self.assertEqual(store.search(query)[0]['id'],item['id'])
    def test_an_events_date_is_not_misread_as_the_chat_record_date(self):
        with Journal(self.root,now=self.now) as store:
            store.capture('today','昨天买了静音键盘。','今天聊到它晚上打字更安静。')
            self.assertIn('静音键盘',store.recall('昨天买的静音键盘'))
            self.assertEqual(store.recall('昨天聊过的静音键盘'),'')


if __name__=='__main__':unittest.main()
