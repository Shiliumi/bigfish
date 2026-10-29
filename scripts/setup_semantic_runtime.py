#!/usr/bin/env python3
"""Explicit optional runtime setup. Activates only after a real offline encoder check."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
from fish_embeddings import MODEL_SHA,TOKENIZER_SHA,REVISION,artifact_hash
from fish_embedding_process import PROTOCOL,MODEL_KEY,WORKER,_exchange,decode_response,inspect_runtime

ROOT=Path(__file__).resolve().parents[1]
PYTHON_VERSION='3.12.14'
LOCK=ROOT/'tests/requirements-semantic.lock'
FILES={'model_optimized.onnx':(MODEL_SHA,100_000_000),'tokenizer.json':(TOKENIZER_SHA,10_000_000)}


def valid_file(path,digest):
    try:return artifact_hash(path)==digest
    except OSError:return False


def model_files(home,source=None):
    directory=home/'models'/MODEL_SHA
    if not directory.resolve().is_relative_to(home):raise ValueError('Model destination must stay inside this runtime.')
    directory.mkdir(parents=True,exist_ok=True)
    for name,(digest,limit)in FILES.items():
        target=directory/name
        if target.is_symlink():raise ValueError('Model destination cannot be an external link.')
        if valid_file(target,digest):continue
        with tempfile.NamedTemporaryFile(dir=directory,delete=False)as handle:temporary=Path(handle.name)
        try:
            if source:
                origin=Path(source)/name
                if not valid_file(origin,digest):raise ValueError('Local model artifacts do not match the pinned hashes.')
                shutil.copyfile(origin,temporary)
            else:
                url=f'https://huggingface.co/Qdrant/bge-small-zh-v1.5/resolve/{REVISION}/{name}'
                with urllib.request.urlopen(url,timeout=30)as response,temporary.open('wb')as handle:
                    size=0
                    while chunk:=response.read(1024*1024):
                        size+=len(chunk)
                        if size>limit:raise ValueError('Model download exceeds its size limit.')
                        handle.write(chunk)
            if not valid_file(temporary,digest):raise ValueError('Model artifact checksum mismatch.')
            temporary.chmod(0o600);temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
    return directory


def health(home,manifest):
    python,model=inspect_runtime(home,manifest);ident=uuid.uuid4().hex
    data=json.dumps({'protocol':PROTOCOL,'id':ident,'query':True,'texts':['临时演示：纸风车有四片叶子。']}).encode()
    decoded=decode_response(_exchange([str(python),'-I',str(WORKER),str(model)],data,20),ident,1)
    return bool(decoded)


def install(home,uv,source=None):
    home=Path(home).resolve();home.mkdir(parents=True,exist_ok=True,mode=0o700);home.chmod(0o700)
    if any(not(home/name).resolve().is_relative_to(home)for name in ['models','python','downloads','generations']):raise ValueError('Runtime directories must stay inside the project runtime.')
    recipe=hashlib.sha256(LOCK.read_bytes()+PYTHON_VERSION.encode()+MODEL_KEY.encode()).hexdigest()
    env={key:value for key,value in os.environ.items()if not key.startswith(('UV_','PIP_','PYTHON'))and key!='VIRTUAL_ENV'}
    env.update({'UV_PYTHON_INSTALL_DIR':str(home/'python'),'UV_PYTHON_INSTALL_BIN':'0',
                'UV_CACHE_DIR':str(home/'downloads'),'UV_NO_CONFIG':'1','UV_PYTHON_PREFERENCE':'only-managed'})
    with (home/'setup.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        active=home/'active.json'
        if active.exists():
            try:
                current=json.loads(active.read_text())
                if current.get('recipe')==recipe and health(home,current):
                    (home/'cooldown.json').unlink(missing_ok=True);return False
            except (ValueError,OSError,TypeError,AttributeError,RecursionError):pass
        # Existing active generation is left intact until all new checks pass.
        model_files(home,source)
        subprocess.run([str(uv),'python','install',PYTHON_VERSION,'--no-bin'],env=env,check=True)
        generation=home/'generations'/uuid.uuid4().hex;generation.mkdir(parents=True,mode=0o700)
        try:
            subprocess.run([str(uv),'venv','--python',PYTHON_VERSION,str(generation/'venv')],env=env,check=True)
            python=generation/'venv/bin/python'
            subprocess.run([str(uv),'pip','sync','--python',str(python),'--require-hashes','--only-binary=:all:',
                            '--index-url','https://pypi.org/simple',str(LOCK)],env=env,check=True)
            manifest={'protocol':PROTOCOL,'model':MODEL_KEY,'recipe':recipe,'python':str(python.relative_to(home)),
                      'model_dir':'models/'+MODEL_SHA}
            if not health(home,manifest):raise ValueError('Offline encoder health check failed.')
            with tempfile.NamedTemporaryFile('w',dir=home,delete=False)as handle:
                temporary=Path(handle.name);json.dump(manifest,handle,indent=2);handle.flush();os.fsync(handle.fileno())
            temporary.chmod(0o600);temporary.replace(active)
            (home/'cooldown.json').unlink(missing_ok=True)
        except BaseException:
            # A cancellation immediately after the atomic swap must not remove its active target.
            try:published=json.loads(active.read_text()).get('python')==str((generation/'venv/bin/python').relative_to(home))
            except (OSError,ValueError,AttributeError,RecursionError):published=False
            if not published:shutil.rmtree(generation)
            raise
    return True


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uv',type=Path);parser.add_argument('--model-dir',type=Path)
    args=parser.parse_args();uv=args.uv or shutil.which('uv')or ROOT/'.runtime/semantic-tools/bin/uv'
    if not Path(uv).is_file():parser.error('Install uv first, or provide --uv /path/to/uv. See docs/semantic-runtime.md.')
    home=(ROOT/'.runtime/semantic').resolve()
    if not home.is_relative_to(ROOT):parser.error('Runtime directory must stay inside this project.')
    changed=install(home,Path(uv).resolve(),args.model_dir)
    print('Optional local encoder runtime ready; chat recall remains unchanged.'if changed else 'Optional local encoder runtime already passes its offline check.')
