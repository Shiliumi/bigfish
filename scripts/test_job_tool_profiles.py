import copy
import unittest
from job_tool_profiles import inspect_jobs,apply_profiles,PROFILES


class Store:
    def __init__(self,rows):self.rows=copy.deepcopy(rows);self.saved=[];self.before_apply=None;self.locked=False
    def load_jobs(self):return copy.deepcopy(self.rows)
    def _with_job(self,ident,callback):
        if self.before_apply:self.before_apply(self.rows);self.before_apply=None
        for index,row in enumerate(self.rows):
            if row['id']==ident:
                self.locked=True
                try:return callback(self.rows,index,row)
                finally:self.locked=False
    def update_job(self,ident,updates):
        assert self.locked
        row=next(row for row in self.rows if row['id']==ident);row.update(copy.deepcopy(updates));self.saved.append(copy.deepcopy(updates));return row


class JobToolsTest(unittest.TestCase):
    def setUp(self):
        self.rows=[{'id':'surf','name':'fish-surf','prompt':'unchanged fictional task','schedule':{'kind':'cron'},'model':'fixture-model','enabled_toolsets':None},
                   {'id':'memory','name':'fish-memory','enabled_toolsets':None},
                   {'id':'custom','name':'fish-study-buddy','enabled_toolsets':['terminal']}]
    def test_only_inherited_project_profiles_change_and_repeated_install_does_not_rewrite(self):
        store=Store(self.rows);result=apply_profiles(store);self.assertTrue(all(row['updated']for row in result))
        for before,after in zip(self.rows,store.rows):
            if before['name']in PROFILES:self.assertEqual(after,{**before,'enabled_toolsets':PROFILES[before['name']]})
            else:self.assertEqual(before,after)
        self.assertEqual(len(store.saved),2);self.assertFalse(any(row['updated']for row in apply_profiles(store)));self.assertEqual(len(store.saved),2)
    def test_explicit_custom_and_empty_toolsets_stay_intact(self):
        self.rows[0]['enabled_toolsets']=[];self.rows[1]['enabled_toolsets']=['terminal','file'];store=Store(self.rows)
        self.assertFalse(any(row['updated']for row in apply_profiles(store)));self.assertEqual(store.rows,self.rows)
    def test_user_choice_or_name_change_after_planning_is_rechecked_under_store_lock(self):
        store=Store(self.rows);store.before_apply=lambda rows:rows[0].update(enabled_toolsets=['terminal'])
        apply_profiles(store);self.assertEqual(store.rows[0]['enabled_toolsets'],['terminal'])
        store=Store(self.rows);store.before_apply=lambda rows:rows[0].update(name='another-task')
        with self.assertRaises(ValueError):apply_profiles(store)
        self.assertFalse(store.saved)
    def test_duplicate_names_abort_before_updates_and_missing_routines_are_not_created(self):
        rows=self.rows+[{'id':'duplicate','name':'fish-memory'}];store=Store(rows)
        with self.assertRaises(ValueError):apply_profiles(store)
        self.assertFalse(store.saved);self.assertEqual(inspect_jobs([self.rows[-1]]),[])


if __name__=='__main__':unittest.main()
