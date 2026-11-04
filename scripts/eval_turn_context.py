#!/usr/bin/env python3
"""Offline wire-context comparison on existing fictional fixtures; no paid API calls."""
import ast
import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch
from fish_context import TurnContext,HOST_NOTE
from fish_journal import Journal
import eval_memory
# Execute only the pinned upstream's pure text-estimation function, without loading configuration.
tree=ast.parse((Path(__file__).resolve().parents[1]/'.runtime/hermes-agent/agent/model_metadata.py').read_text())
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='estimate_tokens_rough')
namespace={'CHARS_PER_TOKEN':4,'_CJK_DENSE_RE':re.compile('[\u1100-\u11ff\u2e80-\u9fff\ua960-\ua97f\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]')}
exec(compile(ast.Module(body=[function],type_ignores=[]),'<pinned-Hermes-token-estimator>','exec'),namespace)
estimate_text=namespace['estimate_tokens_rough']
def estimate_request(request):return sum(estimate_text(str(m['content']))for m in request['messages'])
ROOT=Path(__file__).resolve().parents[1]
BASELINE='591e208'

def evaluate():
    data=json.loads(eval_memory.FIXTURE.read_text());variants=[];outputs=[];recalls=[]
    with tempfile.TemporaryDirectory(prefix='fish-turn-eval-')as temp:
        for variant in ('before','after'):
            root=Path(temp)/variant;plugin=root/'.hermes/plugins/fish-episodes';plugin.mkdir(parents=True)
            (root/'scripts').mkdir();(root/'scripts/fish_journal.py').write_text('# fixture')
            for source,name in [('plugins/fish-episodes/__init__.py','__init__.py'),('scripts/fish_journal.py','journal.py'),('scripts/personality.py','growth.py'),('scripts/fish_conversation.py','conversation.py'),('scripts/fish_matters.py','matters.py'),('scripts/fish_room.py','room.py')]:
                content=subprocess.check_output(['git','show',BASELINE+':'+source],cwd=ROOT)if variant=='before'else(ROOT/source).read_bytes();(plugin/name).write_bytes(content)
            if variant=='after':shutil.copy2(ROOT/'scripts/fish_context.py',plugin/'context.py')
            key=root/'data/context/transport.key';key.parent.mkdir(parents=True);key.write_text('a'*64)
            stub=types.ModuleType('agent.memory_provider');stub.MemoryProvider=type('MemoryProvider',(),{})
            with patch.dict(sys.modules,{'agent.memory_provider':stub}):
                spec=importlib.util.spec_from_file_location('_fixture_'+variant,plugin/'__init__.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            provider=module.FishEpisodes();provider.initialize('fixture',hermes_home=str(root/'.hermes'),agent_context='primary')
            now,mapping=eval_memory.populate(root,data);provider.journal=lambda r:Journal(r,now=now)
            provider.room._request=lambda *args:{'name':'虚构小屋','representation':{'pose':'sleep','goal':'bed'},'environment':{'weather':'snow','period':'night'},'scope':'可移动清单不是全部家具','fixed_furnishings':[{'name':'书架','area':'左边','details':'三层书架'},{'name':'盆栽','area':'窗边','details':'绿植'}],'movable_items':[{'name':'杯子','at':'书桌','locked':True}]}
            queries=[r['query']for r in data['queries']]+['窗外下雪了吗','你屋里有书架和盆栽吗','你是不是很方啊','帮我排查代码报错']
            results=[]
            for query in queries:
                provider.on_turn_start(1,query);text=provider.prefetch(query);results.append(text)
            outputs.append(results)
            recalled=[]
            for packet in results:
                rows=[]
                for line in packet.splitlines():
                    if line.startswith('[{'):
                        try:value=json.loads(line)
                        except ValueError:continue
                        if all(isinstance(r,dict)and str(r.get('id','')).startswith('ep-')for r in value):rows.extend([{**r,'id':mapping.get(r['id'],r['id'])}for r in value])
                recalled.append(rows)
            recalls.append(recalled)
            wire_chars=wire_estimates=0;rows=[];snapshots=[];transport=TurnContext(root);previous='';fresh_estimate=cached_estimate=0
            for i,query in enumerate(queries[:20]):
                rows.append({'role':'user','content':query+'\n\n<memory-context>\n'+HOST_NOTE+'\n\n'+results[i]+'\n</memory-context>'}if results[i]else{'role':'user','content':query})
                request={'messages':[{'role':'system','content':provider.system_prompt_block()},*rows]}
                sent=transport.project(request,'fixture')if variant=='after'else request
                stream='\n'.join(m['role']+'\n'+str(m['content'])for m in sent['messages']);common=0
                for old_char,new_char in zip(previous,stream):
                    if old_char!=new_char:break
                    common+=1
                cached_estimate+=estimate_text(stream[:common]);fresh_estimate+=estimate_text(stream[common:]);previous=stream
                snapshots.append(sent);wire_chars+=sum(len(str(m['content']))for m in sent['messages']);wire_estimates+=estimate_request(sent)
                rows.append({'role':'assistant','content':'虚构回复：接着说吧。'})
            # Earlier-than-previous-turn history is identical across adjacent optimized requests.
            prefix_ok=all(snapshots[i]['messages'][:max(1,len(snapshots[i-1]['messages'])-1)]==snapshots[i-1]['messages'][:max(1,len(snapshots[i-1]['messages'])-1)]for i in range(1,len(snapshots)))
            variants.append({'variant':variant,'queries':len(queries),'static_chars':len(provider.system_prompt_block()),'prefetch_chars':sum(map(len,results)),'wire_20_turns_chars':wire_chars,'wire_20_turns_rough_tokens':wire_estimates,'older_prefix_stable':prefix_ok,'fresh_text_estimate':fresh_estimate,'reusable_prefix_estimate':cached_estimate,'weighted_text_estimates':{str(w):round(fresh_estimate+w*cached_estimate)for w in (0,0.1,0.25,1)}})
        preserved=recalls[0]==recalls[1]
        recalled_cases=sum(bool(rows)for rows in recalls[0])
        assert recalled_cases>0,'Replay must actually contain recalled source fields'
        return {'baseline':BASELINE,'variants':variants,'recall_fields_preserved':preserved,'queries_with_recall':recalled_cases,'note':'Fictional fixtures; rough local estimate, not DeepSeek tokenization, billing or answer quality. Existing unsigned histories are untouched.'}
if __name__=='__main__':print(json.dumps(evaluate(),ensure_ascii=False,indent=2))
