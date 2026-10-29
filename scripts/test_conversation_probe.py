import unittest
from conversation_probe_context import build,instruction


class ConversationProbeTest(unittest.TestCase):
    def test_guarded_provider_still_exposes_its_literal_primary_instruction(self):
        source="class Provider:\n def system_prompt_block(self):\n  if self.primary is False:return ''\n  return 'primary instruction'\n"
        self.assertEqual(instruction(source),'primary instruction')
    def test_before_and_after_use_their_own_context_implementation(self):
        old="def context(root,query,**kwargs):return 'old hints for '+query\n"
        new="def context(root,query,**kwargs):return 'new hints for '+query\n"
        result=build({'conversations':{'before':old,'after':new},'cases':[{'id':'fiction','history':[],'user':'fixture question'}]})
        self.assertEqual(result['hints']['before']['fiction'],'old hints for fixture question')
        self.assertEqual(result['hints']['after']['fiction'],'new hints for fixture question')

    def test_real_history_isolated_by_scenario_and_shared_without_fabricated_turns(self):
        source="def context(root,query,*,journal,session_id,**kwargs):\n return [row[0]for row in journal.db.execute('SELECT excerpt FROM episodes WHERE session_id=?',(session_id,))]\n"
        cases=[{'id':'one','history':[['user','虚构问题甲'],['assistant','虚构回复甲']],'user':'继续'},
               {'id':'two','history':[['user','虚构问题乙'],['assistant','虚构回复乙']],'user':'继续'}]
        result=build({'conversations':{'before':source,'after':source},'cases':cases})
        self.assertEqual(result['hints']['before'],result['hints']['after'])
        self.assertIn('虚构回复甲',result['hints']['after']['one'][0]);self.assertNotIn('虚构回复乙',str(result['hints']['after']['one']))
        cases[0]['history'].pop()
        with self.assertRaises(ValueError):build({'conversations':{'after':source},'cases':cases})


if __name__=='__main__':unittest.main()
