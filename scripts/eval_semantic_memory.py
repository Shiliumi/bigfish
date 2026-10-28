#!/usr/bin/env python3
"""Experimental local semantic replay. Uses fictional temp stores; never installed as recall."""
import argparse
from datetime import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import resource
import statistics
import sys
import tempfile
import time
from eval_memory import populate
from fish_journal import Journal,dated_query,chunks,query_parts

ROOT=Path(__file__).resolve().parents[1]
MODEL_SHA='1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38'
TOKENIZER_SHA='48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26'
REVISION='46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59'
THRESHOLDS=(.25,.30,.35,.40,.45,.50,.55,.60,.65,.70,.75,.80,.85,.90)
MARGINS=(0,.03,.06)


class Encoder:
    def __init__(self,directory):
        directory=Path(directory);weight=directory/'model_optimized.onnx'
        with weight.open('rb')as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
        if digest!=MODEL_SHA:raise ValueError('The local model does not match the pinned public weight.')
        if hashlib.sha256((directory/'tokenizer.json').read_bytes()).hexdigest()!=TOKENIZER_SHA:raise ValueError('The tokenizer does not match the pinned public model.')
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np=np
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.log_severity_level=3
        self.session=ort.InferenceSession(str(weight),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(directory/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=512);self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
        self.inputs={i.name for i in self.session.get_inputs()}

    def encode(self,texts,query=False):
        result=[]
        for start in range(0,len(texts),16):
            batch=texts[start:start+16]
            if query:batch=['为这个句子生成表示以用于检索相关文章：'+s for s in batch]
            encoded=self.tokenizer.encode_batch(batch)
            inputs={'input_ids':[e.ids for e in encoded],'attention_mask':[e.attention_mask for e in encoded],
                    'token_type_ids':[e.type_ids for e in encoded]}
            outputs=self.session.run(None,{k:self.np.asarray(v,dtype=self.np.int64)for k,v in inputs.items()if k in self.inputs})
            vectors=outputs[0][:,0,:]if outputs[0].ndim==3 else outputs[0]
            norms=self.np.linalg.norm(vectors,axis=1,keepdims=True)
            result.append(vectors/self.np.maximum(norms,1e-12))
        return self.np.concatenate(result)


def scope_ids(store,query,rows):
    try:
        cleaned,dates=dated_query(query,store.now)
        if not query_parts(chunks(cleaned)):return set()
        if not(re.search(r'聊|说|提|谈|讨论|对话|记录',query)or not chunks(cleaned)):dates=None
    except ValueError:return set()
    return {r['id']for r in rows if not dates or datetime.fromisoformat(dates[0])<=datetime.fromisoformat(r['recorded_at'])<datetime.fromisoformat(dates[1])}


def sample(encoder,store,cases,mapping):
    rows=[dict(r)for r in store.db.execute("SELECT * FROM episodes WHERE status='active'")if store.effective_status(r)=='active']
    texts=[];owners=[]
    for row in rows:
        body=row['summary']if row['corrected_at']else row['excerpt']
        alias='\n'.join(json.loads(row['aliases']))
        # Keep long sources in local overlapping windows instead of dropping their late details.
        for offset in range(0,len(body),220):
            texts.append(body[offset:offset+280]+('\n'+alias if alias else ''));owners.append(row['id'])
    started=time.perf_counter();vectors=encoder.encode(texts);index_ms=(time.perf_counter()-started)*1000
    started=time.perf_counter();queries=encoder.encode([r['query']for r in cases],query=True);query_ms=(time.perf_counter()-started)*1000
    results=[]
    for case,vector in zip(cases,queries):
        allowed=scope_ids(store,case['query'],rows);scores={}
        for ident,score in zip(owners,vectors@vector):
            if ident in allowed:scores[ident]=max(scores.get(ident,-1),float(score))
        ranked=sorted(scores.items(),key=lambda r:(-r[1],r[0]))
        recall=store.recall(case['query'])
        lexical=[mapping[r['id']]for r in json.loads(recall.split('\n',1)[1])]if recall else []
        results.append({**case,'lexical':lexical,'dense':[{'key':mapping[ident],'score':score}for ident,score in ranked[:5]],
                        'margin':ranked[0][1]-ranked[1][1]if len(ranked)>1 else ranked[0][1]if ranked else 0})
    return results,{'source_rows':len(rows),'passage_windows':len(texts),'index_ms':round(index_ms,2),
                    'batch_query_ms_per_query':round(query_ms/len(cases),3)}


def choose(row,threshold,margin):
    if row['lexical']:return row['lexical']
    dense=row['dense']
    return [dense[0]['key']]if dense and dense[0]['score']>=threshold and row['margin']>=margin else []


def metrics(rows,select):
    positive=[r for r in rows if r['expected']];negative=[r for r in rows if not r['expected']and r.get('kind')!='missing_detail']
    return {'positive_cases':len(positive),'negative_cases':len(negative),
            'positive_any':sum(bool(set(select(r)).intersection(r['expected']))for r in positive),
            'positive_first':sum(bool(select(r)and select(r)[0]in r['expected'])for r in positive),
            'negative_abstention':sum(not select(r)for r in negative),
            'false_positive_cases':sum(bool(select(r))for r in negative)}


def evaluate(directory):
    base_text=(ROOT/'tests/fixtures/memory_replay.json').read_bytes();transfer_text=(ROOT/'tests/fixtures/semantic_transfer.json').read_bytes()
    base=json.loads(base_text);transfer=json.loads(transfer_text)
    started=time.perf_counter();encoder=Encoder(directory);load_ms=(time.perf_counter()-started)*1000
    with tempfile.TemporaryDirectory(prefix='fish-semantic-replay-')as temporary:
        root=Path(temporary);now,mapping=populate(root/'calibration',base)
        with Journal(root/'calibration',now=now)as store:
            calibration,timing_before=sample(encoder,store,base['queries']+base['semantic_stress'],mapping)
        options=[]
        for threshold in THRESHOLDS:
            for margin in MARGINS:
                score=metrics(calibration,lambda r:choose(r,threshold,margin))
                options.append(((-score['false_positive_cases'],score['positive_any'],threshold,margin),threshold,margin,score))
        _,threshold,margin,selected=max(options)
        data={**base,'episodes':base['episodes']+transfer['episodes']}
        now,mapping=populate(root/'transfer',data)
        with Journal(root/'transfer',now=now)as store:
            validation,timing_after=sample(encoder,store,transfer['queries'],mapping)
        elapsed=[]
        for query in [r['query']for r in base['queries'][:10]]:
            started=time.perf_counter();encoder.encode([query],query=True);elapsed.append((time.perf_counter()-started)*1000)
    def describe(rows):
        return {'lexical':metrics(rows,lambda r:r['lexical']),
                'ungated_dense':metrics(rows,lambda r:[r['dense'][0]['key']]if r['dense']else []),
                'lexical_then_dense':metrics(rows,lambda r:choose(r,threshold,margin)),
                'cases':[{**r,'hybrid':choose(r,threshold,margin)}for r in rows]}
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin'else 1024)
    return {'model':{'repo':'Qdrant/bge-small-zh-v1.5','revision':REVISION,'weight_sha256':MODEL_SHA,'tokenizer_sha256':TOKENIZER_SHA,'dimension':512,'pooling':'normalized CLS','query_instruction':True,'cpu_threads':2},
            'fixture_hashes':{'calibration':hashlib.sha256(base_text).hexdigest(),'transfer':hashlib.sha256(transfer_text).hexdigest()},
            'dependencies':{name:importlib.metadata.version(name)for name in ['onnxruntime','tokenizers','numpy']},
            'selection':{'threshold_grid':THRESHOLDS,'margin_grid':MARGINS,'threshold':threshold,'margin':margin,
                         'policy':'Minimize calibration false positives, then maximize positive-any; ties prefer stricter gates. Transfer labels are not used.','calibration_score':selected},
            'calibration':describe(calibration),'transfer':describe(validation),
            'missing_detail_cases':[r for r in describe(validation)['cases']if r.get('kind')=='missing_detail'],
            'resources':{'load_and_checksum_ms':round(load_ms,2),'calibration':timing_before,'transfer':timing_after,
                         'warm_single_query_median_ms':round(statistics.median(elapsed),2),'peak_process_rss_mb':round(rss,1),
                         'model_directory_bytes':sum(p.stat().st_size for p in Path(directory).iterdir()if p.is_file())},
            'scope':'Synthetic local retrieval IDs only, not answer correctness. No private chat, network, API token or installed recall change.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--model-dir',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.model_dir);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    summary={key:value for key,value in result.items()if key not in ('calibration','transfer','missing_detail_cases')}
    for group in ['calibration','transfer']:summary[group]={key:value for key,value in result[group].items()if key!='cases'}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
