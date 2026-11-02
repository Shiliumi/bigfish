"""Narrow room tools for a current human chat turn; all writes use the local room owner."""
import json
from hashlib import sha256
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from uuid import NAMESPACE_URL, uuid5

OBJECTS={'cup':r'杯子|水杯|茶杯|咖啡杯|小杯','book':r'本子|笔记本|书(?!桌|架|房|店|法|柜|写)','cushion':r'抱枕|靠垫|垫子'}
SURFACES={'floor':('地面','地上','地板'),'desk':('书桌','桌上','桌边','桌子'),'sill':('窗台','窗边'),'nightstand':('床头柜',),'bed':('床上','床面','床边')}
SCHEMA={'name':'fish_room','description':'查看真实小屋布局、物品锁定和执行记录，或按当前用户明确要求挪动杯子/书/抱枕。先 inspect 取得最新 revision；move 引用当前用户原话。成功只能依据返回的执行回执；不能解锁物品、无来源自行搬动或声称已拍照。',
        'parameters':{'type':'object','properties':{'action':{'type':'string','enum':['inspect','move']},'object':{'type':'string','enum':list(OBJECTS)},'surface':{'type':'string','enum':list(SURFACES)},'revision':{'type':'integer','minimum':0},'quote':{'type':'string','description':'当前用户要求移动这件物品到此处的原话，最多450字。'}},'required':['action'],'additionalProperties':False}}


class RoomClient:
    def __init__(self,root):self.root=Path(root).resolve()

    def _request(self,method,path,data=None):
        key=(Path.home()/'Library/Application Support/Bigfish/desktop-access.key').read_text().strip()
        if not re.fullmatch(r'[a-f0-9]{64}',key):raise ValueError('本机应用凭据暂时不可用。')
        request=Request('http://127.0.0.1:9120/api/room'+path,data=None if data is None else json.dumps(data,separators=(',',':')).encode(),method=method,headers={'X-Fish-Desktop':key,'X-Fish-Client':'studio','X-Fish-Room-Project':sha256(str(self.root).encode()).hexdigest(),'Content-Type':'application/json'})
        # The room owner is a fixed loopback service; never pass its proof through an HTTP proxy.
        with build_opener(ProxyHandler({})).open(request,timeout=5)as response:
            payload=response.read(100_001)
            if len(payload)>100_000:raise ValueError('小屋返回内容过长。')
            return json.loads(payload)

    def live(self,args,user,session,started_at):
        try:
            if not isinstance(args,dict)or set(args)-{'action','object','surface','revision','quote'}:raise ValueError('这项房间操作不支持。')
            if args.get('action')=='inspect':
                value=self._request('GET','')
                return {'revision':value['revision'],'layout':value['layout'],'locks':value['locks'],'recent_actions':value['actions'][:3],
                        'places':{'floor':'地面','desk':'书桌','sill':'窗台','nightstand':'床头柜','bed':'床上'},'allowed':{'cup':['desk','sill','nightstand'],'book':['floor','desk','nightstand','bed'],'cushion':['floor','bed']}}
            if args.get('action')!='move':raise ValueError('这项房间操作不支持。')
            ident=args.get('object');surface=args.get('surface');quote=args.get('quote')or user
            if ident not in OBJECTS or surface not in SURFACES or type(args.get('revision'))is not int or args['revision']<0:raise ValueError('先 inspect 核对物品和当前布局版本。')
            if not isinstance(user,str)or not isinstance(quote,str)or not 4<=len(quote)<=450 or quote not in user or not session or started_at is None:raise ValueError('需要引用当前用户要求移动物品的原话。')
            start=user.find(quote);end=start+len(quote);boundaries=[m.start()for m in re.finditer(r'[，,。！？!?；;\n]',user)]
            left=max((i+1 for i in boundaries if i<start),default=0);right=min((i for i in boundaries if i>=end),default=len(user));clause=user[left:right]
            if not re.search(OBJECTS[ident],quote)or not any(word in quote for word in SURFACES[surface])or not re.search(r'挪|移|放|摆|搬',quote)or re.search(r'不要|不用|不必|不想|不需要|不准|不许|不能|没让|不是让|别(?:再|给|把|动|挪|移|放|摆|搬)|禁止|假如|如果',clause):raise ValueError('当前原话没有明确要求把这件物品移动到此处，请先核对。')
            operation=str(uuid5(NAMESPACE_URL,json.dumps([str(self.root),session,str(started_at),ident,surface],ensure_ascii=False)))
            result=self._request('POST','/actions',{'object':ident,'surface':surface,'revision':args['revision'],'operation_id':operation})
            if result.get('ok')is not True or not isinstance(result.get('receipt'),dict):raise ValueError('小屋没有返回成功回执，不能声称已移动。')
            return result
        except HTTPError as e:
            try:message=json.loads(e.read(4096)).get('error')
            except (ValueError,AttributeError):message=None
            finally:e.close()
            return {'ok':False,'error':message if isinstance(message,str)and len(message)<250 else '小屋未执行这次动作，请重新 inspect 核对。','status':e.code}
        except (OSError,URLError,ValueError,KeyError,TypeError):
            return {'ok':False,'error':'小屋动作未确认。请检查当前原话、布局版本、锁定状态及本机应用连接；不能声称已经移动。'}
