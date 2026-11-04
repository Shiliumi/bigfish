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
SCHEMA={'name':'fish_room','description':'你的虚拟小屋与用户界面的三维房间相同。inspect 查看完整家具、当前氛围、可移动物品与回执；可移动清单不是全部家具。move 按当前用户要求搬动物品，需最新 revision 和原话。photo 按用户要求渲染新全景或窗边照片，不需摄像头；成功后把返回 markdown 原样放进回复发图。失败不声称已完成，不画示意图冒充照片。',
        'parameters':{'type':'object','properties':{'action':{'type':'string','enum':['inspect','move','photo']},'view':{'type':'string','enum':['room','window'],'description':'拍照角度，默认 room 全景。'},'object':{'type':'string','enum':list(OBJECTS)},'surface':{'type':'string','enum':list(SURFACES)},'revision':{'type':'integer','minimum':0},'quote':{'type':'string','description':'当前用户要求移动物品或查看房间照片的原话，最多450字。'}},'required':['action'],'additionalProperties':False}}

def current_clause(user,quote,session,started_at):
    if not isinstance(user,str)or not isinstance(quote,str)or not 4<=len(quote)<=450 or quote not in user or not session or started_at is None:raise ValueError('需要当前用户原话。')
    start=user.find(quote);end=start+len(quote);boundaries=[m.start()for m in re.finditer(r'[，,。！？!?；;\n]',user)]
    left=max((i+1 for i in boundaries if i<start),default=0);right=min((i for i in boundaries if i>=end),default=len(user));clause=user[left:right]
    if re.search(r'不要|不用|不必|不想|不需要|不准|不许|不能|没让|不是让|别(?:再|给|把|动|挪|移|放|摆|搬|拍|发)|禁止|假如|如果',clause):raise ValueError('当前语句没有明确要求执行。')
    return clause


class RoomClient:
    def __init__(self,root):self.root=Path(root).resolve()

    def _request(self,method,path,data=None):
        key=(Path.home()/'Library/Application Support/Bigfish/desktop-access.key').read_text().strip()
        if not re.fullmatch(r'[a-f0-9]{64}',key):raise ValueError('本机应用凭据暂时不可用。')
        request=Request('http://127.0.0.1:9120/api/room'+path,data=None if data is None else json.dumps(data,separators=(',',':')).encode(),method=method,headers={'X-Fish-Desktop':key,'X-Fish-Client':'studio','X-Fish-Room-Project':sha256(str(self.root).encode()).hexdigest(),'Content-Type':'application/json'})
        # The room owner is a fixed loopback service; never pass its proof through an HTTP proxy.
        with build_opener(ProxyHandler({})).open(request,timeout=35 if path=='/capture'else 5)as response:
            payload=response.read(100_001)
            if len(payload)>100_000:raise ValueError('小屋返回内容过长。')
            return json.loads(payload)

    def context(self,query):
        if not isinstance(query,str)or not re.search(r'房间|小屋|屋里|屋子|窗外|窗边|窗台|花盆|盆栽|家具|书架|床头|地毯|抱枕|你的家|你家|你在(?:哪|干)|自拍|拍照',query):return ''
        try:
            value=self._request('GET','/context')
            compact={key:value[key]for key in ('name','representation','environment','scope')}
            compact['furnishings']=[{key:row[key]for key in ('name','area','details')}for row in value['fixed_furnishings']]
            compact['movable_items']=[{key:row[key]for key in ('name','at','locked')}for row in value['movable_items']]
            if re.search(r'天气|下雨|下雪|雨天|雪天|白天|晚上|窗外',query)and not re.search(r'家具|布置|挪|移动|摆|放到|花盆|盆栽|书架|床|抱枕|杯子|本子',query):
                compact.pop('furnishings',None);compact.pop('movable_items',None)
            return '当前虚拟小屋的宿主状态（同一应用画面；当前状态优先于旧回答、旧回忆里的猜测）：\n'+json.dumps(compact,ensure_ascii=False,separators=(',',':'))
        except (OSError,URLError,ValueError,KeyError,TypeError):return '当前小屋状态暂时无法读取；你仍拥有应用内的小屋，不要把读取失败说成没有房间或没有固定家具。'

    def live(self,args,user,session,started_at):
        try:
            if not isinstance(args,dict)or set(args)-{'action','object','surface','revision','quote','view'}:raise ValueError('这项房间操作不支持。')
            if args.get('action')=='inspect':
                return self._request('GET','/context')
            if args.get('action')=='photo':
                quote=args.get('quote')or user;current_clause(user,quote,session,started_at)
                if not re.search(r'照片|拍照|自拍|拍.{0,8}(?:张|房间|小屋|窗)|(?:看看|看下|看一眼).{0,12}(?:你.{0,3})?(?:房间|小屋|窗外)',quote):raise ValueError('当前用户没有要求看小屋照片。')
                view=args.get('view','room')
                if view not in ('room','window'):raise ValueError('拍照视角不支持。')
                revision=args.get('revision')
                if revision is None:revision=self._request('GET','/context')['revision']
                if type(revision)is not int or revision<0:raise ValueError('房间版本不正确。')
                operation=str(uuid5(NAMESPACE_URL,json.dumps([str(self.root),session,str(started_at),'photo',view],ensure_ascii=False)))
                result=self._request('POST','/capture',{'operation_id':operation,'view':view,'revision':revision})
                if result.get('ok')is not True or not isinstance(result.get('photo'),dict)or not re.fullmatch(r'/api/room/photos/ph-[a-f0-9]{24}/image',result['photo'].get('image_url','')):raise ValueError('照片尚未确认。')
                return result
            if args.get('action')!='move':raise ValueError('这项房间操作不支持。')
            ident=args.get('object');surface=args.get('surface');quote=args.get('quote')or user
            if ident not in OBJECTS or surface not in SURFACES or type(args.get('revision'))is not int or args['revision']<0:raise ValueError('先 inspect 核对物品和当前布局版本。')
            current_clause(user,quote,session,started_at)
            if not re.search(OBJECTS[ident],quote)or not any(word in quote for word in SURFACES[surface])or not re.search(r'挪|移|放|摆|搬',quote):raise ValueError('当前原话没有明确要求把这件物品移动到此处，请先核对。')
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
            return {'ok':False,'error':'小屋操作未确认。请检查当前原话、布局版本、锁定状态及本机应用连接；不能声称已完成或改用示意图冒充照片。'}
