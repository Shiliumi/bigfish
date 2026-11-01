"""Exact local core-memory backups returned by the existing review command."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

FILES=('MEMORY.md','USER.md')
MAX_BYTES=512_000


def pair(root):
    result={}
    for name in FILES:
        path=root/'.hermes/memories'/name
        if not path.resolve().is_relative_to(root):raise ValueError('核心记忆路径越过项目，未备份。')
        if not path.exists():result[name]=None;continue
        if not path.is_file()or path.stat().st_size>MAX_BYTES:raise ValueError('核心记忆文件无法完整备份，未截断。')
        value=path.read_bytes()
        if len(value)>MAX_BYTES:raise ValueError('核心记忆读取期间变大，未截断。')
        result[name]=value
    return result


def fingerprint(values):
    return {name:hashlib.sha256(value).hexdigest()if value is not None else None for name,value in values.items()}


def validate(root,path,expected):
    if not path.resolve().is_relative_to(root)or path.is_symlink():raise ValueError('核心记忆备份路径无效。')
    manifest=path/'manifest.json'
    if manifest.is_symlink():raise ValueError('核心记忆备份清单无效。')
    data=json.loads(manifest.read_text())
    if data.get('version')!=1 or data.get('files')!=expected:raise ValueError('已有核心记忆备份与指纹不符，未覆盖。')
    for name,sha in expected.items():
        file=path/name
        if file.is_symlink()or not file.resolve().is_relative_to(root):raise ValueError('核心记忆备份文件路径无效。')
        if sha is None:
            if file.exists():raise ValueError('原本缺失的核心记忆出现备份内容，未覆盖。')
        elif not file.is_file()or file.stat().st_size>MAX_BYTES or hashlib.sha256(file.read_bytes()).hexdigest()!=sha:
            raise ValueError('已有核心记忆备份损坏，未覆盖。')
    return {'path':str(path.relative_to(root)),'files':expected,'created_at':data['created_at']}


def capture(root,snapshot_id):
    root=Path(root).resolve()
    if not isinstance(snapshot_id,str)or not re.fullmatch(r'[a-f0-9]{64}',snapshot_id):raise ValueError('核心记忆备份需要有效快照编号。')
    parent=root/'backups/memory-review'/snapshot_id
    if not parent.resolve().is_relative_to(root):raise ValueError('核心记忆备份目录越过项目。')
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    for _ in range(3):
        values=pair(root);expected=fingerprint(values)
        image=hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest();path=parent/image
        if path.exists():
            result=validate(root,path,expected)
        else:
            with tempfile.TemporaryDirectory(prefix='.preparing-',dir=parent)as folder:
                staged=Path(folder)
                for name,value in values.items():
                    if value is not None:
                        file=staged/name;file.write_bytes(value);file.chmod(0o600)
                manifest=staged/'manifest.json'
                manifest.write_text(json.dumps({'version':1,'files':expected,'created_at':datetime.now(timezone.utc).isoformat()}))
                manifest.chmod(0o600)
                if pair(root)!=values:continue
                try:staged.rename(path)
                except OSError:
                    if not path.exists():raise
                result=validate(root,path,expected)
        if pair(root)==values:return result
    raise ValueError('核心记忆正在变化，本次未确认备份；请稍后重试 review。')
