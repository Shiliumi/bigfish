#!/usr/bin/env python3
"""Private request ledger and atomic daily cron token allowance. No prompts or keys."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Shanghai')
DEFAULT_LIMIT = 2_000_000
OUTPUT_CAP = 8192
BUCKETS = ('input_tokens','cache_read_tokens','cache_write_tokens','output_tokens')


def record_cron_owner(root,session,identity):
    """Bridge trusted in-process cron identity to the matching tool subprocess, without text."""
    if not isinstance(session,str)or not session or not identity or getattr(identity,'job_name',None)!='fish-surf':return
    values={key:getattr(identity,key,None)for key in ('job_id','execution_id')}
    if any(not isinstance(value,str)or not 1<=len(value)<=200 for value in values.values()):return
    import tempfile
    root=Path(root).resolve();folder=root/'data/curiosity/owners'
    if not folder.resolve().is_relative_to(root):raise ValueError('Cron owner metadata escaped project.')
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile('w',encoding='utf8',dir=folder,delete=False)as stream:
        json.dump(values,stream);temporary=Path(stream.name)
    temporary.chmod(0o600);temporary.replace(folder/(hashlib.sha256(session.encode()).hexdigest()+'.json'))


class Budget:
    def __init__(self, root, now=None):
        self.root = Path(root)
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.day = self.now.astimezone(TZ).date().isoformat()
        directory = self.root/'data/automation'
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        path = directory/'requests.sqlite3'
        self.db = sqlite3.connect(path,timeout=10)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS allowance(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL,daily_tokens INTEGER NOT NULL,revision INTEGER NOT NULL,activated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests(
                id TEXT PRIMARY KEY,day TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,
                source TEXT NOT NULL,task TEXT NOT NULL,model TEXT NOT NULL,session_hash TEXT,
                status TEXT NOT NULL,reserved INTEGER NOT NULL,charged INTEGER NOT NULL,
                input_tokens INTEGER,cache_read_tokens INTEGER,cache_write_tokens INTEGER,output_tokens INTEGER,
                duration_ms INTEGER,error INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS request_day ON requests(day,source);
        ''')
        with self.db:
            # New installations meter immediately, but opt into limits only after the plugin is installed.
            self.db.execute('INSERT OR IGNORE INTO allowance VALUES(1,0,?,1,?)',(DEFAULT_LIMIT,self.now.isoformat()))

    def __enter__(self): return self
    def __exit__(self,*args): self.db.close()

    @contextmanager
    def transaction(self):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            # A lost process is unknown, never free. Later real usage may still replace this estimate.
            self.db.execute("UPDATE requests SET status='unknown' WHERE status='reserved' AND started_at<?",((self.now-timedelta(minutes=20)).isoformat(),))
            yield

    def settings(self):
        row = dict(self.db.execute('SELECT * FROM allowance WHERE id=1').fetchone())
        row.pop('id');row['enabled']=bool(row['enabled'])
        return row

    def save(self,data):
        if not isinstance(data,dict) or type(data.get('enabled')) is not bool or type(data.get('daily_tokens')) is not int or not 10_000<=data['daily_tokens']<=200_000_000 or type(data.get('revision')) is not int:
            raise ValueError('请填写 1 万至 2 亿的每日后台 token 额度，并刷新设置版本。')
        with self.transaction():
            if data['revision']!=self.settings()['revision']:raise ValueError('后台额度已变化，请刷新后重试。')
            self.db.execute('UPDATE allowance SET enabled=?,daily_tokens=?,revision=revision+1 WHERE id=1',(int(data['enabled']),data['daily_tokens']))
        return self.settings()

    def used(self):
        return self.db.execute("SELECT COALESCE(SUM(charged),0) FROM requests WHERE day=? AND source='background'",(self.day,)).fetchone()[0]

    def reserve(self,ident,estimate,*,source='background',task='main',model='',session='',enforce=True):
        if not isinstance(ident,str) or not 1<=len(ident)<=300 or type(estimate) is not int or estimate<0:raise ValueError('请求预留无效。')
        source = source if source in ('background','chat','unassigned') else 'unassigned'
        import re
        task=task if isinstance(task,str) and re.fullmatch(r'[a-zA-Z0-9:_-]{1,60}',task) else 'other'
        # These purposes are background work even when triggered by a human conversation.
        if task in ('aux:background_review','aux:title_generation'):source='background'
        with self.transaction():
            old = self.db.execute('SELECT * FROM requests WHERE id=?',(ident,)).fetchone()
            if old:
                # A request identity is single-use; duplicate callbacks must not reach the provider again.
                return {'allowed':False,'reason':'这次请求已经预留或结算，未重复发送。','duplicate':True}
            settings=self.settings()
            if source=='background' and enforce and settings['enabled'] and self.used()+estimate>settings['daily_tokens']:
                self.db.execute('INSERT INTO requests(id,day,started_at,source,task,model,session_hash,status,reserved,charged) VALUES(?,?,?,?,?,?,?,?,0,0)',
                    (ident,self.day,self.now.isoformat(),source,str(task)[:60],safe_model(model),hashed(session),'blocked'))
                return {'allowed':False,'reason':'今日后台鱼粮不足以预留下一次请求，先休息；聊天仍可使用。'}
            self.db.execute('INSERT INTO requests(id,day,started_at,source,task,model,session_hash,status,reserved,charged) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (ident,self.day,self.now.isoformat(),source,str(task)[:60],safe_model(model),hashed(session),'reserved',estimate,estimate))
        return {'allowed':True,'id':ident,'reserved':estimate}

    def settle(self,ident,usage=None,*,error=False,duration=None):
        values=canonical(usage)
        with self.transaction():
            row=self.db.execute('SELECT * FROM requests WHERE id=?',(ident,)).fetchone()
            if not row or row['status']=='blocked':return
            if row['status']=='actual':return
            actual=values is not None
            buckets=values or [None]*4
            self.db.execute('UPDATE requests SET ended_at=?,status=?,charged=?,input_tokens=?,cache_read_tokens=?,cache_write_tokens=?,output_tokens=?,duration_ms=?,error=? WHERE id=?',
                (self.now.isoformat(),'actual' if actual else 'unknown',sum(values) if actual else row['reserved'],*buckets,
                 max(0,int(duration*1000)) if isinstance(duration,(int,float)) else None,int(bool(error)),ident))

    def snapshot(self):
        with self.transaction(): pass
        rows=[dict(r) for r in self.db.execute('SELECT source,task,status,COUNT(*) calls,SUM(charged) charged,SUM(input_tokens) input_tokens,SUM(cache_read_tokens) cache_read_tokens,SUM(cache_write_tokens) cache_write_tokens,SUM(output_tokens) output_tokens FROM requests WHERE day=? GROUP BY source,task,status',(self.day,))]
        used=self.used();settings=self.settings()
        return {'day':self.day,'settings':settings,'used':used,'remaining':max(0,settings['daily_tokens']-used),
            'reserved':sum(r['charged'] for r in rows if r['source']=='background' and r['status']=='reserved'),
            'unknown':sum(r['charged'] for r in rows if r['source']=='background' and r['status']=='unknown'),
            'blocked':sum(r['calls'] for r in rows if r['status']=='blocked'), 'groups':rows}


def hashed(value): return hashlib.sha256(str(value).encode()).hexdigest()[:20] if value else None


def safe_model(value):
    import re
    value=str(value)
    return value[:100] if re.fullmatch(r'[\w./:@+-]{1,100}',value) and not re.search(r'(?:sk-|ghp_|github_pat_|https?:)',value) else 'configured-model'


def canonical(usage):
    if not isinstance(usage,dict):return None
    # Hooks supply canonical non-overlapping buckets, not provider prompt_tokens.
    values=[usage.get(k) for k in BUCKETS]
    return values if all(type(v) is int and v>=0 for v in values) else None


def estimate_request(request):
    # UTF-8 bytes are a deliberately conservative text-token estimate; never count cache as free.
    return len(json.dumps(request,ensure_ascii=False,default=lambda _: '<opaque>').encode())+512


def prepare(request,remaining=None,api_mode='chat_completions'):
    request=dict(request)
    key=next((k for k in ('max_completion_tokens','max_tokens','max_output_tokens') if k in request),None)
    key=key or ('max_output_tokens' if api_mode=='codex_responses' else 'max_tokens')
    raw=request.get(key)
    cap=min(raw,OUTPUT_CAP) if type(raw) is int and raw>0 else OUTPUT_CAP
    minimum=min(256,cap)
    estimate=estimate_request(request)
    if remaining is not None:cap=min(cap,max(0,remaining-estimate))
    if cap<minimum:return None,estimate+minimum
    request[key]=cap
    return request,estimate_request(request)+cap


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['api','status']);args=parser.parse_args()
    try:
        with Budget(ROOT) as ledger:
            data=json.load(sys.stdin) if args.command=='api' else {}
            result=ledger.save(data) if data.get('action')=='settings' else ledger.snapshot()
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,TypeError,OSError,sqlite3.Error):
        print(json.dumps({'error':'后台额度暂时无法读取或版本已变化，请刷新后重试。'},ensure_ascii=False));raise SystemExit(1) from None


if __name__=='__main__':main()
