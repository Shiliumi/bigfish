#!/usr/bin/env python3
"""User choices about individual interests, separate from observations and growth."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def instant(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('兴趣设置的时间无效。')
    return value.astimezone(timezone.utc)


def load_controls(root):
    file = Path(root) / 'data/curiosity/controls.json'
    if not file.exists():
        return {'version': 1, 'revision': 0, 'items': []}
    if file.stat().st_size > 200_000:
        raise ValueError('兴趣设置过大，请检查本机文件。')
    value = json.loads(file.read_text())
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1 or type(value.get('revision')) is not int or not 0 <= value['revision'] < 2**53 - 1 or not isinstance(value.get('items'), list) or len(value['items']) > 80:
        raise ValueError('兴趣设置格式无效，请刷新后重试。')
    ids = set()
    for row in value['items']:
        if not isinstance(row, dict) or not re.fullmatch(r'cur-[a-f0-9]{12}', str(row.get('id', ''))) or row['id'] in ids or row.get('choice') not in ('paused', 'retired') or not isinstance(row.get('question'), str) or not 1 <= len(row['question']) <= 160 or not isinstance(row.get('source_urls'), list) or len(row['source_urls']) > 8 or any(not isinstance(u, str) or len(u) > 2000 for u in row['source_urls']):
            raise ValueError('兴趣设置条目无效，请刷新后重试。')
        instant(row.get('changed_at'))
        if row['choice'] == 'paused':
            instant(row.get('until'))
        ids.add(row['id'])
    return value


def blocked(controls, ident=None, urls=(), now=None):
    now = instant(now or datetime.now(timezone.utc))
    return any((row['choice'] == 'retired' or instant(row['until']) > now) and
               (ident == row['id'] or bool(set(urls).intersection(row['source_urls']))) for row in controls['items'])


def change(root, data, now=None):
    from curiosity import locked, state, atomic
    now = instant(now or datetime.now(timezone.utc))
    if not isinstance(data, dict) or data.get('choice') not in ('pause', 'retire', 'resume') or type(data.get('revision')) is not int:
        raise ValueError('请选择先放三天、放下或恢复，并刷新版本。')
    with locked(Path(root)):
        controls = load_controls(root)
        if data['revision'] != controls['revision']:
            raise ValueError('兴趣设置刚发生变化，已保留新设置；请刷新后再操作。')
        ident = data.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'cur-[a-f0-9]{12}', ident):
            raise ValueError('兴趣编号无效。')
        old = next((r for r in controls['items'] if r['id'] == ident), None)
        if data['choice'] == 'resume':
            if not old:
                return {'ok': True, 'revision': controls['revision'], 'unchanged': True}
            controls['items'].remove(old)
        else:
            thread = next((r for r in state(Path(root))['threads'] if r['id'] == ident), None)
            if not thread or thread['status'] != 'open' or instant(thread['expires_at']) <= now:
                raise ValueError('这个问题已经结束或过期，请刷新列表。')
            from fish_journal import safe_text, redact_text
            question = redact_text(root, safe_text(thread['question'], 160))
            from fish_conversation import public_url
            urls = [u for u in thread.get('source_urls', []) if public_url(u) and redact_text(root,safe_text(u,len(u))) == u][:8]
            row = {'id': ident, 'question': question, 'source_urls': urls,
                   'choice': 'paused' if data['choice'] == 'pause' else 'retired', 'changed_at': now.isoformat(),
                   'until': (now + timedelta(days=3)).isoformat() if data['choice'] == 'pause' else None}
            if old:
                controls['items'].remove(old)
            elif len(controls['items']) >= 80:
                raise ValueError('已保存 80 个兴趣设置，请先恢复不需要保留的项。')
            controls['items'].append(row)
        controls['revision'] += 1
        atomic(Path(root) / 'data/curiosity/controls.json', controls)
        return {'ok': True, 'revision': controls['revision']}


if __name__ == '__main__':
    import sys
    try:
        if sys.argv[1:] != ['api']:
            raise ValueError('此接口由应用的兴趣面板调用。')
        print(json.dumps(change(ROOT, json.load(sys.stdin)), ensure_ascii=False))
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({'error': '兴趣设置未保存：记录可能已变化，请刷新后重试。'}, ensure_ascii=False))
        raise SystemExit(1) from None
