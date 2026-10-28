#!/usr/bin/env python3
"""Compare exact recall payload packing on fictional fixtures, without model requests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import eval_memory
from fish_journal import Journal

ROOT=Path(__file__).resolve().parents[1]
BASELINE='f86119b'


def evaluate():
    fixture=json.loads(eval_memory.FIXTURE.read_text())
    with tempfile.TemporaryDirectory(prefix='fish-context-compare-')as temp:
        folder=Path(temp);file=folder/'baseline.py'
        file.write_bytes(subprocess.check_output(['git','show',BASELINE+':scripts/fish_journal.py'],cwd=ROOT))
        spec=importlib.util.spec_from_file_location('_context_baseline',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        runs=[]
        for index,klass in enumerate((module.Journal,Journal)):
            root=folder/str(index)
            with patch.object(eval_memory,'Journal',klass):now,_=eval_memory.populate(root,fixture)
            with klass(root,now=now)as store:runs.append([store.recall(case['query'])for case in fixture['queries']])
    preserved=True;before,after=runs
    for old,new in zip(before,after):
        rows=lambda s:json.loads(s.split('\n',1)[1])if s else []
        current={r['id']:r for r in rows(new)}
        for row in rows(old):
            found=current.get(row['id'],{})
            if any(found.get(k)!=v for k,v in row.items()if k!='summary'):preserved=False
            if 'summary'in found:
                if found['summary']!=row['summary']:preserved=False
            else:
                a,separator,b=found.get('excerpt','').removeprefix('你：').partition('\n大肥鱼：');parts=row['summary'].split(' · ',1)
                if row['summary']!=found.get('excerpt')and not(separator and len(parts)==2 and parts[0]in a and parts[1]in b):preserved=False
    return {'baseline':BASELINE,'queries':len(before),'before_chars':sum(map(len,before)),'after_chars':sum(map(len,after)),
            'removed_chars':sum(map(len,before))-sum(map(len,after)),'old_sources_and_text_preserved':preserved,
            'note':'Synthetic recall payload characters only; excludes new matter/tool costs, tokenizer, cache and provider billing.'}


if __name__=='__main__':print(json.dumps(evaluate(),ensure_ascii=False,indent=2))
