#!/usr/bin/env python3
"""Isolated persistent-vector replay with a pinned local encoder; no installed recall changes."""
import argparse
from datetime import timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import statistics
import sys
import tempfile
import time
from eval_memory import populate
from eval_semantic_memory import Encoder,MODEL_SHA,TOKENIZER_SHA,REVISION,choose,sample,scope_ids
from fish_journal import Journal
from fish_semantic_cache import SemanticCache,meaning

ROOT=Path(__file__).resolve().parents[1]
IDENTITY={'repo':'Qdrant/bge-small-zh-v1.5','revision':REVISION,'weight_sha256':MODEL_SHA,
          'tokenizer_sha256':TOKENIZER_SHA,'dimension':512,'pooling':'normalized CLS','query_instruction':True}


def encode_jobs(encoder,jobs):
    texts=[text for job in jobs for text in job.texts]
    if not texts:return []
    vectors=encoder.encode(texts);result=[];offset=0
    for job in jobs:
        result.append((job,vectors[offset:offset+len(job.texts)]));offset+=len(job.texts)
    return result


def fill(encoder,cache,now):
    jobs=cache.prepare(now,limit=128)
    encoded=encode_jobs(encoder,jobs)
    for job,vectors in encoded:
        if not cache.publish(job,vectors,now):raise AssertionError('Current fictional source unexpectedly rejected.')
    return {'source_jobs':len(jobs),'passage_windows':sum(len(job.texts)for job in jobs)}


def source_rows(store):return [tuple(row)for row in store.db.execute('SELECT * FROM episodes ORDER BY id')]


def lifecycle(encoder,root,now):
    checks={}
    with Journal(root,now=now)as journal,SemanticCache(journal,IDENTITY)as cache:
        row=journal.capture('fiction-gear','讨论铜色齿轮的装配。','装正以后不卡住了。')
        jobs=cache.prepare(now);old_job,old_vectors=encode_jobs(encoder,jobs)[0]
        assert cache.publish(old_job,old_vectors,now)
        query=encoder.encode(['之前铜色齿轮装好了吗'],query=True)[0]
        ranked=cache.rank(query,now)
        journal.update(row['id'],1,summary='更正：讨论的是银色弹簧，已经装回正确位置。')
        checks['correction_blocks_late_write']=not cache.publish(old_job,old_vectors,now)
        checks['correction_blocks_ranked_snapshot']=cache.resolve(ranked,now)==[]
        changed=cache.prepare(now)
        current_job,current_vectors=encode_jobs(encoder,changed)[0]
        assert cache.publish(current_job,current_vectors,now)
        resolved=cache.resolve(cache.rank(query,now),now)
        checks['only_current_corrected_text']=len(resolved)==1 and resolved[0]['excerpt']==journal.get(row['id'])['summary'] and '铜色'not in resolved[0]['excerpt']
        checks['only_changed_source_reencoded']=len(changed)==1 and cache.prepare(now)==[]
        ranked=cache.rank(query,now)
        journal.update(row['id'],2,forget=True)
        checks['forget_blocks_late_write']=not cache.publish(current_job,current_vectors,now)
        checks['forget_blocks_old_candidates']=cache.resolve(ranked,now)==[] and cache.rank(query,now)==[]
        checks['forget_prunes_on_next_access']=cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0]==0

        expiry=journal.capture('fiction-expiry','临时在木盒里放一枚绿色纽扣。','只保留一小时。')
        journal.update(expiry['id'],1,valid_until=(now+timedelta(hours=1)).isoformat())
        fill(encoder,cache,now);ranked=cache.rank(query,now)
        checks['expiry_boundary_blocks_candidates']=cache.resolve(ranked,now+timedelta(hours=1))==[]
        checks['expiry_boundary_prunes_vectors']=cache.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0]==0

        now+=timedelta(hours=1);journal.now=now
        alias=journal.capture('fiction-alias','讨论纸制风车的叶片。','四片叶子。')
        old_job,old_vectors=encode_jobs(encoder,[job for job in cache.prepare(now)if job.ident==alias['id']])[0]
        journal.update(alias['id'],1,aliases=['四叶小风轮'])
        checks['alias_change_blocks_late_write']=not cache.publish(old_job,old_vectors,now)
        pending=cache.prepare(now)
        checks['expired_sources_stay_unencoded']=all(job.ident!=expiry['id']for job in pending)
        current_job,current_vectors=encode_jobs(encoder,pending)[0]
        assert cache.publish(current_job,current_vectors,now)
        with SemanticCache(journal,{**IDENTITY,'revision':REVISION+'-different-identity'})as replacement:
            fill(encoder,replacement,now)
            checks['model_change_fences_old_worker']=not cache.publish(current_job,current_vectors,now) and cache.rank(query,now)==[]
            checks['replacement_model_remains_usable']=bool(replacement.resolve(replacement.rank(query,now),now))
    assert all(checks.values()),checks
    return checks


