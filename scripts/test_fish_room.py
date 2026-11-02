import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
from io import BytesIO
from fish_room import RoomClient


class RoomToolTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.client=RoomClient(Path(self.temp.name))
        self.args={'action':'move','object':'cup','surface':'sill','revision':4,'quote':'把杯子挪到窗台'}

    def test_same_turn_action_has_stable_identity_and_new_turn_has_a_new_identity(self):
        with patch.object(self.client,'_request',return_value={'ok':True,'receipt':{'id':'fiction'}})as call:
            for _ in range(2):self.client.live(self.args,'帮我把杯子挪到窗台。','chat-a','time-a')
            self.assertEqual(call.call_args_list[0],call.call_args_list[1]);first=call.call_args.args[2]['operation_id']
            self.client.live(self.args,'帮我把杯子挪到窗台。','chat-a','time-b');self.assertNotEqual(first,call.call_args.args[2]['operation_id'])

    def test_quote_must_match_current_human_and_requested_object_destination(self):
        for text,changes in [('你看这个视频。',{}),('不要把杯子挪到窗台',{}),('如果把杯子挪到窗台',{}),('把杯子挪到窗台',{'surface':'bed'}),('把杯子挪到窗台',{'object':'book'}),('把杯子放到书桌',{'quote':'把杯子放到书桌','object':'book','surface':'desk'}),('把杯子挪到窗台',{'quote':'帮我把杯子挪到窗台'}),('把杯子挪到窗台',{'revision':True}),('把杯子挪到窗台',{'unlock':True})]:
            with self.subTest(text=text,changes=changes),patch.object(self.client,'_request')as call:
                self.assertFalse(self.client.live({**self.args,**changes},text,'chat','time')['ok']);call.assert_not_called()

    def test_inspect_is_small_and_does_not_return_photos_or_private_storage_fields(self):
        value={'revision':2,'fixed_furnishings':[{'id':'shelf','name':'书架'},{'id':'plant','name':'盆栽'}],'movable_items':[{'id':'cup'}],'scope':'可移动清单不是全部家具'}
        with patch.object(self.client,'_request',return_value=value)as call:
            result=self.client.live({'action':'inspect'},'看看小屋。','chat','time');self.assertEqual(call.call_args.args,('GET','/context'));self.assertEqual(result,value)

    def test_errors_and_missing_receipts_never_report_success(self):
        for result in [{},{'ok':True},{'ok':False,'receipt':{}}]:
            with patch.object(self.client,'_request',return_value=result):self.assertFalse(self.client.live(self.args,'把杯子挪到窗台','chat','time')['ok'])
        for error in [URLError('private connection text'),HTTPError('private-url',409,'Conflict',{},BytesIO(json.dumps({'error':'物品已锁定'}).encode()))]:
            with patch.object(self.client,'_request',side_effect=error):
                result=self.client.live(self.args,'把杯子挪到窗台','chat','time');self.assertFalse(result['ok']);self.assertNotIn('private',json.dumps(result))

    def test_missing_current_turn_cannot_execute(self):
        with patch.object(self.client,'_request')as call:
            for session,at in [('',None),('chat',None)]:self.assertFalse(self.client.live(self.args,'把杯子挪到窗台',session,at)['ok'])
            call.assert_not_called()

    def test_room_queries_get_grounded_context_but_unrelated_chat_adds_no_network_or_room_tokens(self):
        value={'name':'大肥鱼的小屋','representation':'地毯上','environment':{'weather':'snow'},'scope':'三件可移动物品不是全部家具','fixed_furnishings':[{'name':'书架','area':'左边','details':'多本书'},{'name':'盆栽','area':'桌旁','details':'绿植'}],'movable_items':[{'name':'杯子','at':'窗台','locked':False}]}
        with patch.object(self.client,'_request',return_value=value)as call:
            self.assertEqual(self.client.context('讲个冷笑话'), '');call.assert_not_called()
            text=self.client.context('你房间里没有花盆和书架吗');self.assertIn('盆栽',text);self.assertIn('书架',text);self.assertIn('不是全部家具',text);self.assertLess(len(text),1800)

    def test_photo_returns_only_a_confirmed_local_image_and_reuses_identity_for_retries(self):
        photo={'ok':True,'photo':{'image_url':'/api/room/photos/ph-'+'a'*24+'/image'},'markdown':'![小屋](/api/room/photos/ph-'+'a'*24+'/image)'}
        args={'action':'photo','revision':4,'quote':'把你房间的照片发我看看'}
        with patch.object(self.client,'_request',return_value=photo)as call:
            self.assertTrue(self.client.live(args,'嗯哼，把你房间的照片发我看看','chat','time')['ok']);first=call.call_args
            self.assertTrue(self.client.live(args,'嗯哼，把你房间的照片发我看看','chat','time')['ok']);self.assertEqual(first,call.call_args)
        for result in [{},{'ok':True,'photo':{}},{'ok':True,'photo':{'image_url':'https://example.org/old.png'}}]:
            with patch.object(self.client,'_request',return_value=result):self.assertFalse(self.client.live(args,'把你房间的照片发我看看','chat','time')['ok'])
        with patch.object(self.client,'_request')as call:
            self.assertFalse(self.client.live({'action':'photo','quote':'把你房间的照片发我看看'},'不要把你房间的照片发我看看','chat','time')['ok']);call.assert_not_called()


if __name__=='__main__':unittest.main()
