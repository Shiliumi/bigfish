#!/usr/bin/env python3
"""Compare source quoting over fictional stores; no private data, network or model."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import eval_memory
from fish_journal import Journal

ROOT=Path(__file__).resolve().parents[1]


def run(klass,root,data,cases):
    with patch.object(eval_memory,'Journal',klass):now,mapping=eval_memory.populate(root,data)
    result=[]
    with klass(root,now=now)as store:
        original=[tuple(row)for row in store.db.execute('SELECT * FROM episodes ORDER BY id')]
        for case in cases:
            context=store.recall(case['query'])
            rows=json.loads(context.split('\n',1)[1])if context else []
            # Check the actual quote, never count a stray prefix-summary as preserved context.
            excerpts='\n'.join(row['excerpt']for row in rows)
            required=case.get('must_include',[])
            required=[required]if isinstance(required,str)else required
            result.append({'query':case['query'],'expected':case['expected'],'kind':case.get('kind'),
                'recalled':[mapping[row['id']]for row in rows],
                'manual':[mapping[row['id']]for row in store.search(case['query'],limit=5)],
                'quote_preserved':all(value in excerpts for value in required),
                'forbidden_absent':all(value not in context for value in case.get('forbidden',[])),
                'chars':len(context),'within_budget':len(context)<=4200})
        assert original==[tuple(row)for row in store.db.execute('SELECT * FROM episodes ORDER BY id')],'Source rows changed'
    return result


def summary(rows):
    positive=[row for row in rows if row['expected']]
    negative=[row for row in rows if not row['expected']and row.get('kind')!='missing_detail']
    return {'queries':len(rows),'positive_cases':len(positive),
        'target_in_context':sum(bool(set(row['expected'])&set(row['recalled']))for row in positive),
        'negative_contexts':sum(bool(row['recalled'])for row in negative),'negative_cases':len(negative),
        'incomplete_required_quotes':sum(not row['quote_preserved']for row in rows),
        'forbidden_contexts':sum(not row['forbidden_absent']for row in rows),
        'total_context_chars':sum(row['chars']for row in rows),'max_context_chars':max(row['chars']for row in rows),
        'budget_failures':sum(not row['within_budget']for row in rows)}


def evaluate(baseline):
    revision=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',baseline+'^{commit}'],cwd=ROOT,text=True).strip()
    names=['memory_replay.json','semantic_transfer.json','lexical_precision.json','memory_constraints.json','memory_excerpt_boundaries.json']
    raw={name:(ROOT/'tests/fixtures'/name).read_bytes()for name in names};fixtures={name:json.loads(value)for name,value in raw.items()}
    base=fixtures[names[0]];combined={**base,'episodes':[row for name in names[:-1]for row in fixtures[name]['episodes']]}
    boundary=fixtures[names[-1]]['cases']
    special={**base,'episodes':[{'day':8,**row}for row in boundary]}
    special_cases=[{**row,'expected':[]if row.get('must_empty')else[row['key']]}for row in boundary]
    suites=[(name,combined,fixtures[name]['queries']+fixtures[name].get('semantic_stress',[]))for name in names[:-1]]+[(names[-1],special,special_cases)]
    with tempfile.TemporaryDirectory(prefix='fish-excerpt-replay-')as directory:
        root=Path(directory);path=root/'baseline.py';path.write_bytes(subprocess.check_output(['git','show',revision+':scripts/fish_journal.py'],cwd=ROOT))
        spec=importlib.util.spec_from_file_location('_fish_excerpt_baseline',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        groups={}
        for number,(name,data,cases)in enumerate(suites):
            before=run(module.Journal,root/(str(number)+'-before'),data,cases)
            after=run(Journal,root/(str(number)+'-after'),data,cases)
            groups[name]={'before':summary(before),'after':summary(after),
                'manual_search_identical':all(a['manual']==b['manual']for a,b in zip(before,after)),
                'changed':[{'query':a['query'],'before':a,'after':b}for a,b in zip(before,after)if a!=b]}
    return {'baseline':revision,'fixture_hashes':{name:hashlib.sha256(value).hexdigest()for name,value in raw.items()},
        'groups':groups,'scope':'Fictional lexical retrieval and verbatim quoting only; not generation quality, supplier tokens, or real-chat cost.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',default='3fccaeb');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.baseline)
    if args.output:
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps({**result,'groups':{name:{key:value for key,value in group.items()if key!='changed'}for name,group in result['groups'].items()}},ensure_ascii=False,indent=2))
