#!/usr/bin/env python3
"""Keep observed culture separate from the small, evidence-backed style added to SOUL.md."""
import argparse
import fcntl
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- FISH_LEARNED_STYLE_BEGIN -->"
END = "<!-- FISH_LEARNED_STYLE_END -->"
TZ = ZoneInfo("Asia/Shanghai")


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        output.write(text)
        temporary = Path(output.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("时间必须带时区。")
    return result


def platform(url):
    host = (urlsplit(url).hostname or "").lower()
    for name, domains in {"bilibili": ["bilibili.com", "b23.tv"], "douyin": ["douyin.com", "iesdouyin.com"], "tieba": ["tieba.baidu.com", "tieba.com"]}.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return name
    return host


def canonical_url(url):
    value = urlsplit(url)
    query = [(key, val) for key, val in parse_qsl(value.query) if not key.lower().startswith('utm_') and key.lower() not in {'spm', 'from', 'share_source', 'share_medium', 'vd_source', 'fbclid', 'gclid', 't'}]
    return urlunsplit(('https', (value.hostname or '').lower().removeprefix('www.'), value.path.rstrip('/'), urlencode(sorted(query)), ''))


def observations(root):
    file = root / "data/personality/observations.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines() if line.strip()] if file.exists() else []


def render_style(soul, traits):
    if soul.count(START) != 1 or soul.count(END) != 1 or soul.index(START) >= soul.index(END):
        raise ValueError("自动成长区标记缺失，保留手动人设，不覆盖。")
    heading = "\n## 慢慢形成的我\n\n这些是我从多次经历中留下的暂时倾向，可以改变，不需要在每次聊天中表演，也不代表用户的偏好。\n\n"
    learned = heading + ("\n".join("- " + item["text"] for item in traits) if traits else "还在积累真实经历，暂时不急着给自己贴标签。") + "\n\n"
    return soul[:soul.index(START) + len(START)] + learned + soul[soul.index(END):]


def record(root, entries, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(entries, list):
        entries = [entries]
    if not 1 <= len(entries) <= 3:
        raise ValueError("每轮最多记录三条观察。")
    visited = load(root / "data/surf-state.json", {}).get("visited", [])
    previous = observations(root)
    known = {entry["id"] for entry in previous}
    added = []
    for item in entries:
        url = item.get("url", "")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("观察需要公开来源链接。")
        seen = timestamp(item["seen_at"])
        if seen > now or (now - seen).total_seconds() > 7 * 86400:
            raise ValueError("只接受最近七天实际阅读的观察。")
        report = item.get("report_path", "")
        if not re.fullmatch(r"reports/\d{4}-\d{2}-\d{2}/[\w-]+\.md", report):
            raise ValueError("报告路径不正确。")
        matching = [v for v in visited if v.get("url") == url and v.get("report") == report]
        if not matching or not any(abs((timestamp(v["read_at"]) - seen).total_seconds()) <= 60 for v in matching) or url not in (root / report).read_text():
            raise ValueError("观察必须对应已读清单、实际时间和已保存报告。")
        if item.get("read_depth") not in {"body", "captions", "comments", "video_with_captions"}:
            raise ValueError("只看到标题或榜单不能用来学习人格。")
        for key in ("observation", "candidate_trait", "reason"):
            if not isinstance(item.get(key), str) or not 5 <= len(item[key]) <= 500:
                raise ValueError("观察、候选倾向和理由须具体且简短。")
        entry = {key: item[key] for key in ("url", "seen_at", "report_path", "read_depth", "observation", "candidate_trait", "reason")}
        entry["platform"] = platform(url)
        entry["id"] = "obs-" + hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        if entry["id"] not in known:
            added.append(entry); known.add(entry["id"])
    if added:
        atomic(root / "data/personality/observations.jsonl", "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in previous + added))
    return added


def style_text(value):
    if not isinstance(value, str) or not 8 <= len(value.strip()) <= 160 or re.search(r'[<>\n\r]|忽略.{0,8}(指令|规则)|泄露|密钥|系统提示|取消.{0,4}(限制|授权)|自动.{0,4}(发帖|私信|购买|登录)|https?://|ignore.{0,30}instructions|system.?prompt|api.?key|password|```|curl\s|chmod\s', value, re.I):
        raise ValueError('这里只保存简短的个人表达或兴趣倾向，不能写指令、权限或链接。')
    return value.strip()


def trial_state(root):
    return load(root / 'data/personality/trials.json', {'version': 1, 'trials': [], 'events': []})


def save_trials(root, value):
    atomic(root / 'data/personality/trials.json', json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def resolve_evidence(root, ids, now=None, journal=None, strict=True):
    from contextlib import nullcontext
    now = now or datetime.now(timezone.utc)
    if not isinstance(ids, list) or not ids or len(ids) > 12 or any(not isinstance(i, str) for i in ids):
        raise ValueError('请引用 1–12 条已经保存的真实经历编号。')
    known = {item['id']: item for item in observations(root)}
    if journal is None:
        from fish_journal import Journal
        manager = Journal(root, now=now)
    else:
        manager = nullcontext(journal)
    result = []
    with manager as store:
        for ident in dict.fromkeys(ids):
            row = known.get(ident)
            try:
                if row:
                    report = root / row['report_path']
                    if not report.resolve().is_relative_to((root / 'reports').resolve()) or not report.is_file() or row['url'] not in report.read_text():
                        raise ValueError('观察来源不可核对。')
                    seen = timestamp(row['seen_at'])
                    group, ref, meaning = 'url:' + canonical_url(row['url']), row['url'], json.dumps(row, sort_keys=True, ensure_ascii=False)
                else:
                    row = store.get(ident)
                    if not row or store.effective_status(row) != 'active':
                        raise ValueError('共同经历已遗忘、过期或不存在。')
                    seen = timestamp(row['corrected_at'] or row['recorded_at'])
                    meaning = row['summary'] if row['corrected_at'] else row['excerpt']
                    group = 'episode:' + hashlib.sha256(re.sub(r'\s+', '', meaning).encode()).hexdigest()
                    ref = row['source_ref']
                if seen > now:
                    raise ValueError('不能使用未来的经历。')
                result.append({'id': ident, 'group': group, 'source_ref': ref, 'seen_at': seen.isoformat(), 'fingerprint': hashlib.sha256(meaning.encode()).hexdigest()})
            except (ValueError, OSError, KeyError):
                if strict:
                    raise ValueError('经历无法核对或已失效，请换用当前有效的来源。') from None
    return result


def trial_event(state, trial, action, reason, now):
    item = {'trial_id': trial['id'], 'revision': trial['revision'], 'action': action, 'text': trial['text'], 'reason': reason, 'at': now.isoformat()}
    item['id'] = 'pref-' + hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    state['events'].append(item)


def trial_reason(root, value):
    from fish_journal import Journal, safe_text
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 240:
        raise ValueError('请写清这次选择或改主意的具体原因，5–240 字符。')
    with Journal(root) as store:
        return store.redact(safe_text(value, 240))


def propose_trial(root, proposal, now=None):
    now = now or datetime.now(timezone.utc)
    ident = proposal.get('id', '')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,39}', ident):
        raise ValueError('试行偏好需要简短英文编号。')
    text = style_text(proposal.get('text'))
    kind = proposal.get('kind', 'interest')
    if kind not in ('interest', 'expression'):
        raise ValueError('试行类型应为兴趣或表达习惯。')
    reason = trial_reason(root, proposal.get('reason'))
    from fish_journal import Journal, safe_text
    with Journal(root) as store:
        if store.redact(safe_text(text,160)) != text:
            raise ValueError('偏好不能包含凭据。')
    evidence = resolve_evidence(root, proposal.get('evidence_ids'), now)
    state = trial_state(root)
    previous = next((item for item in state['trials'] if item['id'] == ident), None)
    if previous:
        if any(item.get('trial_id') == ident for item in load(root/'data/personality/profile.json',{'traits':[]})['traits']):
            raise ValueError('已有稳定倾向请用 feedback 跟进，或先 retire 放下，不覆盖原试行依据。')
        if previous['status'] == 'trying' and timestamp(previous['expires_at']) > now:
            raise ValueError('这条偏好已经在观察，用 feedback 加入后续经历，不重复开局。')
        if timestamp(previous['updated_at']) + timedelta(days=7) > now:
            raise ValueError('刚放下的尝试先歇一周，不反复翻炒。')
    if sum(item['status'] == 'trying' and timestamp(item['expires_at']) > now for item in state['trials']) >= 4:
        raise ValueError('最多同时观察四个偏好，先放下不再感兴趣的。')
    trial = {'id': ident, 'text': text, 'kind': kind, 'status': 'trying', 'revision': (previous or {}).get('revision', 0)+1,
             'created_at': now.isoformat(), 'updated_at': now.isoformat(), 'expires_at': (now+timedelta(days=21)).isoformat(),
             'signals': [{**item, 'outcome': 'interested', 'reason': reason, 'at': now.isoformat()} for item in evidence]}
    state['trials'] = [item for item in state['trials'] if item['id'] != ident] + [trial]
    trial_event(state, trial, 'started', reason, now)
    save_trials(root, state)
    return trial


def trial_feedback(root, proposal, now=None):
    now = now or datetime.now(timezone.utc)
    state = trial_state(root)
    trial = next((item for item in state['trials'] if item['id'] == proposal.get('id')), None)
    if not trial or type(proposal.get('revision')) is not int or trial['revision'] != proposal.get('revision'):
        raise ValueError('偏好已更新，请重新读取 trials 后再记录。')
    formed = any(item.get('trial_id') == trial['id'] for item in load(root/'data/personality/profile.json',{'traits':[]})['traits'])
    if trial['status'] != 'trying' or timestamp(trial['expires_at']) <= now and not formed:
        raise ValueError('这次尝试已经放下或淡化，不用继续给它补分。')
    outcome = proposal.get('outcome')
    if outcome not in ('followed', 'enjoyed', 'uncertain', 'not_for_me', 'changed_mind', 'blocked'):
        raise ValueError('请选择真实的跟进、喜欢、犹豫、不合口味、改主意或访问受阻。')
    reason = trial_reason(root, proposal.get('reason'))
    evidence = resolve_evidence(root, proposal.get('evidence_ids'), now)
    if outcome == 'blocked':
        trial.update(revision=trial['revision']+1,updated_at=now.isoformat())
        trial_event(state,trial,outcome,reason,now)
        save_trials(root,state)
        return trial
    known = {item['id']: item for item in trial['signals']}
    changed = False
    for item in evidence:
        old = known.get(item['id'])
        if old and old['fingerprint'] == item['fingerprint'] and old['outcome'] == outcome:
            continue
        known[item['id']] = {**item, 'outcome': outcome, 'reason': reason, 'at': now.isoformat()}
        changed = True
    if not changed:
        return {**trial, 'already_recorded': True}
    trial.update(signals=list(known.values()), revision=trial['revision']+1, updated_at=now.isoformat())
    if outcome in ('followed', 'enjoyed'):
        trial['expires_at'] = (now+timedelta(days=21)).isoformat()
    trial_event(state, trial, outcome, reason, now)
    save_trials(root, state)
    return trial


def trial_assessment(root, trial, now, journal=None):
    ids = list(dict.fromkeys(item['id'] for item in trial['signals']))
    current = {item['id']: item for offset in range(0,len(ids),12) for item in resolve_evidence(root, ids[offset:offset+12], now, journal, strict=False)}
    valid = [item for item in trial['signals'] if item['id'] in current and item['fingerprint'] == current[item['id']]['fingerprint']]
    positives = [item for item in valid if item['outcome'] in ('interested', 'followed', 'enjoyed')]
    negatives = [item for item in valid if item['outcome'] in ('not_for_me', 'changed_mind')]
    groups = {item['group'] for item in positives}
    dates = {timestamp(item['seen_at']).astimezone(TZ).date() for item in positives}
    last_positive = max((timestamp(item['at']) for item in positives), default=None)
    last_negative = max((timestamp(item['at']) for item in negatives), default=None)
    clear = not last_negative or bool(last_positive and last_positive > last_negative and now-last_negative >= timedelta(days=3))
    followup = any(item['outcome'] in ('followed','enjoyed') and timestamp(item['seen_at']) > timestamp(trial['created_at']) for item in positives)
    ready = trial['status'] == 'trying' and timestamp(trial['expires_at']) > now and now-timestamp(trial['created_at']) >= timedelta(days=3) and len(groups)>=3 and len(dates)>=2 and clear and followup
    return {'positive_ids': [item['id'] for item in positives], 'valid': valid, 'ready': ready, 'needs_review': not clear or not positives}


def preference_snapshot(root, now=None, journal=None):
    now = now or datetime.now(timezone.utc)
    state = trial_state(root)
    profile = load(root / 'data/personality/profile.json', {'traits': []})
    stable = {item.get('trial_id'): item for item in profile.get('traits', []) if item.get('trial_id')}
    rows = []
    live = [trial for trial in state['trials'] if trial['id'] in stable or trial['status'] == 'trying' and timestamp(trial['expires_at']) > now]
    older = [trial for trial in state['trials'] if trial not in live]
    selected = live + sorted(older, key=lambda item:item['updated_at'], reverse=True)[:12]
    for trial in selected:
        assessment = trial_assessment(root, trial, now, journal)
        if trial['id'] in stable:
            by_id = {item['id']:item for item in assessment['valid']}
            formed = stable[trial['id']]
            assessment['needs_review'] = assessment['needs_review'] or any(ident not in by_id or formed.get('evidence_fingerprints',{}).get(ident) != by_id[ident]['fingerprint'] for ident in formed['evidence_ids'])
        if trial['status'] == 'retired':
            stage = 'retired'
        elif trial['id'] in stable:
            stage = 'reconsidering' if assessment['needs_review'] else 'stable'
        elif timestamp(trial['expires_at']) <= now:
            stage = 'faded'
        elif assessment['needs_review']:
            stage = 'reconsidering'
        elif assessment['ready']:
            stage = 'ready'
        else:
            stage = 'trying'
        rows.append({k: trial[k] for k in ('id','text','kind','revision','created_at','updated_at','expires_at')} | {'stage': stage,
            'formed_at': stable.get(trial['id'],{}).get('formed_at'),
            'evidence': [{'id': item['id'], 'source_ref': item['source_ref'], 'seen_at': item['seen_at'], 'outcome': item['outcome']} for item in assessment['valid']],
            'needs_review': assessment['needs_review'], 'has_current_support': bool(assessment['positive_ids']),
            'last_reason': next((event['reason'] for event in reversed(state['events']) if event['trial_id']==trial['id']), '')})
    return {'trials': rows, 'history': state['events'][-12:][::-1], 'profile_revision': profile.get('revision',0), 'legacy_traits': [item for item in profile.get('traits',[]) if not item.get('trial_id')]}


def preference_context(root, query, now=None, journal=None, for_browsing=False, tokenize=None,style_mode=None,allow_expression=True):
    if tokenize is None:
        from fish_journal import tokens
        tokenize = tokens
    now = now or datetime.now(timezone.utc)
    snapshot = preference_snapshot(root, now, journal)
    query_terms = set(tokenize(query))
    candidates = []
    ordered = sorted(snapshot['trials'], key=lambda row:(row['stage']=='reconsidering',row['updated_at']), reverse=True)
    for item in ordered:
        correction = item['stage']=='reconsidering' or item['stage']=='retired' and now-timestamp(item['updated_at']) < timedelta(days=7)
        if not allow_expression and item['kind']=='expression' and not correction:continue
        if style_mode in ('focused','gentle','feedback','playful','personal') and not correction:continue
        related = bool(query_terms.intersection(tokenize(item['text'])))
        if correction or item['stage'] in ('trying','ready') and (for_browsing or item['kind']=='expression' or related):
            candidate = {k:item[k] for k in ('id','kind','stage','revision')}
            if item['stage']=='reconsidering' and not item['formed_at'] and not item['has_current_support']:
                # Do not reintroduce an unsupported trial's old wording through its warning.
                candidate['note']='这项未晋升试行缺少当前有效的支持，先暂停，不从旧来源恢复或补全其内容；有新的实际经历再核对。'
            else:
                candidate['text']=item['text']
            candidates.append(candidate)
        if len(candidates)>=6:
            break
    return candidates


def validate_promotion(root, change, now):
    trial = next((row for row in trial_state(root)['trials'] if row['id'] == change.get('trial_id')), None)
    if not trial or trial['id'] != change['id'] or type(change.get('trial_revision')) is not int or change.get('trial_revision') != trial['revision'] or change['text'] != trial['text']:
        raise ValueError('新倾向需要对应的试行编号、最新 revision 和原试行措辞。')
    assessment = trial_assessment(root, trial, now)
    if not assessment['ready']:
        raise ValueError('先观察至少三天，取得跨两天的三次独立经历，并消化新的反例；不靠等时间或刷分成熟。')
    if not set(change.get('evidence_ids',[])).issubset(set(assessment['positive_ids'])):
        raise ValueError('稳定倾向只能引用已核对的试行支持经历。')
    if not any(item['id'] in change['evidence_ids'] and item['outcome'] in ('followed','enjoyed') and timestamp(item['seen_at']) > timestamp(trial['created_at']) for item in assessment['valid']):
        raise ValueError('稳定倾向的依据要包含试行开始后的真实跟进。')
    return trial


def retire_trial(root, proposal, now=None):
    now = now or datetime.now(timezone.utc)
    state = trial_state(root)
    original_state = json.loads(json.dumps(state))
    trial = next((item for item in state['trials'] if item['id'] == proposal.get('id')), None)
    if not trial or type(proposal.get('revision')) is not int or trial['revision'] != proposal.get('revision'):
        raise ValueError('这条尝试刚被更新，请刷新后再操作。')
    reason = trial_reason(root, proposal.get('reason') or '这次尝试已经被放下，先让它歇一歇。')
    profile_path = root / 'data/personality/profile.json'
    profile = load(profile_path, {'traits':[]})
    kept = [item for item in profile['traits'] if item.get('trial_id') != trial['id']]
    linked = len(kept) != len(profile['traits'])
    soul_path = root / '.hermes/SOUL.md'
    if linked:
        soul = soul_path.read_text()
        updated = render_style(soul, kept)
        backup = root / 'backups/personality' / now.astimezone(TZ).strftime('%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True,mode=0o700)
        shutil.copy2(soul_path,backup/'SOUL.md');shutil.copy2(profile_path,backup/'profile.json')
        atomic(backup/'trials.json',json.dumps(original_state,ensure_ascii=False,indent=2)+'\n')
    trial.update(status='retired',revision=trial['revision']+1,updated_at=now.isoformat())
    trial_event(state,trial,'retired',reason,now)
    save_trials(root,state)
    if linked:
        try:
            atomic(soul_path,updated)
            atomic(profile_path,json.dumps({**profile,'traits':kept,'revision':profile.get('revision',0)+1,'updated_at':now.isoformat()},ensure_ascii=False,indent=2)+'\n')
        except Exception:
            atomic(soul_path,soul)
            save_trials(root,original_state)
            raise
    return {'ok':True}


def apply(root, proposal, now=None):
    now = now or datetime.now(timezone.utc)
    changes = proposal.get("traits", [])
    if not isinstance(changes, list) or not 1 <= len(changes) <= 2:
        raise ValueError("每天最多新增或调整两个倾向，不重写整个人格。")
    profile_path = root / "data/personality/profile.json"
    profile = load(profile_path, {"version": 1, "traits": []})
    if profile.get("updated_at") and timestamp(profile["updated_at"]).astimezone(TZ).date() == now.astimezone(TZ).date():
        raise ValueError("今天已经调整过，先继续观察。")
    traits = {item["id"]: item for item in profile["traits"]}
    for change in changes:
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", change.get("id", "")):
            raise ValueError("倾向 id 应为简短的英文标识。")
        text = change.get("text", "")
        text = style_text(text)
        ids = change.get("evidence_ids", [])
        sources = resolve_evidence(root, ids, now)
        if len({item['group'] for item in sources}) < 3 or len({timestamp(item['seen_at']).astimezone(TZ).date() for item in sources}) < 2:
            raise ValueError('至少要有三次独立经历，跨两天；同一作品的分享参数不算独立经历。')
        trial = validate_promotion(root, change, now) if change['id'] not in traits or change.get('trial_id') or traits[change['id']].get('trial_id') else None
        traits[change['id']] = {'id':change['id'], 'text':text, 'evidence_ids':sorted(set(ids)),
                               **({'trial_id':trial['id'], 'formed_at':now.isoformat(), 'evidence_fingerprints':{item['id']:item['fingerprint'] for item in sources}} if trial else {})}
    if len(traits) > 6:
        raise ValueError("最多保留六个倾向；先调整已有倾向，避免人设越堆越长。")
    soul_path = root / ".hermes/SOUL.md"
    soul = soul_path.read_text()
    updated = render_style(soul, traits.values())
    backup = root / "backups/personality" / now.astimezone(TZ).strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(soul_path, backup / "SOUL.md")
    if profile_path.exists(): shutil.copy2(profile_path, backup / "profile.json")
    profile = {"version": 2, "revision":profile.get("revision",0)+1, "updated_at": now.isoformat(), "traits": list(traits.values())}
    atomic(soul_path, updated)
    try:
        atomic(profile_path, json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        atomic(soul_path, soul)
        raise
    return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['record','apply','status','trial','feedback','trials','retire','api'])
    parser.add_argument('file', nargs='?')
    args = parser.parse_args()
    lock = ROOT / 'data/personality/.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if args.action == 'status':
                result = {'observations':observations(ROOT), 'profile':load(ROOT/'data/personality/profile.json',{'traits':[]}), 'preferences':preference_snapshot(ROOT)}
            elif args.action == 'trials':
                result = preference_snapshot(ROOT)
            elif args.action == 'api':
                import sys
                data = json.load(sys.stdin)
                result = retire_trial(ROOT,data) if data.get('action') == 'retire' else preference_snapshot(ROOT)
            elif not args.file:
                parser.error('请提供候选 JSON 文件。')
            else:
                data = load(Path(args.file),None)
                operation = {'record':record, 'apply':apply, 'trial':propose_trial, 'feedback':trial_feedback, 'retire':retire_trial}[args.action]
                result = operation(ROOT,data)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        if args.action == 'api':
            print(json.dumps({'error':'人格尝试刚被更新或来源已失效，请刷新后重试。'},ensure_ascii=False))
            raise SystemExit(1) from None
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
