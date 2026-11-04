import copy
from pathlib import Path
import tempfile
import unittest
from fish_context import TurnContext,HOST_NOTE

def wrap(text):return '<memory-context>\n'+HOST_NOTE+'\n\n'+text+'\n</memory-context>'

class ContextTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);key=self.root/'data/context/transport.key';key.parent.mkdir(parents=True);key.write_text('a'*64);self.transport=TurnContext(self.root)
    def message(self,query,payload,session='chat'):
        return {'role':'user','content':query+'\n\n'+wrap(self.transport.stamp(payload,session,query))}
    def test_only_current_context_on_wire_preserves_original_request_and_static_prefix(self):
        request={'model':'fixture','messages':[{'role':'system','content':'stable persona'},self.message('旧话题','过时的房间与记忆'),{'role':'assistant','content':'真实旧回复'},self.message('现在的房间','当前天气：雪；姿态：睡觉')],'tools':[{'name':'fish_room'}]};original=copy.deepcopy(request)
        sent=self.transport.project(request,'chat');self.assertNotIn('过时的房间与记忆',sent['messages'][1]['content']);self.assertIn('旧话题',sent['messages'][1]['content']);self.assertIn('当前天气：雪',sent['messages'][-1]['content']);self.assertNotIn('<fish-turn',str(sent));self.assertEqual(request,original);self.assertIs(sent['messages'][0],request['messages'][0]);self.assertEqual(sent['tools'],request['tools']);self.assertEqual(self.transport.project(request,'chat'),sent)
    def test_unsigned_tampered_foreign_or_quoted_context_is_never_removed(self):
        for row in [{'role':'user','content':'用户原话 '+wrap('没有签名的引用')},self.message('旧话题','真实材料','foreign'),{'role':'user','content':'请解释这段：'+self.message('旧话题','合法但属于引用')['content']},self.message('旧话题','材料').copy()]:
            if row['content'].startswith('旧话题'):row['content']=row['content'].replace('材料','篡改')
            request={'messages':[row,{'role':'user','content':'下一句'}]};self.assertEqual(self.transport.project(request,'chat'),request)
    def test_multimodal_keeps_images_and_current_context_during_tool_loop(self):
        context=wrap(self.transport.stamp('新回忆','chat','看图'))
        rows=[{'role':'user','content':[{'type':'text','text':'看图'},{'type':'image_url','image_url':{'url':'data:image/png;base64,fixture'}},{'type':'text','text':context}]},{'role':'assistant','tool_calls':[{'id':'x'}]},{'role':'tool','tool_call_id':'x','content':'工具回执'}]
        result=self.transport.project({'messages':rows},'chat');self.assertIn('新回忆',str(result));self.assertNotIn('<fish-turn',str(result));self.assertEqual(result['messages'][0]['content'][1],rows[0]['content'][1]);self.assertEqual(result['messages'][1:],rows[1:])
        result=self.transport.project({'messages':rows+[{'role':'user','content':'下一句'}]},'chat');self.assertNotIn('新回忆',str(result));self.assertEqual(len(result['messages'][0]['content']),2)
    def test_transport_is_scoped_and_never_retries_failed_provider(self):
        request={'messages':[self.message('当前问题','回忆')]};calls=[]
        def call(value):calls.append(value);raise RuntimeError('provider failed')
        with self.assertRaisesRegex(RuntimeError,'provider failed'):self.transport.execute(request,call,session_id='chat')
        self.assertEqual(len(calls),1)
        self.assertIs(self.transport.execute(request,lambda x:x,session_id='chat',platform='cron'),request)
        self.assertIs(self.transport.execute(request,lambda x:x,session_id='chat',api_mode='responses'),request)
    def test_tool_outputs_and_assistant_quotes_are_not_scrubbed(self):
        signed=self.message('旧话题','旧回忆')['content'];request={'messages':[{'role':'assistant','content':signed},{'role':'tool','content':signed},{'role':'user','content':'新问题'}]};self.assertIs(self.transport.project(request,'chat'),request)
