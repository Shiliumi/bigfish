"""Bind outings to local cron audit evidence; never infer completion from elapsed time."""
from contextlib import closing
from datetime import datetime
import json
import hashlib
import os
import re
from pathlib import Path
import sqlite3

TERMINAL={'completed','failed','unknown'}


def stamp(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Execution times need a timezone.')
    return result


def audit(root):
    root=Path(root).resolve();home=root/'.hermes'
    jobs=home/'cron/jobs.json';database=home/'cron/executions.db'
    if not jobs.is_file()or not database.is_file():return None,[]
    if not jobs.resolve().is_relative_to(home)or not database.resolve().is_relative_to(home):raise ValueError('Cron audit source escaped this project.')
    document=json.loads(jobs.read_text())
    if not isinstance(document,dict)or not isinstance(document.get('jobs'),list)or any(not isinstance(row,dict)for row in document['jobs']):raise ValueError('Invalid cron job source.')
    rows=document['jobs'];matches=[row['id']for row in rows if row.get('name')=='fish-surf']
    if len(matches)!=1:return None,[]
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1))as db:
        db.row_factory=sqlite3.Row
        rows=[dict(row)for row in db.execute('SELECT id,job_id,status,claimed_at,started_at,finished_at FROM executions WHERE job_id=? ORDER BY claimed_at DESC LIMIT 1000',(matches[0],))]
    return matches[0],rows


def current_owner(root,now):
    # Hermes injects this scope freshly into each terminal command; manual CLI runs stay unbound.
    if os.environ.get('HERMES_CRON_SESSION','').lower()not in ('1','true','yes'):return None
    try:
        session=os.environ.get('HERMES_SESSION_ID','')
        if not session:return None
        folder=Path(root).resolve()/'data/curiosity/owners';file=folder/(hashlib.sha256(session.encode()).hexdigest()+'.json')
        if not file.is_file()or not file.resolve().is_relative_to(folder)or file.stat().st_size>4096:return None
        owner=json.loads(file.read_text())
        if not isinstance(owner,dict):return None
        job,rows=audit(root)
        if owner.get('job_id')!=job:return None
        candidates=[row for row in rows if row['id']==owner.get('execution_id')and row['status']=='running'and not row['finished_at']and stamp(row['started_at']or row['claimed_at'])<=now]
        if len(candidates)!=1:return None
        return {'job_id':job,'execution_id':candidates[0]['id']}
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):return None


def prepared_receipts(root):
    root=Path(root).resolve();folder=root/'data/surf-completions';result=[]
    if not folder.resolve().is_relative_to(root):raise ValueError('Surf receipts escaped this project.')
    for path in sorted(folder.glob('browse-*.json')):
        if not path.resolve().is_relative_to(folder.resolve())or path.stat().st_size>2_000_000:raise ValueError('Invalid surf receipt source.')
        row=json.loads(path.read_text())
        if not isinstance(row,dict):raise ValueError('Invalid surf receipt.')
        if row.get('status')=='prepared':result.append((path,row))
    return result


def reconcile(root,now,*,legacy=False):
    import curiosity
    root=Path(root).resolve()
    with curiosity.locked(root):
        # A prepared transaction may contain the next state image; recover it before any edits.
        if prepared_receipts(root):raise ValueError('Pending surf commit must be recovered first.')
        job,rows=audit(root);value=curiosity.state(root);changed=0;unresolved=0
        for run in value['runs']:
            if run['status']!='started':continue
            if not re.fullmatch(r'browse-[a-f0-9]{16}',run['id']):raise ValueError('Invalid outing identity.')
            receipt=root/'data/surf-completions'/(run['id']+'.json')
            if receipt.exists():unresolved+=1;continue
            start=stamp(run['started_at']);owner=run.get('cron_execution');candidates=[]
            if isinstance(owner,dict)and owner.get('job_id')==job:
                candidates=[row for row in rows if row['id']==owner.get('execution_id')]
            elif legacy and not owner and not any(row['status']not in TERMINAL for row in rows):
                # Explicit operator repair only. A time-window match is weaker than a bound owner.
                candidates=[row for row in rows if row['finished_at']and stamp(row['started_at']or row['claimed_at'])<=start<=stamp(row['finished_at'])]
            if len(candidates)!=1:unresolved+=1;continue
            source=candidates[0]
            if source['status']not in TERMINAL or not source['finished_at']:unresolved+=1;continue
            end=stamp(source['finished_at'])
            if not stamp(source['started_at']or source['claimed_at'])<=start<=end<=now:unresolved+=1;continue
            run.update(status='interrupted',outcome=None,reason='上次执行已结束，但没有收到完整收尾；保留已保存的内容。',
                       reconciled_at=now.isoformat(),execution_finished_at=end.isoformat(),execution_status=source['status'],
                       cron_execution={'job_id':job,'execution_id':source['id']},owner_evidence='bound'if owner else'legacy_time_window')
            changed+=1
        if changed:curiosity.atomic(root/'data/curiosity/state.json',value)
        return {'interrupted':changed,'unresolved':unresolved}
