"""Defaults for the two project routines; explicit per-job choices remain user-owned."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PROFILES={'fish-surf':['terminal','file','browser','web'],
          'fish-memory':['terminal','file','memory']}


def inspect_jobs(jobs):
    result=[]
    for name,tools in PROFILES.items():
        matches=[row for row in jobs if row.get('name')==name]
        if len(matches)>1:raise ValueError('Duplicate project routine: '+name)
        if matches:
            job=matches[0];current=job.get('enabled_toolsets')
            result.append({'id':job['id'],'name':name,'tools':list(tools),'change':current is None})
    return result


def apply_profiles(store):
    plan=inspect_jobs(store.load_jobs());result=[]
    for item in plan:
        def apply(jobs,index,job):
            # Recheck identity and the user's choice inside Hermes' own job-store lock.
            if job.get('name')!=item['name']or sum(row.get('name')==item['name']for row in jobs)!=1:raise ValueError('Routine changed during update.')
            if job.get('enabled_toolsets')is not None:return False
            updated=store.update_job(item['id'],{'enabled_toolsets':item['tools']})
            if not updated or updated.get('enabled_toolsets')!=item['tools']:raise ValueError('Routine tool profile was not saved.')
            return True
        changed=store._with_job(item['id'],apply)
        result.append({'name':item['name'],'updated':bool(changed)})
    return result


def runtime_argv(script,args):
    # Use the installation launcher contract: dependency generations are selected and leased
    # at child start. A cached bin/python path can disappear during dependency GC.
    os.environ['HERMES_HOME']=str(ROOT/'.hermes')
    sys.path.insert(0,str(ROOT/'.runtime/hermes-agent'))
    from hermes_cli._launchers import runtime_command as launch,resolve_store_python
    python=resolve_store_python(ROOT/'.runtime/hermes-agent')
    if python is None or not Path(python).is_file():raise ValueError('Initialize the local Hermes runtime before running this maintenance command.')
    code='sys.argv=['+repr(str(Path(script).resolve()))+',*sys.argv[1:]];runpy.run_path(sys.argv[0],run_name="__main__")'
    return launch(ROOT/'.runtime/hermes-agent',args,code=code,python=python,home=ROOT/'.hermes')


def runtime_environment():return {**os.environ,'HERMES_HOME':str(ROOT/'.hermes'),'HERMES_DISABLE_LAZY_INSTALLS':'1'}


def runtime_command(script,args):
    return subprocess.run(runtime_argv(script,args),cwd=ROOT,env=runtime_environment()).returncode
