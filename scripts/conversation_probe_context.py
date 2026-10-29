#!/usr/bin/env python3
"""Build versioned conversation hints over fictional, isolated episodes for paid probes."""
import ast
from datetime import datetime,timedelta,timezone
import importlib.util
import json
from pathlib import Path
import tempfile
from fish_journal import Journal,tokens


def instruction(source):
    tree=ast.parse(source)
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='system_prompt_block')
    return ast.literal_eval(method.body[0].value)


def build(data):
    result={'provider':{key:instruction(value)for key,value in data.get('plugins',{}).items()},'hints':{}}
    with tempfile.TemporaryDirectory(prefix='fish-voice-probe-')as directory:
        root=Path(directory);now=datetime.now(timezone.utc)
        with Journal(root,now=now)as journal:
            for scenario in data['cases']:
                history=scenario['history']
                if len(history)%2 or any(role!=('user'if i%2==0 else'assistant')for i,(role,_)in enumerate(history)):
                    raise ValueError('Probe history must contain complete alternating fictional turns.')
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
