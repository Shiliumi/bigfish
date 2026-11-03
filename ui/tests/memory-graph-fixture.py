"""Owned temporary profile only; never reads the user's memories."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from fish_journal import Journal, UNSET
from fish_memory_graph import graph

root = Path(sys.argv[1]).resolve()
if not root.name.startswith('fish-stars-browser-') or not (root/'.fixture-owned').is_file():
    raise SystemExit('Fixture requires its own temporary profile.')
now = datetime(2026, 11, 3, 4, tzinfo=timezone.utc)
with Journal(root, now=now) as journal:
    if sys.argv[2] == 'seed':
        topics = ['纸机关','海边小屋','雨声白噪音','小鲸鱼摆件','猫咪短片','星空摄影','杯子与窗台','蓝色手账','积木小厨房','像素游戏','热可可','吉他和弦']
        for number in range(96):
            topic = topics[number%len(topics)]
            row = journal.capture('fixture-chat-'+str(number%8), '虚构验收 '+str(number)+'：那天一起聊了'+topic+'。', '先记住那个具体的小细节，留着下次接着聊。', now-timedelta(hours=number*9+1))
            if number%3 == 0:
                journal.update(row['id'],1,aliases=[topic],pinned=number%12==0)
            elif number%7 == 0:
                journal.update(row['id'],1,kind='impression',invalidate=True)
        result={'seeded':96}
    else:
        data=json.load(sys.stdin)
        if data.get('action')=='graph':
            result=graph(journal,data)
        elif data.get('action')=='detail':
            row=journal.get(data['id'])
            result={**journal.describe(row),'history':journal.history(row['id'])} if row and row['status']=='active' else None
        elif data.get('action')=='update':
            result=journal.update(data['id'],data['revision'],summary=data.get('summary'),pinned=data.get('pinned'),forget=data.get('forget',False),valid_until=data.get('valid_until',UNSET),kind=data.get('kind'),invalidate=data.get('invalidate',False),aliases=data.get('aliases',UNSET))
        else:
            result={'items':[{k:v for k,v in row.items() if k!='excerpt'} for row in journal.search(data.get('q',''),30,scope=data.get('scope','current'))],'stats':journal.status()}
print(json.dumps(result,ensure_ascii=False))
