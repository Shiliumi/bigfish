from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import tempfile
import unittest
from fish_journal import Journal
from fish_memory_graph import graph, MAX_NODES

NOW = datetime(2026, 11, 3, 4, tzinfo=timezone.utc)


class MemoryGraphTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root, now=NOW)
        self.addCleanup(self.journal.db.close)

    def capture(self, session, text, when=None):
        return self.journal.capture(session, text, '这是虚构验收回复。', when or NOW-timedelta(days=1))

    def test_only_explainable_connections_and_minimal_projection(self):
        first = self.capture('private-chat-a', '一起折纸机关')
        second = self.capture('private-chat-a', '试试纸片弹簧')
        third = self.capture('private-chat-b', '后来聊起鲸鱼')
        self.journal.update(first['id'], 1, aliases=['纸机关'])
        self.journal.update(third['id'], 1, aliases=['纸机关'])
        value = graph(self.journal, {})
        self.assertEqual(len(value['nodes']), 3)
        reasons = [r['kind'] for edge in value['edges'] for r in edge['reasons']]
        self.assertEqual(sorted(reasons), ['alias', 'conversation'])
        for node in value['nodes']:
            self.assertNotIn('excerpt', node)
            self.assertNotIn('session_id', node)
            self.assertNotIn('source_ref', node)
            self.assertNotIn('history', node)
        self.assertNotIn('private-chat', json.dumps(value))
        self.assertTrue(all(node['group'].startswith('cg-') for node in value['nodes']))

    def test_correction_rebuilds_connections_from_current_meaning(self):
        first = self.capture('one', '旧记法：喜欢纸机关')
        second = self.capture('two', '后来又聊到纸机关')
        for row in (first, second):
            self.journal.update(row['id'], 1, aliases=['纸机关'])
        before = graph(self.journal, {})
        self.assertEqual(len(before['edges']), 1)
        self.journal.update(first['id'], 2, summary='更正：只是看过，并没有说喜欢。')
        after = graph(self.journal, {})
        self.assertNotEqual(before['revision'], after['revision'])
        self.assertEqual(after['edges'], [])
        self.assertNotIn('旧记法', json.dumps(after, ensure_ascii=False))
        self.assertEqual(len(graph(self.journal, {'q':'纸机关'})['nodes']), 1)
        self.assertEqual(len(graph(self.journal, {'q':'更正：只是看过'})['nodes']), 1)

    def test_forgetting_removes_nodes_and_edges_without_resurrection(self):
        first = self.capture('one', '可遗忘的纸机关')
        self.capture('one', '同一次聊天里的后续')
        self.journal.update(first['id'], 1, forget=True)
        self.capture('one', '可遗忘的纸机关')
        for scope in ('current', 'history'):
            value = graph(self.journal, {'scope':scope})
            self.assertEqual(len(value['nodes']), 1)
            self.assertEqual(value['edges'], [])
            self.assertNotIn(first['id'], json.dumps(value))

    def test_validity_and_pins_never_make_expired_facts_current(self):
        row = self.capture('one', '当时有点困')
        self.journal.update(row['id'], 1, kind='impression', pinned=True, invalidate=True)
        self.assertEqual(graph(self.journal, {})['nodes'], [])
        historical = graph(self.journal, {'scope':'history'})
        self.assertEqual(historical['nodes'][0]['effective_status'], 'expired')
        self.assertTrue(historical['nodes'][0]['pinned'])
        self.assertEqual(historical['stats']['historical'], 1)
        self.assertEqual(graph(self.journal, {'kind':'event','scope':'history'})['nodes'], [])

    def test_beijing_date_boundaries_and_literal_normalized_search(self):
        before = self.capture('one', '日期边界之前', datetime(2026, 11, 1, 15, 59, tzinfo=timezone.utc))
        row = self.capture('two', 'ＮＡＳＡ发射与纸机关', datetime(2026, 11, 1, 16, tzinfo=timezone.utc))
        self.capture('three', '日期边界之后', datetime(2026, 11, 2, 16, tzinfo=timezone.utc))
        value = graph(self.journal, {'from':'2026-11-02','to':'2026-11-02'})
        self.assertEqual([n['id'] for n in value['nodes']], [row['id']])
        self.assertNotIn(before['id'], json.dumps(value))
        self.assertEqual(len(graph(self.journal, {'q':'nasa'})['nodes']), 1)
        self.assertEqual(graph(self.journal, {'q':'%_ OR 1=1'})['nodes'], [])
        self.assertEqual(value['range'], {'from':'2026-11-01','to':'2026-11-03'})

    def test_bounded_graph_exposes_omissions_and_old_records_are_reachable(self):
        for number in range(MAX_NODES+2):
            self.capture('many', f'虚构记录编号 {number}', NOW-timedelta(days=number))
        value = graph(self.journal, {})
        self.assertEqual(value['stats']['shown'], MAX_NODES)
        self.assertEqual(value['stats']['matched'], MAX_NODES+2)
        self.assertEqual(value['stats']['omitted'], 2)
        older = graph(self.journal, {'to':(NOW-timedelta(days=MAX_NODES)).date().isoformat()})
        self.assertGreater(len(older['nodes']), 0)
        self.assertLess(len(older['nodes']), MAX_NODES)

    def test_projection_is_repeatable_read_only_and_redacts_current_credentials(self):
        (self.root/'.hermes').mkdir(exist_ok=True)
        secret='a-configured-private-credential-for-graph'
        (self.root/'.hermes/.env').write_text('MODEL_API_KEY='+secret)
        self.capture('one', '鱼粮和 '+secret)
        before=self.journal.db.total_changes
        one,two=graph(self.journal, {}),graph(self.journal, {})
        self.assertEqual(one,two)
        self.assertEqual(before,self.journal.db.total_changes)
        self.assertNotIn(secret,json.dumps(one))

    def test_invalid_filters_are_rejected(self):
        for data in ({'scope':'deleted'},{'kind':'emotion'},{'q':'x'*101},{'q':4},{'pinned':1},
                     {'from':'2026-02-30'},{'from':'2026-1-01'},{'from':'2026-11-03','to':'2026-11-01'}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                graph(self.journal,data)

    def test_expiry_changes_projection_even_without_database_writes(self):
        row=self.capture('one','临时印象')
        self.journal.update(row['id'],1,kind='impression',valid_until=(NOW+timedelta(hours=1)).isoformat())
        before=graph(self.journal,{})
        self.journal.now=NOW+timedelta(hours=2)
        after=graph(self.journal,{})
        self.assertEqual(after['nodes'],[])
        self.assertNotEqual(before['revision'],after['revision'])


if __name__=='__main__':
    unittest.main()
