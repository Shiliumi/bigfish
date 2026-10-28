#!/usr/bin/env python3
"""Offline retrieval replay over hand-written fictional conversations. No model or private data."""
import argparse
from collections import defaultdict
from datetime import datetime,timedelta
import inspect
import json
from pathlib import Path
import tempfile
from fish_journal import Journal

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/memory_replay.json'


def populate(root,fixture):
    now=datetime.fromisoformat(fixture['now']);base=now.replace(day=1,hour=12,minute=0,second=0,microsecond=0)
    mapping={}
    for item in fixture['episodes']:
        with Journal(root,now=now) as store:
            row=store.capture('replay-'+item['key'],item['user'],item['assistant'],(base+timedelta(days=item['day']-1)).isoformat())
        when=base+timedelta(days=item.get('correction_day',19)-1)
        with Journal(root,now=when) as store:
            change={}
            if item.get('correction'):change['summary']=item['correction']
            if item.get('pinned'):change['pinned']=True
            if item.get('expiry_day'):change['valid_until']=(base+timedelta(days=item['expiry_day']-1)).isoformat()
            if item.get('forget'):change['forget']=True
            if item.get('aliases') and 'aliases' in inspect.signature(store.update).parameters:change['aliases']=item['aliases']
            if change:store.update(row['id'],row['revision'],**change)
        mapping[row['id']]=item['key']
    return now,mapping


def evaluate(fixture=FIXTURE):
    data=json.loads(Path(fixture).read_text());results=[];stress=[]
    with tempfile.TemporaryDirectory(prefix='fish-memory-replay-') as directory:
        root=Path(directory);now,mapping=populate(root,data)
        with Journal(root,now=now) as store:
            for case in data['queries']:
                found=[mapping[r['id']]for r in store.search(case['query'],limit=5)]
                context=store.recall(case['query'])
                recalled=[mapping[item['id']]for item in json.loads(context.split('\n',1)[1])] if context else []
                expected=set(case['expected'])
                positive=bool(expected)
                hit=bool(expected.intersection(found)) if positive else not found
                forbidden=all(s not in context for s in case.get('forbidden',[]))
                wanted=case.get('must_include',[]);wanted=[wanted]if isinstance(wanted,str)else wanted
                snippet=all(s in context for s in wanted)
                results.append({'query':case['query'],'category':case['category'],'split':case.get('split','development'),
                    'positive':positive,'top5':hit,'top1':bool(found and found[0]in expected)if positive else not found,
                    'context_hit':bool(expected.intersection(recalled))if positive else not recalled,
                    'safe_context':forbidden,'snippet':snippet,'context_chars':len(context),'found':found,'expected':case['expected']})
            for case in data.get('semantic_stress',[]):
                found=[mapping[r['id']]for r in store.search(case['query'],limit=5)]
                stress.append({'query':case['query'],'top5':bool(set(found).intersection(case['expected'])),'found':found,'expected':case['expected']})
    positives=[r for r in results if r['positive']];negatives=[r for r in results if not r['positive']]
    categories=defaultdict(list)
    for row in results:categories[row['category']].append(row)
    return {'fixture_version':data['version'],'cases':len(results),'positive_cases':len(positives),'negative_cases':len(negatives),
        'top5_recall':sum(r['top5']for r in positives)/len(positives),'top1_accuracy':sum(r['top1']for r in positives)/len(positives),
        'context_recall':sum(r['context_hit']for r in positives)/len(positives),
        'negative_abstention':sum(r['top5']for r in negatives)/len(negatives),'unsafe_contexts':sum(not r['safe_context']for r in results),
        'missing_snippets':sum(not r['snippet']for r in results),'max_context_chars':max(r['context_chars']for r in results),
        'categories':{key:{'cases':len(rows),'passed':sum(r['top5']and r['safe_context']and r['snippet']for r in rows)}for key,rows in categories.items()},
        'heldout':{'cases':sum(r['split']=='heldout'for r in results),'passed':sum(r['split']=='heldout'and r['top5']and r['safe_context']and r['snippet']for r in results)},
        'failures':[r for r in results if not(r['top5']and r['safe_context']and r['snippet']and r['context_hit'])],
        'semantic_stress':stress,'note':'Offline synthetic retrieval only; not a measured real-chat or answer-quality success rate.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
