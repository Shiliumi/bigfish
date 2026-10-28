#!/usr/bin/env python3
"""Update only the conversation guide; preserve personal identity and learned traits."""
from datetime import datetime
import fcntl
import hashlib
from pathlib import Path
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
START='<!-- FISH_CONVERSATION_BEGIN -->'
END='<!-- FISH_CONVERSATION_END -->'
KNOWN_STOCK_HASH='9897fe33182fa6ce375d08b08d15187f9e4118931f943dfa922b61c3d50e024f'
REPLACEMENT='玩笑用当下的细节长出来，示例只说明节奏，不存成整句供反复调用；没梗的时候就正常接话。'


def render(original,guide):
    paragraphs=original.split('\n\n')
    paragraphs=[REPLACEMENT if hashlib.sha256(p.encode()).hexdigest()==KNOWN_STOCK_HASH else p for p in paragraphs]
    original='\n\n'.join(paragraphs)
    block=START+'\n'+guide.strip()+'\n'+END
    if START in original or END in original:
        if original.count(START)!=1 or original.count(END)!=1 or original.index(START)>original.index(END):raise ValueError('接话说明的边界标记损坏，保留原人设，未覆盖。')
        return original[:original.index(START)]+block+original[original.index(END)+len(END):]
    return original.rstrip()+'\n\n'+block+'\n'


def update(root):
    root=Path(root);soul=root/'.hermes/SOUL.md';lock=root/'data/personality/.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    if not soul.resolve().is_relative_to(root.resolve()):raise ValueError('人设文件越过本项目，未修改。')
    with lock.open('a')as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        original=soul.read_text();updated=render(original,(root/'config/CONVERSATION.md').read_text())
        if updated==original:return False
        backup=root/'backups/conversation-guide'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup.mkdir(parents=True,mode=0o700);shutil.copy2(soul,backup/'SOUL.md')
        with tempfile.NamedTemporaryFile('w',encoding='utf8',dir=soul.parent,delete=False)as file:file.write(updated);temporary=Path(file.name)
        temporary.chmod(0o600)
        if soul.read_text()!=original:
            temporary.unlink();raise ValueError('人设刚被其他操作修改，原样保留，请稍后重试。')
        temporary.replace(soul)
    return True


if __name__=='__main__':
    print('接话说明已更新并备份，个人身份与自动成长区保留；新对话加载。'if update(ROOT)else '接话说明已是最新，个人内容保留。')
