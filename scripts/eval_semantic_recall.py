#!/usr/bin/env python3
"""Real bounded encoder plus installed-path-compatible recall over fictional stores only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
from eval_memory import populate
from fish_journal import Journal
from fish_semantic_recall import SemanticRecall
from fish_semantic_cache import SemanticCache
from fish_embeddings import MODEL_IDENTITY

ROOT=Path(__file__).resolve().parents[1]


def ids(context,mapping):return [mapping[r['id']]for r in json.loads(context.split('\n',1)[1])]if context else []


def metrics(rows,field):
    positive=[r for r in rows if r['expected']];negative=[r for r in rows if not r['expected']and r.get('kind')!='missing_detail']
    return {'positive_cases':len(positive),'positive_any':sum(bool(set(r[field])&set(r['expected']))for r in positive),
            'negative_cases':len(negative),'false_positives':sum(bool(r[field])for r in negative),
            'unwanted_contexts':sum(bool(set(r[field])&set(r.get('unwanted',[])))for r in rows)}


def evaluate(runtime_home,baseline):
    names=['memory_replay.json','semantic_transfer.json','lexical_precision.json','memory_constraints.json']
    raw={name:(ROOT/'tests/fixtures'/name).read_bytes()for name in names};fixtures={name:json.loads(value)for name,value in raw.items()}
    base=fixtures[names[0]];fixture={**base,'episodes':[row for name in names for row in fixtures[name]['episodes']]}
    revision=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',baseline+'^{commit}'],cwd=ROOT,text=True).strip()
    before_source=subprocess.check_output(['git','show',revision+':scripts/fish_journal.py'],cwd=ROOT,text=True)
    results=[];timings=[]
    with tempfile.TemporaryDirectory(prefix='fish-semantic-recall-')as directory:
        root=Path(directory);old=root/'before.py';old.write_text(before_source)
        spec=importlib.util.spec_from_file_location('fish_recall_baseline',old);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        now,mapping=populate(root,fixture);helper=SemanticRecall(root,runtime_home=runtime_home)
        with Journal(root,now=now)as journal,module.Journal(root,now=now)as previous:
            source_before=[tuple(row)for row in journal.db.execute('SELECT * FROM episodes ORDER BY id')]
            deadline=time.monotonic()+45
            with SemanticCache(journal,MODEL_IDENTITY)as cache:
                while not cache.covered(cache._sources(now),now):
                    remaining=deadline-time.monotonic()
                    if remaining<.05 or not helper.index_pending(journal,budget=min(3,remaining),max_jobs=2):raise ValueError('Fictional index preparation incomplete; no fake-success replay.')
            for name in names:
                cases=fixtures[name]['queries']+fixtures[name].get('semantic_stress',[])
                for case in cases:
                    wanted=case.get('must_include',[]);wanted=[wanted]if isinstance(wanted,str)else wanted
                    old_context=previous.recall(case['query']);lexical=journal.recall(case['query'])
                    started=time.perf_counter();context=helper.recall(journal,case['query']);timings.append((time.perf_counter()-started)*1000)
                    result={**case,'group':name,'before':ids(old_context,mapping),'lexical':ids(lexical,mapping),'current':ids(context,mapping),
                            'chars':len(context),'contains_required':not context or all(value in context for value in wanted),
                            'semantic':bool(context and json.loads(context.split('\n',1)[1])[0].get('match_kind')=='semantic')}
                    if lexical and context!=lexical:raise AssertionError('Semantic supplement changed an existing lexical result.')
                    if len(context)>4200:raise AssertionError('Recall budget exceeded.')
                    results.append(result)
            assert [tuple(row)for row in journal.db.execute('SELECT * FROM episodes ORDER BY id')]==source_before,'Recall/index changed source rows.'
    return {'baseline':revision,'model':MODEL_IDENTITY,'fixture_hashes':{name:hashlib.sha256(value).hexdigest()for name,value in raw.items()},
            'groups':{name:{field:metrics([r for r in results if r['group']==name],field)for field in ['before','lexical','current']}for name in names},
            'queries':len(results),'semantic_supplements':sum(r['semantic']for r in results),'max_context_chars':max(r['chars']for r in results),
            'missing_required_fragments':sum(not r['contains_required']for r in results),'max_lookup_ms':round(max(timings),2),
            'scope':'Fictional retrieval and quoting only; no answer-generation accuracy claim or paid model calls. New constraint examples are observed developer data.',
            'cases':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime-home',type=Path,required=True)
    parser.add_argument('--baseline',default='2122ff3');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.runtime_home,args.baseline)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items()if key!='cases'},ensure_ascii=False,indent=2))
