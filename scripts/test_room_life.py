import copy
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_surf_complete as surf_tests
from room_life import proposal,briefing


class RoomCompletionTest(unittest.TestCase):
    setUp=surf_tests.CompleteTest.setUp
    complete=surf_tests.CompleteTest.complete
    def test_room_wish_commits_after_sources_and_retry_never_duplicates(self):
        data=copy.deepcopy(self.payload)
        data['room']={'action':'wish','item':'鲸鱼书签','text':'爹，我想给小本子夹个鲸鱼书签。','why':'读到了纸片机关，想留个翻页记号。','evidence_observations':[0]}
        result=self.complete(data)
        self.assertTrue(result['room_event_queued'])
        events=list((self.root/'data/room-events').glob('*.json'));self.assertEqual(len(events),1)
        event=json.loads(events[0].read_text());self.assertEqual(event['observation_ids'],result['observation_ids']);self.assertTrue(event['observation_hashes'])
        self.assertTrue(self.complete(data)['already_submitted']);self.assertEqual(len(list((self.root/'data/room-events').glob('*.json'))),1)

    def test_invalid_room_evidence_rolls_back_whole_outing(self):
        data=copy.deepcopy(self.payload);data['room']={'action':'wish','item':'鲸鱼书签','text':'爹，我想给小本子夹个鲸鱼书签。','why':'读到了纸片机关，想留个翻页记号。','evidence_observations':[1]}
        with self.assertRaises(ValueError):self.complete(data)
        self.assertFalse((self.root/self.payload['report']['path']).exists())

    def test_room_event_is_not_visible_before_surf_commit_and_recovers_after_interruption(self):
        import surf_complete
        data=copy.deepcopy(self.payload);data['room']={'action':'move','object':'cup','surface':'sill','revision':2,'why':'读到了窗边小角落，想把杯子挪近一点。','evidence_observations':[0]}
        actual=surf_complete.write_bytes
        def fail(path,value):
            if path.parent==self.root/'data/room-events':raise OSError('simulated room spool interruption')
            return actual(path,value)
        with patch.object(surf_complete,'write_bytes',side_effect=fail):
            with self.assertRaises(OSError):self.complete(data)
        self.assertEqual(surf_complete.recover(self.root),{'recovered':1})
        self.assertEqual(len(list((self.root/'data/room-events').glob('*.json'))),1)
        self.assertEqual(json.loads((self.root/'data/surf-completions'/(self.run+'.json')).read_text())['status'],'committed')

    def test_no_room_proposal_does_not_create_a_fake_life_event(self):
        self.complete();self.assertFalse((self.root/'data/room-events').exists())
        self.assertEqual(briefing(self.root),{'available':False})

    def test_room_choice_rejects_invalid_targets_and_credentials(self):
        rows=[{'id':'obs-test','url':'https://example.org'}]
        for extra in ({'object':'plant','surface':'desk','revision':0},{'object':'cup','surface':'bed','revision':0},{'object':'cup','surface':'sill','revision':True}):
            with self.assertRaises(ValueError):proposal(self.root,{'action':'move','why':'这是虚构验收中的理由。','evidence_observations':[0],**extra},self.run,'report',rows,self.now)
