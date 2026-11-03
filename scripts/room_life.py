"""Optional, evidenced room choices piggyback on the existing surf completion."""
import hashlib
from fish_journal import safe_text, redact_text

OBJECTS={'cup':{'desk','sill','nightstand'},'book':{'floor','desk','nightstand','bed'},'cushion':{'floor','bed'}}


def proposal(root, value, run_id, report_path, observations, now):
    if value is None:
        return None
    if not isinstance(value,dict) or value.get('action') not in ('move','wish'):
        raise ValueError('小屋选择只能是一次移动或一个愿望。')
    indexes=value.get('evidence_observations')
    if not isinstance(indexes,list) or not indexes or len(indexes)>3 or any(type(i)is not int or not 0<=i<len(observations) for i in indexes):
        raise ValueError('小屋想法必须引用本轮真实观察。')
    def text(key,minimum,maximum):
        raw=value.get(key)
        if not isinstance(raw,str)or not minimum<=len(raw.strip())<=maximum or redact_text(root,safe_text(raw,maximum))!=raw.strip():
            raise ValueError('小屋想法内容无效或包含凭据。')
        return raw.strip()
    item={'action':value['action'],'why':text('why',6,200)}
    if value['action']=='move':
        if value.get('object')not in OBJECTS or value.get('surface')not in OBJECTS[value['object']] or type(value.get('revision'))is not int or value['revision']<0:
            raise ValueError('请使用 briefing 里的小屋版本和允许的位置。')
        item.update({key:value[key]for key in ('object','surface','revision')})
    else:
        item.update(item=text('item',2,40),text=text('text',6,200))
    selected=[observations[i]for i in dict.fromkeys(indexes)]
    fingerprints={o['id']:hashlib.sha256('\0'.join(o.get(k)or''for k in ('id','url','report_path','seen_at','read_depth','observation','candidate_trait','reason')).encode()).hexdigest()for o in selected}
    return {'schema':1,'id':'rl-'+hashlib.sha256(run_id.encode()).hexdigest()[:24],'run_id':run_id,
            'created_at':now.isoformat(),'report_path':report_path,'observation_ids':[o['id']for o in selected],'observation_hashes':fingerprints,'proposal':item}


def briefing(root):
    if not (root/'scripts/fish_room.py').is_file():
        return {'available':False}
    try:
        from fish_room import RoomClient
        return RoomClient(root)._request('GET','/life/briefing')
    except Exception:
        return {'available':False,'note':'小屋暂时没有连接；照常冲浪，不提交移动或愿望，不额外唤醒模型。'}
