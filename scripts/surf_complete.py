#!/usr/bin/env python3
"""Validate and durably submit one real outing in a single local operation."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
import curiosity
import personality

ROOT=Path(__file__).resolve().parents[1]
MUTABLE=('data/surf-state.json','data/personality/observations.jsonl','data/curiosity/state.json','data/personality/trials.json')
READ_ONLY=('.hermes/SOUL.md','data/personality/profile.json')


def digest(value):return hashlib.sha256(value).hexdigest() if value is not None else None


def safe_path(root,name):
    if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('收尾路径无效。')
    path=root/name
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('收尾路径越过了项目目录。')
    return path


def read_bytes(root,name):
    path=safe_path(root,name)
    return path.read_bytes() if path.exists() else None


def write_bytes(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('wb',dir=path.parent,delete=False) as stream:
        stream.write(value);stream.flush();__import__('os').fsync(stream.fileno());tmp=Path(stream.name)
    tmp.chmod(0o600);tmp.replace(path)
    descriptor=__import__('os').open(path.parent,__import__('os').O_RDONLY)
    try:__import__('os').fsync(descriptor)
    finally:__import__('os').close(descriptor)


def apply_plan(root,receipt,path):
    # Check ALL preimages before writing anything. A crash may have already applied a prefix.
    for row in receipt['writes']:
        current=digest(read_bytes(root,row['path']))
        if current not in (row['before'],digest(row['content'].encode())):
            raise ValueError('未完成收尾的来源已被其他操作改变，停止覆盖；请检查本机收尾记录。')
    for row in receipt['reads']:
        if digest(read_bytes(root,row['path']))!=row['before']:raise ValueError('收尾期间人设依据发生变化，请先检查未完成记录。')
    for row in receipt['writes']:
        write_bytes(safe_path(root,row['path']),row['content'].encode())
    receipt['status']='committed'
    # Completed receipts keep hashes and resulting ids, not another complete copy of memory text.
    receipt['writes']=[{'path':r['path'],'sha256':digest(r['content'].encode())}for r in receipt['writes']]
    write_bytes(path,json.dumps(receipt,ensure_ascii=False,indent=2).encode())
    return receipt['result']


def validate_page(page,run,now,report):
    if not isinstance(page,dict):raise ValueError('已读页面格式无效。')
    url=page.get('url','');parts=urlsplit(url)
    if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or len(url)>2000:raise ValueError('已读页面需要公开来源链接。')
    if not isinstance(page.get('read_at'),str):raise ValueError('已读时间需要带时区的真实时间。')
    seen=personality.timestamp(page['read_at'])
    if seen>now+timedelta(seconds=60) or seen<personality.timestamp(run['started_at'])-timedelta(minutes=2):raise ValueError('已读页面必须来自本次真实出发。')
    if url not in report:raise ValueError('报告需要包含本次实际读到的来源链接。')
    title=curiosity.text(page.get('title'),'页面标题',1,200)
    return {'url':url,'title':title,'read_at':seen.isoformat()}


def complete(root,data,now=None):
    now=curiosity.clock(now)
    if not isinstance(data,dict) or len(json.dumps(data,ensure_ascii=False).encode())>180_000:raise ValueError('请提交有限的本轮收尾 JSON。')
    ident=data.get('run_id','')
    if not re.fullmatch(r'browse-[a-f0-9]{16}',ident):raise ValueError('请使用 begin 返回的真实出发编号。')
    token=digest(json.dumps(data,ensure_ascii=False,sort_keys=True).encode())
    folder=root/'data/surf-completions';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with ExitStack() as stack:
        # Same locks as the individual tools, so a normal CLI write cannot interleave the commit.
        for relative in ('data/curiosity/.lock','data/personality/.lock'):
            file=safe_path(root,relative);file.parent.mkdir(parents=True,exist_ok=True)
            handle=stack.enter_context(file.open('a'));fcntl.flock(handle,fcntl.LOCK_EX)
        path=folder/(ident+'.json')
        previous=curiosity.load(path,None)
        if previous:
            if previous['payload_hash']!=token:raise ValueError('同一出发编号已提交不同内容，不能覆盖。')
            return {**(previous['result'] if previous['status']=='committed' else apply_plan(root,previous,path)),'already_submitted':True}
        # Recover an interrupted commit before accepting new writes to the same stores.
        for pending in sorted(folder.glob('browse-*.json')):
            receipt=curiosity.load(pending,{})
            if receipt.get('status')=='prepared':apply_plan(root,receipt,pending)
        state=curiosity.state(root);run=next((r for r in state['runs']if r['id']==ident),None)
        if not run or run['status']!='started':raise ValueError('这轮尚未开始或已由其他入口完成。')
        report=data.get('report',{})
        if not isinstance(report,dict):raise ValueError('请提供本轮报告对象。')
        name=report.get('path','');content=report.get('content','')
        if not re.fullmatch(r'reports/\d{4}-\d{2}-\d{2}/[\w-]*surf[\w-]*\.md',name) or not isinstance(content,str) or not 20<=len(content)<=40_000:raise ValueError('请提供本轮探索报告路径和有限的真实阅读记录。')
        if name.split('/')[1]!=personality.timestamp(run['started_at']).astimezone(curiosity.TZ).date().isoformat():raise ValueError('报告日期应为本轮出发日期。')
        if read_bytes(root,name) is not None:raise ValueError('该报告已经存在，请使用新的本轮文件名，不覆盖旧笔记。')
        pages=data.get('pages',[]);obs=data.get('observations',[]);threads=data.get('threads',[]);preference=data.get('preference')
        if not isinstance(pages,list) or len(pages)>5 or not isinstance(obs,list) or len(obs)>3 or not isinstance(threads,list) or len(threads)>3:raise ValueError('每轮最多五页、三条观察和三个未完问题。')
        if any(not isinstance(item,dict)for item in obs+threads):raise ValueError('观察与未完问题需要 JSON 对象。')
        pages=[validate_page(p,run,now,content)for p in pages]
        if len({p['url']for p in pages})!=len(pages):raise ValueError('同一已读页面不重复登记。')
        if not pages and data.get('outcome')!='blocked':raise ValueError('没有实际读到内容只能记录受阻，不制造发现。')
        before={n:read_bytes(root,n)for n in MUTABLE+READ_ONLY}
        with tempfile.TemporaryDirectory(prefix='fish-surf-',dir=folder) as temporary:
            staged=Path(temporary)
            for n,value in before.items():
                if value is not None:write_bytes(staged/n,value)
            write_bytes(staged/name,content.encode())
            surf=curiosity.load(staged/'data/surf-state.json',{'visited':[]})
            surf['visited']+=[{**p,'report':name}for p in pages]
            curiosity.atomic(staged/'data/surf-state.json',surf)
            entries=[]
            for o in obs:
                index=o.get('page_index')
                if type(index) is not int or not 0<=index<len(pages):raise ValueError('观察必须引用本轮的实际已读页面序号。')
                p=pages[index]
                entries.append({**{k:o.get(k)for k in ('read_depth','observation','candidate_trait','reason')},'url':p['url'],'seen_at':p['read_at'],'report_path':name})
            added=personality.record(staged,entries,now) if entries else []
            def refs(item):
                indexes=item.get('evidence_observations')
                if not isinstance(indexes,list) or not indexes or any(type(i) is not int or not 0<=i<len(added)for i in indexes):raise ValueError('请用本次观察序号引用依据，不编写 obs-id。')
                return [added[i]['id']for i in dict.fromkeys(indexes)]
            remembered=[]
            if threads:
                remembered=curiosity.remember(staged,[{**t,'evidence_ids':refs(t)}for t in threads],now)
            trial=None
            if preference is not None:
                if not isinstance(preference,dict) or preference.get('action') not in ('trial','feedback'):raise ValueError('本轮可选一项真实试行或跟进反馈。')
                proposal={**preference,'evidence_ids':refs(preference)}
                trial=(personality.propose_trial if preference['action']=='trial' else personality.trial_feedback)(staged,proposal,now)
            finished=curiosity.finish(staged,{'run_id':ident,'outcome':data.get('outcome'),'reason':data.get('reason'),'report_path':name,'evidence_ids':[a['id']for a in added]},now)
            share=data.get('share');outbox=None
            if share is not None:
                if not isinstance(share,dict) or type(share.get('page_index')) is not int or not 0<=share['page_index']<len(pages):raise ValueError('来信只能引用本轮实际阅读的页面。')
                p=pages[share['page_index']]
                letter={'worth_sharing':True,'text':curiosity.text(share.get('text'),'想说的话',8,320),'why_share':curiosity.text(share.get('why_share'),'分享理由',6,240),
                    'source_url':p['url'],'source_title':p['title'],'report_path':name,'created_at':now.isoformat()}
                if share.get('sticker_id'):
                    if not re.fullmatch(r'[a-f0-9]{16}',share['sticker_id']):raise ValueError('表情编号无效。')
                    letter['sticker_id']=share['sticker_id']
                outbox='data/outbox/'+ident+'.json'
                if read_bytes(root,outbox) is not None:raise ValueError('本轮来信候选已存在，未覆盖。')
                curiosity.atomic(staged/outbox,letter)
            result={'ok':True,'run_id':ident,'outcome':finished['outcome'],'report_path':name,'observation_ids':[a['id']for a in added],
                'thread_ids':[t['id']for t in remembered],'preference_id':trial['id'] if trial else None,'share_queued':bool(outbox)}
            order=[name,*MUTABLE]+([outbox]if outbox else [])
            writes=[{'path':n,'before':digest(before.get(n)),'content':(staged/n).read_text()}for n in order if (staged/n).exists() and (staged/n).read_bytes()!=before.get(n)]
            receipt={'version':1,'status':'prepared','payload_hash':token,'writes':writes,'reads':[{'path':n,'before':digest(before[n])}for n in READ_ONLY], 'result':result}
            write_bytes(path,json.dumps(receipt,ensure_ascii=False,indent=2).encode())
        return apply_plan(root,receipt,path)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('file',type=Path);args=parser.parse_args()
    try:print(json.dumps(complete(ROOT,json.loads(args.file.read_text())),ensure_ascii=False))
    except (ValueError,TypeError,KeyError,OSError) as error:raise SystemExit(str(error)) from None


if __name__=='__main__':main()
