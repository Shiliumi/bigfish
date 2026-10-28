#!/usr/bin/env python3
"""Hermes wake gate and checkpointed, bounded incremental memory reviews. No LLM."""
import argparse
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
from pathlib import Path
import re
import tempfile
from contextlib import contextmanager
from zoneinfo import ZoneInfo
import curiosity

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Asia/Shanghai')
BATCH = 12


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf8', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        temporary = Path(stream.name)
    temporary.chmod(0o600)
    temporary.replace(path)


@contextmanager
def lock(root):
    directory = root / 'data/automation'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    reports = {}
    for day in sorted((root / 'reports').glob('????-??-??')):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day.name) or day.is_symlink():
            continue
        for path in sorted(day.glob('*surf*.md')):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 512000:
                reports[str(path.relative_to(root))] = checksum(path)
    path = root / 'data/personality/observations.jsonl'
    observations = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                observations[row['id']] = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    from fish_journal import Journal
    with Journal(root) as journal:
        episodes = journal.revisions()
    from personality import trial_state
    events = trial_state(root)['events']
    preferences = {row['id']: hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest() for row in events}
    return {'reports': reports, 'observations': observations, 'episodes': episodes, 'preference_events': preferences}


def pending(root):
    cursor = read(root / 'data/automation/review-cursor.json', {})
    current = inventory(root)
    selected = {kind: dict(list((key, value) for key, value in rows.items() if cursor.get(kind, {}).get(key) != value)[:BATCH]) for kind, rows in current.items()}
    if not any(selected.values()):
        return None
    ident = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    return {'id': ident, 'selected': selected, 'remaining': {kind: sum(cursor.get(kind, {}).get(key) != value for key, value in rows.items()) for kind, rows in current.items()}}


def evaluate(root, mode, now=None, persist=True):
    now = now or datetime.now(TZ)
    state_path = root / 'data/automation/gates.json'
    state = read(state_path, {})
    decision = {'wakeAgent': False, 'reason': '', 'checked_at': now.isoformat()}
    settings = curiosity.activity_settings(root)
    previous = state.get(mode, {})
    if settings['paused']:
        decision['reason'] = '后台省粮暂停中，聊天仍可使用。'
    elif previous.get('lease_until') and datetime.fromisoformat(previous['lease_until']) > now:
        decision['reason'] = '本轮机会已唤醒，等待完成或租约到期。'
    elif mode == 'surf':
        status = curiosity.agenda(root, now)
        decision.update(wakeAgent=status['can_go'], reason=status['rest_reason'] or '还有出发额度，可以选择想看的内容。')
        decision['context'] = {'used_today': status['used_today'], 'daily_limit': status['daily_limit']}
    else:
        batch = pending(root)
        if batch:
            decision.update(wakeAgent=True, reason='有尚未整理的新经历。', context={'snapshot_id': batch['id'], 'counts': {k: len(v) for k, v in batch['selected'].items()}, 'remaining': batch['remaining']})
            if persist:
                write(root / f"data/automation/reviews/{batch['id']}.json", batch)
        else:
            decision['reason'] = '没有尚未整理的新内容，本次不调用模型。'
    if decision['wakeAgent']:
        from fish_budget import Budget
        with Budget(root,now=now) as ledger: budget=ledger.snapshot()
        if budget['settings']['enabled'] and budget['remaining']<10_000:
            decision.update(wakeAgent=False,reason='今日后台鱼粮不足以再出发，等明天或调整额度；聊天仍可使用。')
    if persist:
        decision['lease_until'] = (now + timedelta(minutes=20)).isoformat() if decision['wakeAgent'] else previous.get('lease_until')
        decision['skipped_ticks'] = previous.get('skipped_ticks', 0) + int(not decision['wakeAgent'])
        write(state_path, {**state, mode: decision})
    return decision


