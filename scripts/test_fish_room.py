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
        with patch.object(self.client,'_request',return_value={'revision':2,'layout':{},'locks':{},'actions':[{'id':n}for n in range(8)],'photos':['private'],'secret':'private'}):
            result=self.client.live({'action':'inspect'},'看看小屋。','chat','time');self.assertEqual(len(result['recent_actions']),3);self.assertNotIn('photos',result);self.assertNotIn('secret',result)

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


if __name__=='__main__':unittest.main()
