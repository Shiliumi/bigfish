import unittest
import json
from pathlib import Path
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

    def prefetch_sources(self):
        root=Path(__file__).resolve().parents[1]
        return {key:(root/path).read_text()for key,path in [('provider','plugins/fish-episodes/__init__.py'),('conversation','scripts/fish_conversation.py'),('growth','scripts/personality.py'),('journal','scripts/fish_journal.py'),('matters','scripts/fish_matters.py')]}
    def test_fictional_trials_use_actual_prefetch_and_keep_scenarios_isolated(self):
        source=self.prefetch_sources();fixture=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/conversation_trial_timing.json').read_text())
        cases=[{'id':'play','history':[['user','你今天有种微波炉土豆的气质。'],['assistant','烫嘴是吧。']],'user':'那就叫你薯熟吧。'},
               {'id':'ordinary','history':[],'user':'说说你平常怎么看小工具。'}]
        result=build({'prefetch':{'after':source},'cases':cases,'trials':fixture['trials']})['hints']['after']
        self.assertIn('"mode":"playful"',result['play']);self.assertNotIn(fixture['trials'][0]['text'],result['play'])
        self.assertIn(fixture['trials'][0]['text'],result['ordinary']);self.assertNotIn('"mode":"playful"',result['ordinary'])
        cases[0]['history'].pop()
        with self.assertRaises(ValueError):build({'prefetch':{'after':source},'cases':cases,'trials':fixture['trials']})
    def test_prefetch_uses_each_selected_provider_and_growth_source(self):
        current=self.prefetch_sources();other=dict(current);other['provider']+='\nclass FishEpisodes(FishEpisodes):\n def prefetch(self,query,**kwargs):return "fictional provider marker"\n'
        altered=dict(current);altered['growth']+='\ndef preference_context(*args,**kwargs):return [{"text":"fictional growth marker"}]\n'
        data={'cases':[{'id':'sample','history':[],'user':'普通聊聊。'}],'prefetch':{'before':other,'after':altered},'trials':[]}
        result=build(data)['hints'];self.assertEqual(result['before']['sample'],'fictional provider marker')
        self.assertIn('fictional growth marker',result['after']['sample'])


if __name__=='__main__':unittest.main()
