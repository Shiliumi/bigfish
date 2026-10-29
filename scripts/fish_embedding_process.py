"""Optional offline encoder process client. No model imports, network or memory DB access."""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time
import uuid
from fish_embeddings import MODEL_IDENTITY,MODEL_SHA

PROTOCOL=1
MODEL_KEY=hashlib.sha256(json.dumps(MODEL_IDENTITY,sort_keys=True,separators=(',',':')).encode()).hexdigest()
MAX_INPUT=65536
MAX_OUTPUT=512000
WORKER=Path(__file__).with_name('fish_embedding_worker.py')


def inspect_runtime(home,manifest):
    home=Path(home).resolve()
    if type(manifest.get('protocol'))is not int or manifest.get('protocol')!=PROTOCOL or manifest.get('model')!=MODEL_KEY:raise ValueError('Unsupported local encoder.')
    python=manifest.get('python','');model=manifest.get('model_dir','')
    if not isinstance(python,str)or not re.fullmatch(r'generations/[a-f0-9]{32}/venv/bin/python',python)or model!='models/'+MODEL_SHA:raise ValueError('Invalid local runtime paths.')
    executable=home/python;directory=home/model
    if not executable.resolve().is_relative_to(home/'python')or not executable.is_file()or not os.access(executable,os.X_OK):raise ValueError('Interpreter must belong to this managed runtime.')
    if not directory.resolve().is_relative_to(home)or not directory.is_dir():raise ValueError('Model must belong to this runtime.')
    return executable,directory


def _exchange(command,payload,timeout):
    """Bound both pipe directions and wall time; reap the process group on failure."""
    deadline=time.monotonic()+timeout;output=bytearray();offset=0;child=None;selector=selectors.DefaultSelector();success=False
    try:
        child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,
            env={'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false','OMP_NUM_THREADS':'2'})
        os.set_blocking(child.stdin.fileno(),False);os.set_blocking(child.stdout.fileno(),False)
        selector.register(child.stdin,selectors.EVENT_WRITE);selector.register(child.stdout,selectors.EVENT_READ)
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:return None
            for key,_ in selector.select(min(remaining,.1)):
                if key.fileobj is child.stdin:
                    try:offset+=os.write(child.stdin.fileno(),payload[offset:offset+8192])
                    except BrokenPipeError:return None
                    except BlockingIOError:continue
                    if offset==len(payload):selector.unregister(child.stdin);child.stdin.close()
                else:
                    try:chunk=os.read(child.stdout.fileno(),8192)
                    except BlockingIOError:continue
                    if not chunk:selector.unregister(child.stdout);continue
                    output.extend(chunk)
                    if len(output)>MAX_OUTPUT:return None
        if child.wait(timeout=max(.001,deadline-time.monotonic()))!=0:return None
        success=True;return bytes(output)
    except (OSError,subprocess.TimeoutExpired):return None
    finally:
        selector.close()
        if child:
            if not success:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            try:child.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
            for pipe in (child.stdin,child.stdout):
                if pipe and not pipe.closed:pipe.close()


def decode_response(raw,request_id,count):
    if raw is None or len(raw)>MAX_OUTPUT:raise ValueError('Missing bounded encoder response.')
    try:value=json.loads(raw)
    except (ValueError,RecursionError)as error:raise ValueError('Invalid encoder JSON.')from error
    if not isinstance(value,dict)or set(value)!={'protocol','id','model','vectors'}or type(value['protocol'])is not int or value['protocol']!=PROTOCOL or value['id']!=request_id or value['model']!=MODEL_KEY:raise ValueError('Unexpected encoder response.')
    vectors=value['vectors']
    if not isinstance(vectors,list)or len(vectors)!=count:raise ValueError('Incomplete embeddings.')
    for vector in vectors:
        if not isinstance(vector,list)or len(vector)!=512 or any(type(v)not in (int,float)or not -1.001<=v<=1.001 for v in vector)or not .999<math.hypot(*vector)<1.001:raise ValueError('Invalid normalized embedding.')
    return vectors


def _read(path,limit=8192):
    with Path(path).open('rb')as handle:raw=handle.read(limit+1)
    if len(raw)>limit:raise ValueError('Runtime metadata too large.')
    return raw


def _failed(home,generation):
    # Only a generation and retry time persist. No query, passage, exception or model output.
    path=home/('cooldown-'+uuid.uuid4().hex+'.tmp')
    try:
        with path.open('x')as handle:os.chmod(path,0o600);json.dump({'generation':generation,'until':time.time()+60},handle)
        path.replace(home/'cooldown.json')
    except OSError:pass
    finally:path.unlink(missing_ok=True)


def encode(home,texts,*,query=False,timeout=2.0):
    """Vectors or None; caller keeps its lexical path on None. Never installs/downloads."""
    if not isinstance(texts,list)or not 1<=len(texts)<=16 or any(not isinstance(s,str)or not 1<=len(s)<=2000 for s in texts)or type(query)is not bool or type(timeout)not in (int,float)or not .05<=timeout<=30:return None
    request_id=uuid.uuid4().hex
    payload=json.dumps({'protocol':PROTOCOL,'id':request_id,'query':query,'texts':texts},ensure_ascii=False).encode()
    if len(payload)>MAX_INPUT:return None
    try:
        home=Path(home).resolve();raw=_read(home/'active.json');manifest=json.loads(raw);python,model=inspect_runtime(home,manifest)
        generation=hashlib.sha256(raw).hexdigest()
        descriptor=os.open(home/'query.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'a')as lock:
            os.fchmod(lock.fileno(),0o600)
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return None
            try:
                cooldown=json.loads(_read(home/'cooldown.json'))
                if cooldown.get('generation')==generation and type(cooldown.get('until'))in (int,float)and 0<cooldown['until']-time.time()<=60:return None
            except (OSError,ValueError,TypeError,AttributeError,RecursionError):pass
            result=_exchange([str(python),'-I',str(WORKER),str(model)],payload,timeout)
            try:return decode_response(result,request_id,len(texts))
            except (ValueError,TypeError,KeyError):_failed(home,generation);return None
    except (OSError,ValueError,TypeError,AttributeError,RecursionError):return None
