"""Read-only star map projection. Edges describe evidence, never inferred facts."""
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import unicodedata

MAX_NODES = 500
MAX_EDGES = 1000


def date_boundary(value, end=False):
    from fish_journal import LOCAL_TZ
    if not value:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('日期需为 YYYY-MM-DD。')
    day = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=LOCAL_TZ)
    if day.strftime('%Y-%m-%d') != value:
        raise ValueError('日期无效。')
    return day + timedelta(days=1) if end else day


def graph(journal, data):
    scope, kind = data.get('scope', 'current'), data.get('kind', 'all')
    query, pinned = data.get('q', ''), data.get('pinned', False)
    if scope not in ('current', 'history') or kind not in ('all', 'event', 'impression'):
        raise ValueError('星图筛选无效。')
    if not isinstance(query, str) or len(query) > 100 or type(pinned) is not bool:
        raise ValueError('星图筛选无效。')
    low, high = date_boundary(data.get('from')), date_boundary(data.get('to'), True)
    if low and high and low >= high:
        raise ValueError('结束日期不能早于开始日期。')
    # Counts, date bounds and the bounded node projection share a SQLite read
    # snapshot. The whole archive and excerpts are never loaded into the UI.
    active = "julianday(valid_from)<=julianday(?) AND (valid_until IS NULL OR julianday(valid_until)>julianday(?))"
    clock = [journal.now.isoformat()] * 2
    base = "status='active'"
    scoped = base if scope == 'history' else base + ' AND ' + active
    scope_args = [] if scope == 'history' else clock
    where, args = scoped, list(scope_args)
    if kind != 'all':
        where += ' AND kind=?'
        args.append(kind)
    if pinned:
        where += ' AND pinned=1'
    if low:
        where += ' AND julianday(recorded_at)>=julianday(?)'
        args.append(low.isoformat())
    if high:
        where += ' AND julianday(recorded_at)<julianday(?)'
        args.append(high.isoformat())
    needle = unicodedata.normalize('NFKC', query).casefold().strip()
    if needle:
        def matches(summary, aliases):
            body = summary + '\n' + '\n'.join(json.loads(aliases))
            return int(needle in unicodedata.normalize('NFKC', body).casefold())
        journal.db.create_function('star_matches', 2, matches, deterministic=True)
        where += ' AND star_matches(summary,aliases)=1'
    with journal.db:
        journal.db.execute('BEGIN')
        total = journal.db.execute("SELECT COUNT(*) FROM episodes WHERE " + base).fetchone()[0]
        current = journal.db.execute("SELECT COUNT(*) FROM episodes WHERE " + base + ' AND ' + active, clock).fetchone()[0]
        bounds = journal.db.execute("SELECT MIN(date(recorded_at,'+8 hours')),MAX(date(recorded_at,'+8 hours')) FROM episodes WHERE " + scoped, scope_args).fetchone()
        matched_count = journal.db.execute('SELECT COUNT(*) FROM episodes WHERE ' + where, args).fetchone()[0]
        matched = [dict(row) for row in journal.db.execute("SELECT id, session_id, summary, aliases, recorded_at, revision, pinned, kind, valid_from, valid_until, corrected_at, status FROM episodes WHERE " + where + " ORDER BY julianday(recorded_at) DESC,id LIMIT ?", [*args, MAX_NODES])]
    nodes = []
    conversations, aliases = defaultdict(list), defaultdict(list)
    for row in matched[:MAX_NODES]:
        ident = row['id']
        names = [value for value in json.loads(row['aliases']) if journal.clean_text(value, 40) == value]
        node = {key: row[key] for key in ('id', 'revision', 'recorded_at', 'kind', 'valid_from', 'valid_until', 'corrected_at')}
        node.update(summary=journal.clean_text(row['summary'], 500), pinned=bool(row['pinned']),
                    effective_status=journal.effective_status(row), aliases=names,
                    group='cg-' + hashlib.sha256((str(journal.root) + '\0' + row['session_id']).encode()).hexdigest()[:20])
        nodes.append(node)
        conversations[row['session_id']].append(ident)
        for name in names:
            aliases[unicodedata.normalize('NFKC', name).casefold()].append(ident)
    links, omitted_edges = {}, 0

    def connect(left, right, reason):
        nonlocal omitted_edges
        pair = tuple(sorted((left, right)))
        if pair not in links:
            if len(links) >= MAX_EDGES:
                omitted_edges += 1
                return
            links[pair] = {'source': pair[0], 'target': pair[1], 'reasons': []}
        if reason not in links[pair]['reasons'] and len(links[pair]['reasons']) < 3:
            links[pair]['reasons'].append(reason)

    for members in conversations.values():
        for left, right in zip(members, members[1:]):
            connect(left, right, {'kind': 'conversation', 'label': '同一对话中当前筛选的相邻记录'})
    for name, members in sorted(aliases.items()):
        members = list(dict.fromkeys(members))
        for left, right in zip(members, members[1:]):
            connect(left, right, {'kind': 'alias', 'label': '共同手动别名：' + name})
    edges = list(links.values())
    revision = hashlib.sha256(json.dumps([nodes, edges, matched_count, total, current, list(bounds)], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    return {'revision': revision, 'generated_at': journal.now.isoformat(), 'nodes': nodes, 'edges': edges,
            'stats': {'current': current, 'historical': total-current, 'matched': matched_count, 'shown': len(nodes),
                      'omitted': max(0, matched_count-MAX_NODES), 'node_limit': MAX_NODES, 'edge_limit': MAX_EDGES,
                      'omitted_edges': omitted_edges, 'pinned': sum(node['pinned'] for node in nodes)},
            'range': {'from': bounds[0], 'to': bounds[1]},
            'semantics': '按原记录日期筛选，内容与有效状态始终取当前版本；连线表示来源或手动别名关联，不表示因果、情绪或事实相同。'}
