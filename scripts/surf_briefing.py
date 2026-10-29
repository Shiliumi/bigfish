"""One bounded preparation read; no browsing, implicit outing or model call."""
from pathlib import Path
from fish_journal import SECRET,redact_text

DOCUMENTS=('INTERESTS.md','config/CURIOSITY.md','config/SURF_COMPLETE.md')
PER_FILE=24_000
TOTAL=48_000
INTRO='你是大肥鱼。这是一个可以出去逛逛的空档，不是交作业。先想今天有什么自己还惦记的东西，再决定去不去。'
OLD_STEP='1. 一次读取当前北京时间、INTERESTS.md、config/CURIOSITY.md、config/SURF_COMPLETE.md，并运行 python3 scripts/curiosity.py agenda。can_go=false 就休息，不打开浏览器、不补报告、不凑消息；短句结束。可以有出发机会却不出发。'
NEW_STEP='1. 先运行 python3 scripts/curiosity.py briefing，一次取得当前北京时间、出发条件、兴趣配置与冲浪/收尾协议。结果已有的内容不重复读取，不拼内联 Python；read_required=true 的文件用 read_file 按需读原文。can_go=false 就休息，不打开浏览器、不补报告、不凑消息；短句结束。可以有出发机会却不出发。'


def redact(root,value):
    if isinstance(value,str):return redact_text(root,SECRET.sub('[凭据已隐藏]',value))
    if isinstance(value,list):return [redact(root,item)for item in value]
    if isinstance(value,dict):return {key:redact(root,item)for key,item in value.items()}
    return value


def briefing(root,now=None):
    from curiosity import clock,agenda,state,available,recent_count,activity_settings
    root=Path(root).resolve();now=clock(now);value=state(root);allowed,reason=available(value,now,root)
    result={'can_go':allowed,'rest_reason':reason,'used_today':recent_count(value,now,root),'daily_limit':activity_settings(root)['max_outings'],'checked_at':now.isoformat()}
    if not allowed:return redact(root,result)
    status=agenda(root,now)
    if not status['can_go']:
        result.update({key:status[key]for key in ('can_go','rest_reason','used_today','daily_limit')});return redact(root,result)
    result.update(status);result['time_scope']='checked_at 只是准备时刻；出发时间以 begin 为准，页面 read_at 必须在实际阅读时采集，不估算或复用准备时间。'
    result['documents']=[];used=0
    for name in DOCUMENTS:
        path=root/name
        if path.is_symlink()or not path.resolve().is_relative_to(root)or not path.is_file():raise ValueError('准备文件缺失或路径不正确，请核对本项目文件，未开始出发。')
        size=path.stat().st_size
        if size>PER_FILE or used+size>TOTAL:
            result['documents'].append({'path':name,'read_required':True,'reason':'文件较大，未截断；请按需读取原文。'});continue
        raw=path.read_bytes()
        if len(raw)>PER_FILE or used+len(raw)>TOTAL:
            result['documents'].append({'path':name,'read_required':True,'reason':'文件读取期间变大，未截断；请按需读取原文。'});continue
        content=raw.decode('utf-8')
        result['documents'].append({'path':name,'read_required':False,'content':content});used+=len(raw)
    return redact(root,result)


def upgrade_prompt(prompt):
    if not isinstance(prompt,str):return None
    lines=prompt.splitlines(keepends=True)
    if len(lines)<2 or lines[0].rstrip('\r\n')!=INTRO:return None
    first=lines[1].rstrip('\r\n')
    if first==NEW_STEP:return prompt
    if first!=OLD_STEP or sum(line.rstrip('\r\n')==OLD_STEP for line in lines)!=1:return None
    ending=lines[1][len(first):];lines[1]=NEW_STEP+ending
    return ''.join(lines)


def inspect_jobs(jobs):
    matches=[row for row in jobs if row.get('name')=='fish-surf']
    if len(matches)>1:raise ValueError('冲浪任务重名，未修改。')
    if not matches:return None
    job=matches[0];updated=upgrade_prompt(job.get('prompt'))
    return {'id':job['id'],'prompt':job.get('prompt'),'updated':updated,'change':updated is not None and updated!=job.get('prompt')}


def apply_update(store):
    plan=inspect_jobs(store.load_jobs())
    if plan is None:return {'updated':False,'reason':'missing'}
    if not plan['change']:return {'updated':False,'reason':'custom_prompt'if plan['updated']is None else'already_current'}
    def apply(jobs,index,job):
        if job.get('name')!='fish-surf'or sum(row.get('name')=='fish-surf'for row in jobs)!=1 or job.get('prompt')!=plan['prompt']:
            raise ValueError('冲浪提示刚被修改，保留当前内容，请重新核对。')
        result=store.update_job(job['id'],{'prompt':plan['updated']})
        if not result or result.get('prompt')!=plan['updated']:raise ValueError('冲浪准备入口未保存，请核对任务。')
        return {'updated':True}
    result=store._with_job(plan['id'],apply)
    if result is None:raise ValueError('冲浪任务刚被移除，未创建替代任务。')
    return result