def evaluate(directory):
    fixture_names=['memory_replay.json','semantic_transfer.json','lexical_precision.json']
    raw={name:(ROOT/'tests/fixtures'/name).read_bytes()for name in fixture_names}
    fixtures={name:json.loads(value)for name,value in raw.items()};base=fixtures[fixture_names[0]]
    fixture={**base,'episodes':[row for name in fixture_names for row in fixtures[name]['episodes']]}
    cases=base['queries']+base['semantic_stress']+[row for name in fixture_names[1:]for row in fixtures[name]['queries']]
    started=time.perf_counter();encoder=Encoder(directory);load_ms=(time.perf_counter()-started)*1000
    with tempfile.TemporaryDirectory(prefix='fish-semantic-cache-')as temporary:
        root=Path(temporary);now,mapping=populate(root/'replay',fixture)
        with Journal(root/'replay',now=now)as journal:
            before=source_rows(journal)
            fresh,fresh_timing=sample(encoder,journal,cases,mapping)
            started=time.perf_counter()
            with SemanticCache(journal,IDENTITY)as cache:cold=fill(encoder,cache,now)
            cold['prepare_encode_publish_ms']=round((time.perf_counter()-started)*1000,2)
            queries=encoder.encode([case['query']for case in cases],query=True)
            with SemanticCache(journal,IDENTITY)as cache:
                initial_changes=cache.db.total_changes
                assert cache.prepare(now)==[],'Warm cache must not schedule source encoding.'
                sources=[dict(row)for row in journal.db.execute("SELECT * FROM episodes WHERE status='active'")if journal.effective_status(row)=='active']
                compared=[];latencies=[];largest_difference=0
                for case,query,reference in zip(cases,queries,fresh):
                    started=time.perf_counter()
                    ranked=cache.rank(query,now,allowed_ids=scope_ids(journal,case['query'],sources))
                    resolved=cache.resolve(ranked,now)
                    latencies.append((time.perf_counter()-started)*1000)
                    dense=[{'key':mapping[row['id']],'score':row['score']}for row in ranked]
                    assert [r['key']for r in dense]==[r['key']for r in reference['dense']],'Persistent and fresh top-five rankings differ.'
                    assert len(resolved)==len(ranked),'Current candidates should resolve.'
                    for resolved_row in resolved:assert resolved_row['excerpt']==meaning(journal.get(resolved_row['id']))
                    largest_difference=max([largest_difference]+[abs(a['score']-b['score'])for a,b in zip(dense,reference['dense'])])
                    margin=dense[0]['score']-dense[1]['score']if len(dense)>1 else dense[0]['score']if dense else 0
                    cached={**reference,'dense':dense,'margin':margin}
                    assert choose(reference,.55,.06)==choose(cached,.55,.06),'The previously fixed gate changed decisions.'
                    compared.append({'query':case['query'],'top5':[r['key']for r in dense],'hybrid':choose(cached,.55,.06)})
                assert largest_difference<2e-5,'Unexpected float32 score drift.'
                changes=cache.db.total_changes-initial_changes
                assert changes==0,'Healthy warm lookup must not mutate the cache.'
                assert source_rows(journal)==before,'Read/encoding work changed primary sources.'
                cache.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                cache_bytes=(journal.root/'data/memory/semantic-cache.sqlite3').stat().st_size
            checks=lifecycle(encoder,root/'lifecycle',now)
        # Actual per-query encoding cost remains, even with every source already cached.
        single=[]
        for case in cases[:10]:
            started=time.perf_counter();encoder.encode([case['query']],query=True);single.append((time.perf_counter()-started)*1000)
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin'else 1024)
    return {'scope':'Fictional temporary stores, exact cached-versus-fresh retrieval parity. No private chat, network, paid API or installed recall changes.',
            'model':IDENTITY,'fixture_hashes':{name:hashlib.sha256(value).hexdigest()for name,value in raw.items()},
            'dependencies':{name:importlib.metadata.version(name)for name in ['onnxruntime','tokenizers','numpy']},
            'source_rows':fresh_timing['source_rows'],'queries':len(cases),'cold_cache':cold,
            'warm_cache':{'source_encoding_jobs':0,'lookup_logical_writes':changes,'top5_matches':len(compared),
                          'fixed_gate_matches':len(compared),'max_score_difference':largest_difference,'sqlite_bytes':cache_bytes,
                          'rank_and_resolve_median_ms':round(statistics.median(latencies),3),
                          'rank_and_resolve_p95_ms':round(sorted(latencies)[int(.95*(len(latencies)-1))],3)},
            'resources':{'encoder_load_checksum_ms':round(load_ms,2),'query_encoding_median_ms':round(statistics.median(single),3),'peak_rss_mib':round(peak,1)},
            'lifecycle_checks':checks,'cases':compared}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--model-dir',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.model_dir)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items()if key!='cases'},ensure_ascii=False,indent=2))
