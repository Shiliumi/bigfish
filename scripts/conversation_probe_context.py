#!/usr/bin/env python3
"""Build versioned conversation hints over fictional, isolated episodes for paid probes."""
import ast
from datetime import datetime,timedelta,timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import types
from unittest.mock import patch
from fish_journal import Journal,tokens


def instruction(source):
    tree=ast.parse(source)
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='system_prompt_block')
    return ast.literal_eval(next(node.value for node in method.body if isinstance(node,ast.Return)))


def validate_history(history):
    if len(history)%2 or any(role!=('user'if i%2==0 else'assistant')for i,(role,_)in enumerate(history)):
        raise ValueError('Probe history must contain complete alternating fictional turns.')


def prefetch_hints(directory,data,now):
    """Run the selected local provider code with only declared fictional trials/history."""
    hints={}
    for index,(variant,sources)in enumerate(data['prefetch'].items()):
        hints[variant]={}
        for number,scenario in enumerate(data['cases']):
            validate_history(scenario['history'])
            root=directory/f'provider-{index}-case-{number}';plugin=root/'.hermes/plugins/fish-episodes';plugin.mkdir(parents=True)
            marker=root/'scripts/fish_journal.py';marker.parent.mkdir();marker.write_text('# isolated fictional project marker')
            for key,name in [('provider','__init__.py'),('conversation','conversation.py'),('growth','growth.py'),('journal','journal.py'),('matters','matters.py')]:
                (plugin/name).write_text(sources[key])
            # The dependency is only a base protocol; prefetch and helpers are the real
            # versioned project implementation. No Hermes runtime or private home is read.
            base=types.ModuleType('agent.memory_provider');base.MemoryProvider=type('MemoryProvider',(),{})
            with patch.dict('sys.modules',{'agent.memory_provider':base}):
                spec=importlib.util.spec_from_file_location(f'_fixture_prefetch_{index}_{number}',plugin/'__init__.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            provider=module.FishEpisodes();provider.initialize(scenario['id'],hermes_home=str(root/'.hermes'),agent_context='primary')
            for offset,trial in enumerate(data.get('trials',[])):
                with provider.journal(root,now=now)as journal:
                    row=journal.capture(f'fixture-trial-seed-{offset}',trial['seed']['user'],trial['seed']['assistant'],recorded_at=(now-timedelta(minutes=10)).isoformat())
                provider.growth.propose_trial(root,{key:trial[key]for key in ('id','kind','text','reason')}|{'evidence_ids':[row['id']]},now-timedelta(minutes=9))
            history=scenario['history']
            with provider.journal(root,now=now)as journal:
                for i in range(0,len(history),2):
                    journal.capture(scenario['id'],history[i][1],history[i+1][1],recorded_at=(now-timedelta(minutes=len(history)-i)).isoformat())
            provider.on_turn_start(1,scenario['user'])
            hints[variant][scenario['id']]=provider.prefetch(scenario['user'],session_id=scenario['id'])
    return hints


def build(data):
    result={'provider':{key:instruction(value)for key,value in data.get('plugins',{}).items()},'hints':{}}
    with tempfile.TemporaryDirectory(prefix='fish-voice-probe-')as directory:
        root=Path(directory);now=datetime.now(timezone.utc)
        if data.get('prefetch'):
            result['hints']=prefetch_hints(root,data,now);return result
        with Journal(root,now=now)as journal:
            for scenario in data['cases']:
                history=scenario['history']
                validate_history(history)
                for i in range(0,len(history),2):
                    journal.capture(scenario['id'],history[i][1],history[i+1][1],recorded_at=(now-timedelta(minutes=len(history)-i)).isoformat())
            for index,(variant,source)in enumerate(data['conversations'].items()):
                # Only explicitly selected local Git/worktree source is loaded, never model output.
                path=root/('conversation_'+str(index)+'.py');path.write_text(source)
                spec=importlib.util.spec_from_file_location('_fish_probe_voice_'+str(index),path)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                result['hints'][variant]={scenario['id']:module.context(root,scenario['user'],journal=journal,session_id=scenario['id'],tokenize=tokens,now=now)for scenario in data['cases']}
    return result


if __name__=='__main__':
    import sys
    print(json.dumps(build(json.load(sys.stdin)),ensure_ascii=False))
