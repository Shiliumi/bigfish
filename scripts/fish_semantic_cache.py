"""Experimental derived vectors in source SQLite, with transactional invalidation; no model imports."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
import sqlite3
import struct
if __package__:
    from .fish_journal import instant,SCHEMA_VERSION
else:
    from fish_journal import instant,SCHEMA_VERSION

PIPELINE={'version':1,'window':280,'stride':220,'normalization':'l2-f32-le'}
CACHE_SCHEMA=2
SOURCE_FIELDS=('id','session_id','source_ref','recorded_at','summary','excerpt','status','revision','pinned',
               'valid_from','valid_until','corrected_at','correction_source','kind','aliases')
OBJECTS={
    'fish_semantic_episode_update':('CREATE TRIGGER fish_semantic_episode_update AFTER UPDATE OF '+','.join(SOURCE_FIELDS)+
        ' ON episodes WHEN '+' OR '.join('OLD.'+name+' IS NOT NEW.'+name for name in SOURCE_FIELDS)+
        ' BEGIN DELETE FROM fish_semantic_vectors WHERE episode_id=OLD.id OR episode_id=NEW.id; END'),
    'fish_semantic_episode_delete':'CREATE TRIGGER fish_semantic_episode_delete AFTER DELETE ON episodes BEGIN DELETE FROM fish_semantic_vectors WHERE episode_id=OLD.id; END',
    'fish_semantic_source':'CREATE INDEX fish_semantic_source ON fish_semantic_vectors(episode_id)',
}


@dataclass(frozen=True)
class EncodingJob:
    home: str
    model: str
    ident: str
    revision: int
    fingerprint: str
    texts: tuple


def meaning(row):return row['summary']if row['corrected_at']else row['excerpt']


def fingerprint(row):
    values={key:row[key]for key in ('id','revision','recorded_at','source_ref','kind','valid_from','valid_until','corrected_at','correction_source')}
    values.update(body=meaning(row),aliases=json.loads(row['aliases']))
    return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def live(row,now):
    try:return row['status']=='active'and instant(row['valid_from'])<=now and(not row['valid_until']or instant(row['valid_until'])>now)
    except (ValueError,TypeError):return False


def cache_schema(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fish_semantic_meta'").fetchone():return None
    row=db.execute("SELECT value FROM fish_semantic_meta WHERE key='schema'").fetchone()
    if not row:raise ValueError('Cache schema marker missing; source untouched.')
    return row[0]


def discard_cache(journal):
    """Remove only this optional derived schema, atomically; never delete a database file."""
    db=journal.db
    if db.in_transaction:raise ValueError('Finish the caller transaction before discarding derived data.')
    if db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION:raise ValueError('Primary journal schema is incompatible; left unchanged.')
    with db:
        db.execute('BEGIN IMMEDIATE');version=cache_schema(db)
        if db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION:raise ValueError('Primary journal schema is incompatible; left unchanged.')
        if version is None:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('fish_semantic_vectors','fish_semantic_episode_update','fish_semantic_episode_delete','fish_semantic_source')").fetchone():raise ValueError('Derived schema has no ownership marker; left unchanged.')
            return False
        if version!=str(CACHE_SCHEMA):raise ValueError('Cache schema is newer or incompatible; left unchanged.')
        for name,sql in OBJECTS.items():db.execute('DROP '+('INDEX'if sql.startswith('CREATE INDEX')else 'TRIGGER')+' IF EXISTS '+name)
        db.execute('DROP TABLE IF EXISTS fish_semantic_vectors');db.execute('DROP TABLE fish_semantic_meta')
    return True


class SemanticCache:
    def __init__(self,journal,identity,*,timeout=5):
        self.timeout=timeout
        self.root=Path(journal.root).resolve();directory=self.root/'data/memory'
        self.source=directory/'episodes.sqlite3';legacy=directory/'semantic-cache.sqlite3'
        if not directory.resolve().is_relative_to(self.root)or not self.source.resolve().is_relative_to(directory.resolve()):raise ValueError('Cache must stay in its own memory directory.')
        # Old experiments used a separate file. Never silently retain, migrate or unlink it.
        if legacy.exists()or legacy.is_symlink():raise ValueError('Legacy experimental cache requires explicit removal; source untouched.')
        self.file_identity=(self.source.stat().st_dev,self.source.stat().st_ino)
        self.home=hashlib.sha256((str(self.source.resolve())+repr(self.file_identity)).encode()).hexdigest()
        self.dimension=identity.get('dimension')
        if type(self.dimension)is not int or not 1<=self.dimension<=4096:raise ValueError('Embedding dimension invalid.')
        for key in ('weight_sha256','tokenizer_sha256'):
            value=identity.get(key)
            if not isinstance(value,str)or len(value)!=64 or any(c not in '0123456789abcdef'for c in value):raise ValueError('Public model artifact hashes required.')
        if not identity.get('repo')or not identity.get('revision')or not identity.get('pooling')or 'query_instruction'not in identity:raise ValueError('Complete model identity required.')
        self.model=hashlib.sha256(json.dumps({'identity':identity,'pipeline':PIPELINE},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.metadata={'schema':str(CACHE_SCHEMA),'home':self.home,'model':self.model}
        self.db=sqlite3.connect(self.source.resolve().as_uri()+'?mode=rw',uri=True,timeout=timeout);self.db.row_factory=sqlite3.Row
        try:
            if self.db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION:raise ValueError('Primary journal schema is incompatible; left unchanged.')
            version=self._schema()
            if version not in (None,str(CACHE_SCHEMA)):raise ValueError('Cache schema is newer or incompatible; left unchanged.')
            if version and self._owns()and self._objects_ready():return
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                # Recheck after waiting for another initializer; never downgrade its schema.
                if self.db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION:raise ValueError('Primary journal schema is incompatible; left unchanged.')
                if self._schema()not in (None,str(CACHE_SCHEMA)):raise ValueError('Cache schema is newer or incompatible; left unchanged.')
                if self._schema()and self._owns()and self._objects_ready():return
                if not set(SOURCE_FIELDS).issubset({r['name']for r in self.db.execute('PRAGMA table_info(episodes)')}):raise ValueError('Source columns incomplete; left unchanged.')
                self.db.execute('CREATE TABLE IF NOT EXISTS fish_semantic_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                self.db.execute('CREATE TABLE IF NOT EXISTS fish_semantic_vectors(model TEXT NOT NULL,episode_id TEXT NOT NULL,revision INTEGER NOT NULL,fingerprint TEXT NOT NULL,chunk_no INTEGER NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(model,episode_id,chunk_no))')
                self.db.execute('DELETE FROM fish_semantic_vectors');self.db.execute('DELETE FROM fish_semantic_meta')
                self.db.executemany('INSERT INTO fish_semantic_meta VALUES(?,?)',self.metadata.items())
                for name,sql in OBJECTS.items():
                    self.db.execute('DROP '+('INDEX'if sql.startswith('CREATE INDEX')else 'TRIGGER')+' IF EXISTS '+name)
                    self.db.execute(sql)
        except BaseException:self.db.close();raise

    def __enter__(self):return self
    def __exit__(self,*args):self.db.close()

    def _schema(self):
        return cache_schema(self.db)

    def _objects_ready(self):
        found={r['name']:r['sql']for r in self.db.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('fish_semantic_episode_update','fish_semantic_episode_delete','fish_semantic_source')")}
        return found==OBJECTS

    def _owns(self):
        try:
            status=self.source.stat()
            if (status.st_dev,status.st_ino)!=self.file_identity:return False
            return dict(self.db.execute('SELECT key,value FROM fish_semantic_meta'))==self.metadata
        except (OSError,sqlite3.OperationalError):return False

    def _sources(self,now):
        if not self._owns():return {}
        # A fresh read-only connection avoids a caller's old or uncommitted transaction snapshot.
        with closing(sqlite3.connect(self.source.resolve().as_uri()+'?mode=ro',uri=True,timeout=self.timeout))as db:
            db.row_factory=sqlite3.Row
            return {r['id']:dict(r)for r in db.execute("SELECT * FROM episodes WHERE status='active'")if live(r,now)}

    def _matches(self,job,row):
        return row is not None and row['revision']==job.revision and fingerprint(row)==job.fingerprint

    def _remove(self,ident,revision,stamp,model=None):
        self.db.execute('DELETE FROM fish_semantic_vectors WHERE model=? AND episode_id=? AND revision=? AND fingerprint=?',(model or self.model,ident,revision,stamp))

    def prune(self,now=None):
        if not self._owns():return
        now=instant(now or datetime.now(timezone.utc));sources=self._sources(now)
        stale=[]
        for row in self.db.execute('SELECT DISTINCT episode_id,revision,fingerprint FROM fish_semantic_vectors WHERE model=?',(self.model,)):
            source=sources.get(row['episode_id'])
            if not source or source['revision']!=row['revision']or fingerprint(source)!=row['fingerprint']:stale.append(row)
        if not stale:return
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if not self._owns():return
            for row in stale:self._remove(row['episode_id'],row['revision'],row['fingerprint'])

    def prepare(self,now=None,limit=64,only_ids=None):
        if not self._owns():return []
        now=instant(now or datetime.now(timezone.utc));self.prune(now);sources=self._sources(now);jobs=[]
        cached={r['episode_id']:(r['revision'],r['fingerprint'],r['count'])for r in self.db.execute('SELECT episode_id,revision,fingerprint,COUNT(*) count FROM fish_semantic_vectors WHERE model=? GROUP BY episode_id,revision,fingerprint',(self.model,))}
        for row in sources.values():
            if only_ids is not None and row['id']not in only_ids:continue
            body=meaning(row);aliases='\n'.join(json.loads(row['aliases']))
            texts=tuple(body[i:i+PIPELINE['window']]+('\n'+aliases if aliases else '')for i in range(0,len(body),PIPELINE['stride']))
            stamp=fingerprint(row)
            if texts and cached.get(row['id'])!=(row['revision'],stamp,len(texts)):
                jobs.append(EncodingJob(self.home,self.model,row['id'],row['revision'],stamp,texts))
            if len(jobs)>=max(1,min(128,limit)):break
        return jobs

    def covered(self,idents,now=None):
        """No confident margin from a corpus whose eligible sources are only partly encoded."""
        if not self._owns():return False
        now=instant(now or datetime.now(timezone.utc));sources=self._sources(now)
        groups={r['episode_id']:dict(r)for r in self.db.execute('SELECT episode_id,revision,fingerprint,COUNT(*) n,MIN(chunk_no) lo,MAX(chunk_no) hi,SUM(length(vector)!=?) malformed FROM fish_semantic_vectors WHERE model=? GROUP BY episode_id,revision,fingerprint',(self.dimension*4,self.model))}
        for ident in idents:
            source=sources.get(ident);row=groups.get(ident)
            if not source or not row or source['revision']!=row['revision']or fingerprint(source)!=row['fingerprint']:return False
            size=len(range(0,len(meaning(source)),PIPELINE['stride']))
            if row['n']!=size or row['lo']!=0 or row['hi']!=size-1 or row['malformed']:return False
        return self._owns()

    def _vector(self,values):
        values=list(values)
        if len(values)!=self.dimension or any(isinstance(v,bool)or not isinstance(v,Real)or not math.isfinite(v)for v in values):raise ValueError('Embedding must have the configured finite numeric dimensions.')
        norm=math.hypot(*values)
        if not norm or not math.isfinite(norm):raise ValueError('Embedding norm invalid.')
        return tuple(float(v)/norm for v in values)

    def publish(self,job,vectors,now=None):
        now=instant(now or datetime.now(timezone.utc))
        if job.home!=self.home or job.model!=self.model or not self._owns():return False
        source=self._sources(now).get(job.ident)
        if not self._matches(job,source):return False
        aliases='\n'.join(json.loads(source['aliases']));body=meaning(source)
        texts=tuple(body[i:i+PIPELINE['window']]+('\n'+aliases if aliases else '')for i in range(0,len(body),PIPELINE['stride']))
        if job.texts!=texts:return False
        vectors=[self._vector(v)for v in vectors]
        if len(vectors)!=len(texts):raise ValueError('Embedding count does not cover the complete source.')
        packed=[struct.pack('<'+'f'*self.dimension,*v)for v in vectors]
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if not self._owns()or not self._matches(job,self._sources(now).get(job.ident)):return False
            self.db.execute('DELETE FROM fish_semantic_vectors WHERE model=? AND episode_id=?',(self.model,job.ident))
            self.db.executemany('INSERT INTO fish_semantic_vectors VALUES(?,?,?,?,?,?)',[(self.model,job.ident,job.revision,job.fingerprint,i,data)for i,data in enumerate(packed)])
        if not self._matches(job,self._sources(now).get(job.ident)):
            with self.db:self._remove(job.ident,job.revision,job.fingerprint)
            return False
        return True

    def rank(self,vector,now=None,limit=5,exclude_session='',allowed_ids=None):
        if not self._owns():return []
        now=instant(now or datetime.now(timezone.utc));query=self._vector(vector);self.prune(now);sources=self._sources(now);scores={};corrupt=[]
        for row in self.db.execute('SELECT * FROM fish_semantic_vectors WHERE model=?',(self.model,)):
            source=sources.get(row['episode_id'])
            if not source or source['session_id']==exclude_session or source['revision']!=row['revision']or fingerprint(source)!=row['fingerprint']:continue
            if allowed_ids is not None and row['episode_id']not in allowed_ids:continue
            try:values=struct.unpack('<'+'f'*self.dimension,row['vector']);values=self._vector(values)
            except (ValueError,struct.error):corrupt.append(dict(row));continue
            score=sum(a*b for a,b in zip(query,values));ident=row['episode_id']
            if ident not in scores or score>scores[ident]['score']:
                scores[ident]={'id':ident,'revision':row['revision'],'fingerprint':row['fingerprint'],'model':self.model,'home':self.home,'score':score}
        if corrupt:
            with self.db:
                for row in corrupt:self.db.execute('DELETE FROM fish_semantic_vectors WHERE model=? AND episode_id=? AND chunk_no=? AND revision=? AND fingerprint=? AND vector=?',(self.model,row['episode_id'],row['chunk_no'],row['revision'],row['fingerprint'],row['vector']))
        return sorted(scores.values(),key=lambda r:(-r['score'],r['id']))[:max(1,min(10,limit))]if self._owns()else []

    def resolve(self,candidates,now=None):
        if not self._owns():return []
        now=instant(now or datetime.now(timezone.utc));self.prune(now);sources=self._sources(now);result=[]
        for candidate in candidates[:10]:
            if candidate.get('home')!=self.home or candidate.get('model')!=self.model:continue
            row=sources.get(candidate.get('id'))
            if not row or row['revision']!=candidate.get('revision')or fingerprint(row)!=candidate.get('fingerprint'):continue
            result.append({key:row[key]for key in ('id','revision','source_ref','recorded_at','corrected_at','correction_source','valid_until')}|{'excerpt':meaning(row)})
        return result if self._owns()else []