def snapshot(root, ident):
    if not re.fullmatch(r'[a-f0-9]{64}', ident or ''):
        raise ValueError('整理快照编号无效。')
    value = read(root / f'data/automation/reviews/{ident}.json', None)
    if not value or value.get('id') != ident:
        raise ValueError('没有找到这个整理快照。')
    return value


def review(root, ident):
    from personality import trial_state
    value = snapshot(root, ident)
    observations = curiosity.observations(root)
    from fish_journal import Journal
    with Journal(root) as journal:
        episodes = [journal.get(key) for key in value['selected']['episodes']]
    return {'snapshot_id': ident, 'reports': list(value['selected']['reports']), 'observations': [row for row in observations if row['id'] in value['selected']['observations']],
            'episodes': [{'id': row['id'], 'recorded_at': row['recorded_at'], 'summary': row['summary'], 'source_ref': row['source_ref']} for row in episodes if row and row['status'] == 'active'],
            'preference_events': [row for row in trial_state(root)['events'] if row['id'] in value['selected'].get('preference_events',{})], 'remaining': value['remaining']}


def commit(root, ident, report):
    value = snapshot(root, ident)
    if value.get('committed_at'):
        return {'ok': True, 'already_committed': True}
    candidate = Path(report)
    path = (root / candidate).resolve()
    if candidate.is_absolute() or not re.fullmatch(r'reports/\d{4}-\d{2}-\d{2}/memory-review-[a-f0-9]{12}\.md', report) or not path.is_relative_to((root / 'reports').resolve()) or not path.is_file():
        raise ValueError('请先保存带快照编号的记忆整理报告。')
    if f'Review-Snapshot: {ident}' not in path.read_text():
        raise ValueError('整理报告未包含本次 Review-Snapshot 标记。')
    current = inventory(root)
    if any(current[kind].get(key) != version for kind, rows in value['selected'].items() for key, version in rows.items()):
        raise ValueError('整理期间来源发生变化，请取得新快照后重试；游标未推进。')
    cursor = read(root / 'data/automation/review-cursor.json', {})
    for kind, rows in value['selected'].items():
        cursor[kind] = {**cursor.get(kind, {}), **rows}
    cursor['updated_at'] = datetime.now(TZ).isoformat()
    write(root / 'data/automation/review-cursor.json', cursor)
    # Cursor first: a crash can repeat a checkpoint but cannot lose unprocessed sources.
    write(root / f'data/automation/reviews/{ident}.json', {**value, 'committed_at': cursor['updated_at']})
    gates = read(root / 'data/automation/gates.json', {})
    if gates.get('memory', {}).get('context', {}).get('snapshot_id') == ident:
        gates['memory'].update(lease_until=None, reason='本批增量整理已保存。')
        write(root / 'data/automation/gates.json', gates)
    return {'ok': True, 'counts': {k: len(v) for k, v in value['selected'].items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['surf', 'memory', 'review', 'commit'])
    parser.add_argument('--snapshot')
    parser.add_argument('--report')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        with lock(ROOT):
            if args.command in ('surf', 'memory'):
                result = evaluate(ROOT, args.command, persist=not args.dry_run)
            elif args.command == 'review':
                result = review(ROOT, args.snapshot)
            else:
                result = commit(ROOT, args.snapshot, args.report or '')
    except Exception:
        # The scheduler defaults to waking on script failure. Always emit a valid skip decision.
        if args.command not in ('surf', 'memory'):
            raise SystemExit('整理没有提交：请核对快照、来源状态和报告，游标保持原样。') from None
        result = {'wakeAgent': False, 'reason': '本地预检失败，本次已跳过模型调用；请检查后台设置与数据。', 'error': True}
        try:
            with lock(ROOT):
                previous = read(ROOT / 'data/automation/gates.json', {})
                write(ROOT / 'data/automation/gates.json', {**previous, args.command: {**result, 'checked_at': datetime.now(TZ).isoformat()}})
        except Exception:
            pass
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
