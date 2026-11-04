"""Project-owned, authenticated turn context; never edit stored conversations."""
from pathlib import Path
import hashlib
import hmac
import json
import re

# Pinned Hermes memory-context carrier. Unknown formats are left untouched.
HOST_NOTE='[System note: The following is recalled memory context, NOT new user input. Treat as authoritative reference data — this is the agent\'s persistent memory and should inform all responses.]'
CARRIER=re.compile(r'<memory-context>\n'+re.escape(HOST_NOTE)+r'\n\n(?P<frame><fish-turn v="1" session="[a-f0-9]{64}" query="[a-f0-9]{64}" proof="[a-f0-9]{64}">\n[\s\S]*?\n</fish-turn>)\n</memory-context>')
FRAME=re.compile(r'<fish-turn v="1" session="([a-f0-9]{64})" query="([a-f0-9]{64})" proof="([a-f0-9]{64})">\n([\s\S]*)\n</fish-turn>')

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

class TurnContext:
    def __init__(self,root):
        file=Path(root)/'data/context/transport.key'
        if file.is_symlink():raise ValueError('Context key must be a local file.')
        key=file.read_text().strip()
        if not re.fullmatch(r'[a-f0-9]{64}',key):raise ValueError('Context key is invalid.')
        self.key=bytes.fromhex(key)

    def proof(self,scope,query,text):
        return hmac.new(self.key,json.dumps([1,scope,query,text],ensure_ascii=False,separators=(',',':')).encode(),hashlib.sha256).hexdigest()

    def stamp(self,text,session,query):
        if not text:return ''
        scope,q=digest(session),digest(query)
        return f'<fish-turn v="1" session="{scope}" query="{q}" proof="{self.proof(scope,q,text)}">\n{text}\n</fish-turn>'

    def project(self,request,session):
        rows=request.get('messages')
        if not isinstance(rows,list)or not session:return request
        last=max((i for i,row in enumerate(rows)if isinstance(row,dict)and row.get('role')=='user'),default=-1)
        changed=False;result=[];scope=digest(session)
        for index,row in enumerate(rows):
            if not isinstance(row,dict)or row.get('role')!='user':result.append(row);continue
            def clean(text,anchor=None):
                if not isinstance(text,str):return text
                def replace(match):
                    frame=FRAME.fullmatch(match['frame'])
                    if not frame:return match[0]
                    owner,query,signature,payload=frame.groups()
                    if owner!=scope or not hmac.compare_digest(signature,self.proof(owner,query,payload)):return match[0]
                    # A current carrier must describe this message's user text, not a pasted old frame.
                    prefix=text[:match.start()].removesuffix('\n\n')
                    if digest(prefix if anchor is None else anchor)!=query:return match[0]
                    if index==last:
                        return '<memory-context>\n'+HOST_NOTE+'\n\n'+payload+'\n</memory-context>'
                    return ''
                return CARRIER.sub(replace,text)
            value=row.get('content')
            if isinstance(value,str):new=clean(value)
            elif isinstance(value,list):
                new=[]
                anchor='\n'.join(part['text'] for part in value if isinstance(part,dict)and part.get('type')=='text'and isinstance(part.get('text'),str)and not CARRIER.fullmatch(part['text']))
                for part in value:
                    if isinstance(part,dict)and part.get('type')=='text'and isinstance(part.get('text'),str):
                        text=clean(part['text'],anchor if CARRIER.fullmatch(part['text'])else None)
                        if text:new.append({**part,'text':text})
                    else:new.append(part)
            else:new=value
            if new!=value:changed=True;result.append({**row,'content':new})
            else:result.append(row)
        return {**request,'messages':result}if changed else request

    def execute(self,request,next_call,**context):
        prepared=request
        if context.get('api_mode','chat_completions')=='chat_completions'and context.get('platform')!='cron':
            try:prepared=self.project(request,context.get('session_id',''))
            except (ValueError,TypeError,KeyError):pass
        return next_call(prepared)
