#!/usr/bin/env python3
"""Offline, fresh-process comparison of platform defaults and project routine tool profiles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from job_tool_profiles import ROOT,PROFILES,runtime_command,runtime_argv,runtime_environment


def worker(name,variant):
    os.environ['HERMES_HOME']=str(ROOT/'.hermes')
    sys.path.insert(0,str(ROOT/'.runtime/hermes-agent'))
    from run_agent import AIAgent
    from hermes_cli.config import load_config
    from cron.scheduler import _resolve_cron_enabled_toolsets,_resolve_cron_disabled_toolsets
    from agent.system_prompt import build_system_prompt
    config=load_config();job={'name':name,'enabled_toolsets':None if variant=='platform_default'else PROFILES[name]}
    agent=AIAgent(model=config.get('model',{}).get('default')or'deepseek-flash',api_key='inspect-only',
        base_url='https://openrouter.ai/api/v1',enabled_toolsets=_resolve_cron_enabled_toolsets(job,config),
        disabled_toolsets=_resolve_cron_disabled_toolsets(config),platform='cron',quiet_mode=True,
        save_trajectories=False,skip_context_files=False,load_soul_identity=True,skip_memory=False,skip_background_review=True)
    try:
        prompt=build_system_prompt(agent);tools=agent.tools
        signatures={tool['function']['name']:hashlib.sha256(json.dumps(tool['function']['parameters'],sort_keys=True).encode()).hexdigest()for tool in tools}
        core={}
        if agent._memory_store:
            for key in ['memory','user']:
                block=agent._memory_store.format_for_system_prompt(key)or'';core[key]=hashlib.sha256(block.encode()).hexdigest()
        return {'job':name,'variant':variant,'system_chars':len(prompt),'system_bytes':len(prompt.encode()),
            'schema_bytes':len(json.dumps(tools,ensure_ascii=False).encode()),'tool_names':list(signatures),
            'provider_chars':len(agent._memory_manager.build_system_prompt())if agent._memory_manager else 0,
            'core_fingerprints':core,'parameter_fingerprints':signatures,
            'text_only_browser':any(tool['function']['name']=='browser_exec'and'Your model cannot view images'in tool['function'].get('description','')for tool in tools)}
    finally:
        if agent._memory_manager:agent._memory_manager.shutdown_all()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--worker',nargs=2,metavar=('JOB','VARIANT'),help=argparse.SUPPRESS);parser.add_argument('--driver',action='store_true',help=argparse.SUPPRESS);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.worker:
        name,variant=args.worker
        if name not in PROFILES or variant not in ['platform_default','project_profile']:parser.error('Unknown comparison profile.')
        print(json.dumps(worker(name,variant),ensure_ascii=False));return 0
    if not args.driver:return runtime_command(Path(__file__),['--driver']+(['--output',str(args.output)]if args.output else[]))
    rows=[]
    for name in PROFILES:
        pair=[]
        for variant in ['platform_default','project_profile']:
            result=subprocess.run(runtime_argv(Path(__file__),['--worker',name,variant]),cwd=ROOT,env=runtime_environment(),capture_output=True,text=True,timeout=45)
            if result.returncode:raise RuntimeError('Offline inspection failed; no provider request was made by this script.')
            pair.append(json.loads(result.stdout))
        before,after=pair
        required={'terminal','read_file','write_file','patch','search_files'}|({'browser_exec','web_search','web_extract'}if name=='fish-surf'else{'memory'})
        assert required.issubset(after['tool_names']),'Required task capability missing.'
        assert before['core_fingerprints']==after['core_fingerprints'],'Core memory/profile changed across tool selection.'
        assert all(before['parameter_fingerprints'][key]==after['parameter_fingerprints'][key]for key in required),'Retained tool parameters changed.'
        if name=='fish-surf':assert before['text_only_browser']==after['text_only_browser'],'Browser model-capability hint changed.'
        for row in pair:row.pop('core_fingerprints');row.pop('parameter_fingerprints')
        rows.extend(pair)
    report={'scope':'Offline construction only, dummy credentials, no generated answers or token/billing savings claim. Fresh process per variant; current configured persona never printed.',
            'core_memory_preserved':True,'required_parameters_preserved':True,'rows':rows}
    if args.output:
        if not args.output.resolve().is_relative_to((ROOT/'.setup').resolve()):parser.error('Save local inspection reports inside ignored .setup/.')
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
