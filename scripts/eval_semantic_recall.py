#!/usr/bin/env python3
"""Real bounded encoder plus installed-path-compatible recall over fictional stores only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
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
    positive=[r for r in rows if r['expected']];controls=[r for r in rows if not r['expected']and r.get('kind')in ('missing_detail','ambiguous_subject')]
    negative=[r for r in rows if not r['expected']and r not in controls]
    return {'positive_cases':len(positive),'positive_any':sum(bool(set(r[field])&set(r['expected']))for r in positive),
            'negative_cases':len(negative),'false_positives':sum(bool(r[field])for r in negative),
            'control_cases':len(controls),'control_unrelated_contexts':sum(bool(set(r[field])-set(r.get('related',[])))for r in controls),
            'unexpected_contexts':sum(bool(set(r[field])-set(r['expected'])-set(r.get('related',[])))for r in rows),
            'unwanted_contexts':sum(bool(set(r[field])&set(r.get('unwanted',[])))for r in rows)}


def corpus_cases(fixtures,annotations):
    """Retain every original query; explicit annotations belong to this merged corpus only."""
    keys=[row['key']for fixture in fixtures.values()for row in fixture['episodes']]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate fictional source key.')
    known=set(keys);result={name:[dict(row)for row in fixture['queries']+fixture.get('semantic_stress',[])]for name,fixture in fixtures.items()}
    seen=set()
    for annotation in annotations:
        target=(annotation['group'],annotation['query'])
        matches=[row for row in result.get(target[0],[])if row['query']==target[1]]
        if target in seen or len(matches)!=1 or not isinstance(annotation.get('reason'),str)or not annotation['reason'].strip():raise ValueError('Ambiguous or unexplained corpus annotation.')
        if annotation.get('kind')not in ('missing_detail','ambiguous_subject'):raise ValueError('Unknown corpus control kind.')
        matches[0].update({key:annotation[key]for key in ('kind','expected','related')})
        matches[0]['corpus_annotation']=annotation['reason'];seen.add(target)
    for rows in result.values():
        for row in rows:
            for field in ('expected','related','unwanted'):
                values=row.get(field,[])
                if not isinstance(values,list)or any(not isinstance(value,str)or value not in known for value in values):raise ValueError('Unknown fictional source in query labels.')
            if row.get('kind')in ('missing_detail','ambiguous_subject')and (row['expected']or not row.get('related')):raise ValueError('Corpus controls need explicit related sources and cannot be positive targets.')
    return result


def evaluate(runtime_home,baseline,extra_fixture=None):
    names=['memory_replay.json','semantic_transfer.json','lexical_precision.json','memory_constraints.json']
    if extra_fixture:
        if not re.fullmatch(r'[a-z][a-z0-9_]*\.json',extra_fixture)or extra_fixture in names:raise ValueError('Invalid extra fixture name.')
        names.append(extra_fixture)
    raw={name:(ROOT/'tests/fixtures'/name).read_bytes()for name in names};fixtures={name:json.loads(value)for name,value in raw.items()}
    annotations_raw=(ROOT/'tests/fixtures/semantic_corpus_annotations.json').read_bytes()
    annotations=json.loads(annotations_raw)['annotations'];cases_by_group=corpus_cases(fixtures,annotations)
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
                cases=cases_by_group[name]
                for case in cases:
                    wanted=case.get('must_include',[]);wanted=[wanted]if isinstance(wanted,str)else wanted
                    old_context=previous.recall(case['query']);lexical=journal.recall(case['query'])
                    # Hold the semantic supplement fixed to isolate the journal's
                    # evidence gate, rather than calling lexical-only a full baseline.
                    old_with_semantics=helper.recall(previous,case['query'])
                    started=time.perf_counter();context=helper.recall(journal,case['query']);timings.append((time.perf_counter()-started)*1000)
                    result={**case,'group':name,'before':ids(old_context,mapping),'lexical':ids(lexical,mapping),'current':ids(context,mapping),
                            'baseline_journal_semantic':ids(old_with_semantics,mapping),
                            'chars':len(context),'contains_required':not context or all(value in context for value in wanted),
                            'semantic':bool(context and json.loads(context.split('\n',1)[1])[0].get('match_kind')=='semantic')}
                    if lexical and context!=lexical:raise AssertionError('Semantic supplement changed an existing lexical result.')
                    if len(context)>4200:raise AssertionError('Recall budget exceeded.')
                    results.append(result)
            assert [tuple(row)for row in journal.db.execute('SELECT * FROM episodes ORDER BY id')]==source_before,'Recall/index changed source rows.'
    return {'baseline':revision,'model':MODEL_IDENTITY,'fixture_hashes':{name:hashlib.sha256(value).hexdigest()for name,value in raw.items()},
            'corpus_annotation_hash':hashlib.sha256(annotations_raw).hexdigest(),'corpus_annotations':annotations,
            'implementation_hashes':{name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()for name in ('fish_journal.py','fish_semantic_recall.py','fish_semantic_cache.py','eval_semantic_recall.py')},
            'groups':{name:{field:metrics([r for r in results if r['group']==name],field)for field in ['before','baseline_journal_semantic','lexical','current']}for name in names},
            'queries':len(results),'semantic_supplements':sum(r['semantic']for r in results),'max_context_chars':max(r['chars']for r in results),
            'missing_required_fragments':sum(not r['contains_required']for r in results),'max_lookup_ms':round(max(timings),2),
            'scope':'Fictional retrieval and quoting only; no answer-generation accuracy claim or paid model calls. baseline_journal_semantic holds the current semantic helper fixed over the selected baseline journal; not a generic full-version baseline. Fixtures and corpus annotations are observed developer data.',
            'cases':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime-home',type=Path,required=True)
    parser.add_argument('--baseline',default='2122ff3');parser.add_argument('--output',type=Path)
    parser.add_argument('--extra-fixture',help='Add one declared fictional fixture to the full merged corpus; never replaces the existing cases.')
    args=parser.parse_args();result=evaluate(args.runtime_home,args.baseline,args.extra_fixture)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items()if key!='cases'},ensure_ascii=False,indent=2))
