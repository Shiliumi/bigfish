#!/usr/bin/env python3
"""Replay isolated SQLite opens; never read real chats or call a model."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
import tempfile
import time
from unittest.mock import patch
from fish_journal import Journal

ROOT=Path(__file__).resolve().parents[1]


def run(klass,root):
    now=datetime(2026,10,29,3,tzinfo=timezone.utc)
    with klass(root,now=now)as journal:
        for i in range(100):journal.capture('fixture-'+str(i),'虚构齿轮维修记录 '+str(i),'把铜色齿轮重新装正了。')
    durations=[];writes=[];contexts=[]
    for i in range(100):
        started=time.perf_counter()
        with klass(root,now=now)as journal:
            contexts.append(journal.recall('铜色齿轮 '+str(i)))
            writes.append(journal.db.total_changes)
        durations.append((time.perf_counter()-started)*1000)
    connect=sqlite3.connect
    with closing(connect(root/'data/memory/episodes.sqlite3'))as writer:
        writer.execute('BEGIN IMMEDIATE')
        writer.execute('UPDATE episodes SET summary=? WHERE session_id=?',('尚未提交的虚构修改。','fixture-42'))
        try:
            with patch('sqlite3.connect',side_effect=lambda path,**kwargs:connect(path,timeout=.05)):
                with klass(root,now=now)as journal:
                    readable=bool(journal.search('铜色齿轮 42'))
        except sqlite3.OperationalError:readable=False
        finally:writer.rollback()
    return {'median_ms':round(statistics.median(durations),3),'p95_ms':round(sorted(durations)[94],3),
            'writes_per_read_min':min(writes),'writes_per_read_max':max(writes),
            'read_while_another_writer_is_uncommitted':readable},contexts


def evaluate(baseline='4acf160'):
    commit=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',baseline+'^{commit}'],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='fish-open-replay-')as temporary:
        root=Path(temporary);file=root/'baseline.py'
        file.write_bytes(subprocess.check_output(['git','show',commit+':scripts/fish_journal.py'],cwd=ROOT))
        spec=importlib.util.spec_from_file_location('_journal_open_baseline',file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        before,old=run(module.Journal,root/'before');after,new=run(Journal,root/'after')
    return {'baseline':commit,'fictional_episodes':100,'opens_per_variant':100,'before':before,'after':after,
            'recall_payloads_identical':old==new,'scope':'Local synthetic microbenchmark; not app latency, model quality, or token/cost savings.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',default='4acf160');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.baseline);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='')
