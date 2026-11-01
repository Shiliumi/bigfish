from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import unittest
import activity_gate as gate
import memory_review_backup as backup
from fish_journal import Journal
from install_memory_review_sources import OLD_BACKUP,NEW_BACKUP,upgrade_prompt


class ReviewBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.core=self.root/'.hermes/memories';self.core.mkdir(parents=True);self.ident='a'*64
    def write(self,name,value):
        (self.core/name).write_bytes(value)
    def test_exact_bytes_and_absence_are_preserved_with_private_permissions(self):
        value=b'\xef\xbb\xbfSynthetic core\r\n\x00';self.write('MEMORY.md',value)
        result=backup.capture(self.root,self.ident);folder=self.root/result['path']
        self.assertEqual((folder/'MEMORY.md').read_bytes(),value);self.assertFalse((folder/'USER.md').exists())
        self.assertIsNone(result['files']['USER.md']);self.assertEqual((folder/'MEMORY.md').stat().st_mode&0o777,0o600)
        self.assertEqual(folder.stat().st_mode&0o777,0o700)
        self.assertFalse((self.core/'USER.md').exists());self.assertEqual((self.core/'MEMORY.md').read_bytes(),value)
    def test_retry_reuses_matching_image_and_changed_core_keeps_both_images(self):
        self.write('MEMORY.md',b'first');first=backup.capture(self.root,self.ident)
        self.assertEqual(first,backup.capture(self.root,self.ident))
        self.write('MEMORY.md',b'second');second=backup.capture(self.root,self.ident)
        self.assertNotEqual(first['path'],second['path']);self.assertEqual((self.root/first['path']/'MEMORY.md').read_bytes(),b'first')
        self.assertEqual((self.root/second['path']/'MEMORY.md').read_bytes(),b'second')
    def test_corrupt_existing_backup_is_not_overwritten(self):
        self.write('USER.md',b'private original');result=backup.capture(self.root,self.ident)
        target=self.root/result['path']/'USER.md';target.write_bytes(b'external edit')
        with self.assertRaises(ValueError):backup.capture(self.root,self.ident)
        self.assertEqual(target.read_bytes(),b'external edit');self.assertEqual((self.core/'USER.md').read_bytes(),b'private original')
    def test_changed_pair_during_capture_is_retried_without_publishing_first_image(self):
        first={'MEMORY.md':b'old','USER.md':None};second={'MEMORY.md':b'new','USER.md':b'profile'}
        with patch.object(backup,'pair',side_effect=[first,second,second,second,second]):result=backup.capture(self.root,self.ident)
        images=[p for p in (self.root/'backups/memory-review'/self.ident).iterdir()if not p.name.startswith('.')]
        self.assertEqual(len(images),1);self.assertEqual((self.root/result['path']/'MEMORY.md').read_bytes(),b'new')
    def test_invalid_identity_oversize_and_outside_source_are_rejected(self):
        with self.assertRaises(ValueError):backup.capture(self.root,'../bad')
        self.write('MEMORY.md',b'x'*(backup.MAX_BYTES+1))
        with self.assertRaises(ValueError):backup.capture(self.root,self.ident)
        (self.core/'MEMORY.md').unlink()
        outside=self.root.parent/(self.root.name+'-outside');outside.write_bytes(b'outside');self.addCleanup(outside.unlink)
        (self.core/'MEMORY.md').symlink_to(outside)
        with self.assertRaises(ValueError):backup.capture(self.root,self.ident)
    def batch(self):
        with Journal(self.root)as journal:journal.capture('fiction','一起看积木机关。','那个翻折结构很有趣。')
        value=gate.pending(self.root);gate.write(self.root/f"data/automation/reviews/{value['id']}.json",value)
        return value
    def test_review_returns_ack_only_and_reuses_backup_for_episode_fetch(self):
        secret=b'synthetic-private-core-without-prefix';self.write('USER.md',secret);batch=self.batch()
        result=gate.review(self.root,batch['id']);receipt=result['core_backup']
        self.assertNotIn(secret.decode(),json.dumps(result));self.assertEqual((self.root/receipt['path']/'USER.md').read_bytes(),secret)
        key=next(iter(batch['selected']['episodes']));single=gate.review(self.root,batch['id'],key)
        self.assertEqual(single['core_backup'],receipt)
        saved=gate.snapshot(self.root,batch['id']);self.assertEqual(saved['core_backup'],receipt)
        self.assertEqual(saved['delivered_episodes'],batch['selected']['episodes'])
    def test_failed_backup_does_not_publish_source_coverage_or_modify_core(self):
        self.write('MEMORY.md',b'keep');batch=self.batch()
        with patch.object(backup,'capture',side_effect=OSError('backup unavailable')):
            with self.assertRaises(OSError):gate.review(self.root,batch['id'])
        saved=gate.snapshot(self.root,batch['id']);self.assertNotIn('delivered_episodes',saved);self.assertNotIn('core_backup',saved)
        self.assertEqual((self.core/'MEMORY.md').read_bytes(),b'keep')
    def test_known_backup_step_upgrades_without_replacing_custom_instructions(self):
        current=(Path(__file__).resolve().parents[1]/'config/memory-prompt.txt').read_text()
        legacy=current.replace(NEW_BACKUP,OLD_BACKUP);self.assertEqual(upgrade_prompt(legacy),current)
        self.assertEqual(upgrade_prompt(current),current)
        custom=current.replace(NEW_BACKUP,'2. 用户自己选择另一个备份方案。')
        self.assertEqual(upgrade_prompt(custom),custom)


if __name__=='__main__':unittest.main()
