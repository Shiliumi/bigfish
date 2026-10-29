#!/usr/bin/env python3
"""Compare automatic recall and manual search on fictional temp stores; no model or network."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import eval_memory
from fish_journal import Journal

ROOT=Path(__file__).resolve().parents[1]


def replay(klass,root,data,cases):
    with patch.object(eval_memory,'Journal',klass):now,mapping=eval_memory.populate(root,data)
    rows=[]
    with klass(root,now=now)as store:
        for case in cases:
            context=store.recall(case['query'])
            recalled=[mapping[r['id']]for r in json.loads(context.split('\n',1)[1])]if context else []
            manual=[mapping[r['id']]for r in store.search(case['query'],limit=5)]
            rows.append({**case,'recalled':recalled,'manual_search':manual,'context_chars':len(context)})
    return rows


def summarize(rows):
    positive=[r for r in rows if r['expected']];negative=[r for r in rows if not r['expected']and r.get('kind')!='missing_detail']
    return {'positive_cases':len(positive),'positive_target_recalled':sum(bool(set(r['expected']).intersection(r['recalled']))for r in positive),
            'negative_cases':len(negative),'negative_contexts':sum(bool(r['recalled'])for r in negative),
            'total_context_chars':sum(r['context_chars']for r in rows)}


def evaluate(baseline='823516b'):
    commit=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',baseline+'^{commit}'],cwd=ROOT,text=True).strip()
    base=json.loads((ROOT/'tests/fixtures/memory_replay.json').read_text())
    transfer=json.loads((ROOT/'tests/fixtures/semantic_transfer.json').read_text())
    fresh=json.loads((ROOT/'tests/fixtures/lexical_precision.json').read_text())
    suites=[('original',base,base['queries']),
            ('transfer',{**base,'episodes':base['episodes']+transfer['episodes']},transfer['queries']),
            ('fresh',{**base,'episodes':base['episodes']+transfer['episodes']+fresh['episodes']},fresh['queries'])]
    with tempfile.TemporaryDirectory(prefix='fish-evidence-replay-')as temporary:
        directory=Path(temporary);path=directory/'baseline.py';path.write_bytes(subprocess.check_output(['git','show',commit+':scripts/fish_journal.py'],cwd=ROOT))
        spec=importlib.util.spec_from_file_location('_recall_evidence_baseline',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result={}
        for name,data,cases in suites:
            before=replay(module.Journal,directory/(name+'-before'),data,cases);after=replay(Journal,directory/(name+'-after'),data,cases)
            result[name]={'before':summarize(before),'after':summarize(after),
                          'manual_search_identical':all(a['manual_search']==b['manual_search']for a,b in zip(before,after)),
                          'changed':[{'query':a['query'],'expected':a['expected'],'kind':a.get('kind'),
                                      'before':a['recalled'],'after':b['recalled']}for a,b in zip(before,after)if a['recalled']!=b['recalled']]}
    return {'baseline':commit,'suites':result,'scope':'Automatic recall context only; missing-detail controls excluded from negative counts. No model, private chat, or measured total token/cost saving.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',default='823516b');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.baseline);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='')
