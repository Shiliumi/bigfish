#!/usr/bin/env python3
"""Small, evidence-backed threads of curiosity; separate from permanent personality."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import re
from pathlib import Path
import tempfile
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Shanghai')
DAILY_LIMIT = 3


def activity_settings(root):
    value = load(root / 'data/automation/settings.json', {'paused': False, 'max_outings': DAILY_LIMIT})
    if not isinstance(value, dict) or not isinstance(value.get('paused', False), bool) or type(value.get('max_outings', DAILY_LIMIT)) is not int or not 1 <= value.get('max_outings', DAILY_LIMIT) <= DAILY_LIMIT:
        raise ValueError('后台活动设置损坏，请在鱼粮账本中重新保存。')
    return {'paused': value.get('paused', False), 'max_outings': value.get('max_outings', DAILY_LIMIT)}


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def clock(now=None):
    return (now or datetime.now(TZ)).astimezone(TZ)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf8', dir=path.parent, delete=False) as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')
        temporary = Path(output.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def state(root):
    return load(root / 'data/curiosity/state.json', {'version': 1, 'threads': [], 'runs': []})


def observations(root):
    path = root / 'data/personality/observations.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def recent_count(value, now, root):
    counted = {run.get('report_path') for run in value['runs']}
    earlier = sum(1 for p in (root / 'reports' / now.strftime('%Y-%m-%d')).glob('*surf*.md') if str(p.relative_to(root)) not in counted)
    return earlier + sum(1 for run in value['runs'] if datetime.fromisoformat(run['started_at']).astimezone(TZ).date() == now.date())


def available(value, now, root):
    runs = value['runs']
    settings = activity_settings(root)
    if settings['paused']:
        return False, '后台省粮暂停中，聊天仍可使用。'
    if not 9 <= now.hour < 22:
        return False, '现在是安静时间。'
    if recent_count(value, now, root) >= settings['max_outings']:
        return False, '今天的出发额度已经用完，先消化一下。'
    if runs and now - datetime.fromisoformat(runs[-1]['started_at']) < timedelta(hours=2):
        return False, '刚逛回来，先歇一会儿。'
    from surf_lifecycle import prepared_receipts
    if prepared_receipts(root):
        return False, '上次收尾等待本地恢复，先不开始新一轮。'
    return True, ''


def reading_followups(root,value,now):
    """Completed reading, rather than failed attempts, informs revisit fatigue."""
    from fish_conversation import public_url
    root=Path(root).resolve();report_root=(root/'reports').resolve()
    if not report_root.is_relative_to(root):return {}
    visited=load(root/'data/surf-state.json',{'visited':[]}).get('visited',[])
    by_report={};reports={};result={};counted=set()
    for page in visited:
        if isinstance(page,dict)and isinstance(page.get('report'),str):by_report.setdefault(page['report'],[]).append(page)
    def at(value):
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('Reading time needs a timezone.')
        return parsed
    for run in value['runs']:
        if run.get('status')!='finished'or run.get('outcome')not in ('want_more','satisfied','bored')or not run.get('thread_id'):continue
        try:
            ident=run['id']
            if not isinstance(ident,str)or ident in counted:continue
            start=at(run['started_at']);end=at(run['finished_at']);name=run['report_path']
            if not start<=end<=now or not isinstance(name,str)or Path(name).is_absolute():continue
            file=(root/name).resolve()
            if not file.is_relative_to(report_root)or not file.is_file()or file.stat().st_size>512_000:continue
            if name not in reports:reports[name]=file.read_text()
            times=[]
            for page in by_report.get(name,[]):
                try:
                    seen=at(page['read_at'])
                    if public_url(page.get('url'))and page['url']in reports[name]and start-timedelta(minutes=2)<=seen<=end+timedelta(seconds=60)and seen<=now:times.append(seen)
                except (ValueError,TypeError,KeyError,AttributeError):continue
            if not times:continue
            latest=max(times);row=result.setdefault(run['thread_id'],{'read_visits':0,'last_read_at':latest})
            row['read_visits']+=1;row['last_read_at']=max(row['last_read_at'],latest);counted.add(ident)
        except (ValueError,TypeError,KeyError,OSError,AttributeError):continue
    return result


def agenda(root, now=None):
    now = clock(now)
    value = state(root)
    allowed, reason = available(value, now, root)
    from fish_conversation import verified_threads,recent_material,interest_material
    try:valid={v['id']for v in verified_threads(root,now)}
    except (ValueError,TypeError,KeyError,OSError):valid=set()
    candidates = [v for v in value['threads'] if v['id']in valid and v['status'] == 'open' and datetime.fromisoformat(v['expires_at']) > now and (not v.get('snoozed_until') or datetime.fromisoformat(v['snoozed_until']) <= now)]
    history=reading_followups(root,value,now)
    candidates=[{**item,'read_visits':history.get(item['id'],{}).get('read_visits',0),
                 'last_read_at':history[item['id']]['last_read_at'].isoformat()if item['id']in history else None}for item in candidates]
    def score(item):
        age = min(7, max(0,(now - datetime.fromisoformat(item['last_read_at'] or item['created_at'])).total_seconds() / 86400))
        return item['interest'] * 2 + age - item['read_visits'] * .35
    candidates.sort(key=score, reverse=True)
    # These are quotations from real observations, not user preferences or fixed identity.
    evidence = recent_material(root,now)
    from personality import preference_context
    preferences = preference_context(root, '', now=now, for_browsing=True)
    continuity = interest_material(root,now=now,for_browsing=True)
    return {'can_go': allowed, 'rest_reason': reason, 'used_today': recent_count(value, now, root), 'daily_limit': activity_settings(root)['max_outings'],
            'trial_preferences': preferences,
            'continuity':continuity,
            'threads': candidates[:3], 'recent_observations': [{k: row.get(k) for k in ('id', 'url', 'observation', 'candidate_trait', 'reason')} for row in evidence],
            'choice': '先想自己还想知道什么。可以追一个问题，也可以从一个新入口随便看看；不想逛就休息，不必交三条发现。'}


def text(value, name, minimum=4, maximum=220):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f'{name}需要 {minimum}–{maximum} 个字符。')
    return value.strip()


def evidence_for(root, ids):
    known = {item['id']: item for item in observations(root)}
    if not isinstance(ids, list) or not 1 <= len(ids) <= 5 or any(not isinstance(i, str) or i not in known for i in ids):
        raise ValueError('好奇线索需要 1–5 条已经核对的观察 id，不能只凭热榜标题。')
    return [known[i] for i in ids]


def remember(root, entries, now=None):
    now = clock(now)
    value = state(root)
    if not isinstance(entries, list): entries = [entries]
    if not 1 <= len(entries) <= 3: raise ValueError('一次最多留下三个问题。')
    updated = []
    for item in entries:
        if not isinstance(item, dict): raise ValueError('请提供好奇问题 JSON 对象。')
        question = text(item.get('question'), '想继续看的问题', 6, 160)
        why = text(item.get('why'), '我为什么在意', 6, 220)
        evidence = evidence_for(root, item.get('evidence_ids'))
        ident = item.get('id') or 'cur-' + hashlib.sha256(question.encode()).hexdigest()[:12]
        if not isinstance(ident, str) or not re.fullmatch(r'cur-[a-f0-9]{12}', ident): raise ValueError('问题编号无效。')
        existing = next((v for v in value['threads'] if v['id'] == ident), None)
        from fish_interest import load_controls, blocked
        if blocked(load_controls(root),ident,[v['url']for v in evidence],now):
            raise ValueError('这个问题或来源已被用户暂停或放下，保留阅读记录，先换个方向。')
        if existing and existing['status'] == 'closed' and datetime.fromisoformat(existing['updated_at']) + timedelta(days=7) > now:
            raise ValueError('刚失去兴趣的话题先放一周，不要反复翻炒。')
        row = {**(existing or {}), 'id': ident, 'question': question, 'why': why, 'evidence_ids': [v['id'] for v in evidence], 'source_urls': list(dict.fromkeys(v['url'] for v in evidence)),
               'status': 'open', 'interest': max(1, min(3, int(item.get('interest', 2)))), 'visits': (existing or {}).get('visits', 0),
               'created_at': (existing or {}).get('created_at', now.isoformat()), 'updated_at': now.isoformat(), 'expires_at': (now + timedelta(days=21)).isoformat()}
        if existing: value['threads'][value['threads'].index(existing)] = row
        else: value['threads'].append(row)
        updated.append(row)
    if len([v for v in value['threads'] if v['status'] == 'open']) > 8: raise ValueError('最多保留八个未完的问题，先放下不感兴趣的。')
    value['threads'] = value['threads'][-40:]
    atomic(root / 'data/curiosity/state.json', value)
    return updated


def begin(root, thread_id=None, now=None):
    now = clock(now)
    value = state(root)
    allowed, reason = available(value, now, root)
    if not allowed: return {'started': False, 'reason': reason}
    thread = next((v for v in agenda(root, now)['threads'] if v['id'] == thread_id), None) if thread_id else None
    if thread_id and not thread: raise ValueError('这条线索已经冷却或不在当前候选里，请重新看 agenda。')
    run = {'id': 'browse-' + uuid4().hex[:16], 'started_at': now.isoformat(), 'thread_id': thread_id, 'status': 'started', 'question': thread['question'] if thread else '这次随便看看，遇到喜欢的再留下问题'}
    from surf_lifecycle import current_owner
    owner=current_owner(root,now)
    if owner:run['cron_execution']=owner
    value['runs'].append(run); value['runs'] = value['runs'][-128:]
    if thread:
        original = next(v for v in value['threads'] if v['id'] == thread_id)
        original['last_followed_at'] = now.isoformat(); original['visits'] += 1
    atomic(root / 'data/curiosity/state.json', value)
    return {'started': True, 'run': run}


def finish(root, data, now=None):
    if not isinstance(data, dict): raise ValueError('请提供本轮结束记录 JSON 对象。')
    now = clock(now)
    value = state(root)
    run = next((v for v in value['runs'] if v['id'] == data.get('run_id')), None)
    if not run or run['status'] != 'started': raise ValueError('这轮尚未开始或已经结束。')
    outcome = data.get('outcome')
    if outcome not in ('want_more', 'satisfied', 'bored', 'blocked'): raise ValueError('结束原因应为 want_more / satisfied / bored / blocked。')
    reason = text(data.get('reason'), '这次的感受', 6, 220)
    report = root / str(data.get('report_path', ''))
    if not report.is_file() or not report.resolve().is_relative_to((root / 'reports').resolve()): raise ValueError('需要这次真实保存的探索报告。')
    evidence = evidence_for(root, data.get('evidence_ids')) if outcome == 'want_more' else []
    if evidence and any(datetime.fromisoformat(v['seen_at']) < datetime.fromisoformat(run['started_at']) - timedelta(minutes=2) for v in evidence): raise ValueError('不能用出发前的旧观察冒充本轮收获。')
    if evidence and any(v.get('report_path') != str(report.relative_to(root)) for v in evidence): raise ValueError('继续追看的理由要有本轮的新观察，不能重复用旧证据。')
    run.update(status='finished', outcome=outcome, reason=reason, report_path=str(report.relative_to(root)), finished_at=now.isoformat())
    thread = next((v for v in value['threads'] if v['id'] == run['thread_id']), None)
    if thread:
        thread.update(last_outcome=outcome, last_reason=reason, updated_at=now.isoformat())
        if outcome == 'want_more':
            thread['interest'] = min(3, thread['interest'] + 1)
            thread['source_urls'] = list(dict.fromkeys(thread['source_urls'] + [v['url'] for v in evidence]))[-8:]
            thread['evidence_ids'] = list(dict.fromkeys(thread['evidence_ids'] + [v['id'] for v in evidence]))[-8:]
        if outcome == 'satisfied': thread['snoozed_until'] = (now + timedelta(days=2)).isoformat()
        if outcome == 'blocked': thread['snoozed_until'] = (now + timedelta(hours=8)).isoformat()
        if outcome == 'bored': thread['status'] = 'closed'
    atomic(root / 'data/curiosity/state.json', value)
    return run


@contextmanager
def locked(root):
    directory = root / 'data/curiosity'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('agenda'); sub.add_parser('status');sub.add_parser('briefing')
    sub.add_parser('reconcile').add_argument('--legacy',action='store_true')
    sub.add_parser('remember').add_argument('file', type=Path)
    sub.add_parser('begin').add_argument('--thread')
    sub.add_parser('finish').add_argument('file', type=Path)
    args = parser.parse_args()
    if args.command=='reconcile':
        from surf_lifecycle import reconcile
        print(json.dumps(reconcile(ROOT,clock(),legacy=args.legacy),ensure_ascii=False));return
    with locked(ROOT):
        if args.command=='briefing':
            from surf_briefing import briefing
            result=briefing(ROOT)
        elif args.command in ('agenda', 'status'): result = agenda(ROOT)
        elif args.command == 'begin': result = begin(ROOT, args.thread)
        elif args.command == 'remember': result = remember(ROOT, load(args.file, None))
        else: result = finish(ROOT, load(args.file, None))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try: main()
    except (ValueError, TypeError, KeyError, OSError) as error: raise SystemExit(str(error))
