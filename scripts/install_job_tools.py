#!/usr/bin/env python3
"""Narrow inherited toolsets of project routines, preserving explicit choices and all other jobs."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from job_tool_profiles import ROOT,inspect_jobs,apply_profiles,runtime_command


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    if not args.worker:return runtime_command(Path(__file__),['--worker']+(['--dry-run']if args.dry_run else[]))
    sys.path.insert(0,str(ROOT/'.runtime/hermes-agent'))
    from cron import jobs
    from hermes_constants import set_hermes_home_override,reset_hermes_home_override
    token=set_hermes_home_override(ROOT/'.hermes')
    try:
        plan=inspect_jobs(jobs.load_jobs())
        if args.dry_run:print(json.dumps([{'name':row['name'],'would_update':row['change'],'tools':row['tools']}for row in plan]));return 0
        if any(row['change']for row in plan):
            folder=ROOT/'backups/job-tools'/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f');folder.mkdir(parents=True,mode=0o700)
            shutil.copy2(ROOT/'.hermes/cron/jobs.json',folder/'jobs.json')
        print(json.dumps(apply_profiles(jobs),ensure_ascii=False));return 0
    finally:reset_hermes_home_override(token)


if __name__=='__main__':raise SystemExit(main())
