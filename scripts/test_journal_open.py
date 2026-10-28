"""Read-only fast path, WAL concurrency and safe migration of real SQLite files."""
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fish_journal import Journal


class JournalOpenTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        with Journal(self.root)as journal:
            self.item=journal.capture('fiction-open','一起把铜色齿轮装正。','装正以后转动平稳了。')
        self.path=self.root/'data/memory/episodes.sqlite3'

    def test_reopening_and_reading_does_not_commit_database_changes(self):
        with closing(sqlite3.connect(self.path))as observer:
            version=observer.execute('PRAGMA data_version').fetchone()[0]
            for i in range(3):
                with Journal(self.root)as journal:
                    self.assertIn('铜色齿轮',journal.recall('铜色齿轮'))
                    self.assertEqual(journal.status()['total'],1)
                    self.assertEqual(journal.db.total_changes,0)
            self.assertEqual(observer.execute('PRAGMA data_version').fetchone()[0],version)

    def test_ready_database_remains_readable_during_an_uncommitted_writer(self):
        connect=sqlite3.connect
        with closing(connect(self.path))as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE episodes SET summary=? WHERE id=?',('这段修改还未提交。',self.item['id']))
            # Fail quickly on the old unconditional write path, not after the production 8s timeout.
            with patch('fish_journal.sqlite3.connect',side_effect=lambda path,**kwargs:connect(path,timeout=.05)):
                with Journal(self.root)as journal:
                    self.assertEqual(journal.get(self.item['id'])['summary'],self.item['summary'])
                    self.assertTrue(journal.search('铜色齿轮'))
                    self.assertEqual(journal.db.total_changes,0)
            writer.rollback()

    def test_upgrade_preserves_sources_corrections_aliases_history_and_tombstones(self):
        with Journal(self.root)as journal:
            journal.update(self.item['id'],1,summary='实际修的是银色齿轮。')
            journal.update(self.item['id'],2,aliases=['小银轮'])
            erased=journal.capture('fiction-erased','另一段需要遗忘的虚构聊天。','不再保留这段内容。')
            journal.update(erased['id'],1,forget=True)
            rows=[dict(row)for row in journal.db.execute('SELECT * FROM episodes ORDER BY id')]
            history=journal.history(self.item['id'])
            journal.db.execute('PRAGMA user_version=0');journal.db.commit()
        with Journal(self.root)as journal:
            self.assertEqual([dict(row)for row in journal.db.execute('SELECT * FROM episodes ORDER BY id')],rows)
            self.assertEqual(journal.history(self.item['id']),history)
            self.assertIn('银色齿轮',journal.recall('小银轮'))
            self.assertNotIn('铜色齿轮',journal.recall('小银轮'))
            self.assertEqual(journal.get(erased['id'])['status'],'deleted')
        with Journal(self.root)as journal:self.assertEqual(journal.db.total_changes,0)

    def test_newer_database_schema_is_preserved_and_refused(self):
        with closing(sqlite3.connect(self.path))as writer:
            writer.execute('PRAGMA user_version=999')
            writer.execute('PRAGMA journal_mode=DELETE')
        with self.assertRaises(ValueError):Journal(self.root)
        with closing(sqlite3.connect(self.path))as reader:
            self.assertEqual(reader.execute('PRAGMA user_version').fetchone()[0],999)
            self.assertEqual(reader.execute('PRAGMA journal_mode').fetchone()[0],'delete')
            self.assertEqual(reader.execute('SELECT excerpt FROM episodes WHERE id=?',(self.item['id'],)).fetchone()[0],self.item['excerpt'])

    def test_failed_upgrade_rolls_back_and_closes_its_connection(self):
        with closing(sqlite3.connect(self.path))as writer:
            writer.execute('PRAGMA user_version=0')
            writer.execute('UPDATE episodes SET aliases=?,index_version=0 WHERE id=?',('invalid-json',self.item['id']))
            writer.commit()
        connect=sqlite3.connect;opened=[]
        def track(path,**kwargs):
            result=connect(path,**kwargs);opened.append(result);return result
        with patch('fish_journal.sqlite3.connect',side_effect=track):
            with self.assertRaises(ValueError):Journal(self.root)
        self.assertEqual(len(opened),1)
        with self.assertRaises(sqlite3.ProgrammingError):opened[0].execute('SELECT 1')
        with closing(connect(self.path))as reader:
            self.assertEqual(reader.execute('PRAGMA user_version').fetchone()[0],0)
            self.assertEqual(reader.execute('SELECT aliases FROM episodes WHERE id=?',(self.item['id'],)).fetchone()[0],'invalid-json')


if __name__=='__main__':unittest.main()
