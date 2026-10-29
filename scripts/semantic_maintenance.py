#!/usr/bin/env python3
"""Explicit local vector backfill/check, without model API calls or recurring tasks."""
import argparse
import json
from pathlib import Path
import time
from fish_journal import Journal
from fish_semantic_recall import SemanticRecall
from fish_semantic_cache import SemanticCache
from fish_embeddings import MODEL_IDENTITY

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--seconds',type=float,default=30);parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if not .1<=args.seconds<=120:parser.error('--seconds must be between 0.1 and 120.')
    helper=SemanticRecall(args.root)
    if not helper.available():parser.error('Optional encoder runtime missing; run setup_semantic_runtime.py explicitly first.')
    deadline=time.monotonic()+args.seconds;indexed=0
    with Journal(args.root)as journal:
        if not args.check:
            while deadline-time.monotonic()>=.05:
                count=helper.index_pending(journal,budget=min(3,deadline-time.monotonic()),max_jobs=2)
                indexed+=count
                if not count:break
        with SemanticCache(journal,MODEL_IDENTITY,timeout=.1)as cache:
            sources=cache._sources(journal.now);complete=cache.covered(sources,journal.now)
        print(json.dumps({'indexed':indexed,'active_sources':len(sources),'complete':complete,'local_only':True}))
    return 0 if complete else 1


if __name__=='__main__':raise SystemExit(main())
