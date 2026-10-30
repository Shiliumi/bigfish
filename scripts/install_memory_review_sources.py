#!/usr/bin/env python3
"""Upgrade known memory-review source and completion steps; retain custom choices."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from job_tool_profiles import ROOT, runtime_command

INTRO = '你是大肥鱼，这次只整理预检交给你的增量经历，不从头扫描今天或全部历史。'
OLD_STEP = '1. 预检上下文中的 snapshot_id 是本批不可变来源清单。运行 `python3 scripts/activity_gate.py review --snapshot 实际snapshot_id`，只处理返回的 reports、observations、episodes、preference_events。没有快照就结束，不另造快照或虚构经历。不额外上网，不新增任务。'
NEW_STEP = '1. 预检上下文中的 snapshot_id 是本批不可变来源清单。运行 `python3 scripts/activity_gate.py review --snapshot 实际snapshot_id`，只处理本批 reports、observations、episodes、preference_events。episodes 返回完整已存原话或当前更正，不按自动前缀摘要推断事实；read_required=true 的项目逐条按其 command 取出完整当前来源，再核对。来源当初存入不全、举例、玩笑、假设或未确认时不升级成用户事实。工具输出若截断，读取工具保存的完整文件核对余下来源，不把未展示内容当已读。没有快照就结束，不另造快照或虚构经历。不额外上网，不新增任务。'
OLD_VERIFY = '3. 本批有新观察、共同经历或偏好事件时，按 config/PERSONALITY_GROWTH.md 读取 personality.py trials，核对试行、后续选择与反例。必要时才读取对应来源；有充分依据再 apply 或 retire，不直接跳过试行。至少三天且有试行后的真实跟进，同日不能凑出成熟性格。没有新变化很正常。未完好奇不是固定人格。不绕过脚本改 SOUL 的其他部分。'
NEW_VERIFY = '3. 本批有新观察、共同经历或偏好事件时，按 config/PERSONALITY_GROWTH.md 运行 `python3 scripts/personality.py trials`，核对试行、后续选择与反例。必要时才读取对应来源；有充分依据再 apply 或 retire，不直接跳过试行。若执行过 feedback/apply/retire，全部完成后，在写报告和 commit 之前再用同一 trials 命令核对一次最新结果；没有变化不重复查。现有命令可返回当前状态，不用内联 Python 或另读 trials.json/profile.json 自编检查。至少三天且有试行后的真实跟进，同日不能凑出成熟性格。没有新变化很正常。未完好奇不是固定人格。不绕过脚本改 SOUL 的其他部分。'
OLD_FINISH = '5. 复查保存和写入结果，再运行 `python3 scripts/activity_gate.py commit --snapshot 实际snapshot_id --report 实际报告相对路径`。只有成功才算本批完成。提交失败不自行改游标，下次会重新取得未消费的来源。remaining 代表后续批次，不要为了清空积压无限循环调用。'
NEW_FINISH = '5. 报告已保存、实际发生的变更已核对后，运行 `python3 scripts/activity_gate.py commit --snapshot 实际snapshot_id --report 实际报告相对路径`。返回 ok=true 即本批完成（包括 already_committed=true），直接结束本轮；不要在提交后继续检查人格状态、重复读取 JSON、运行内联脚本或追加反馈。提交失败不自行改游标，下次会重新取得未消费的来源。remaining 代表后续批次，不要为了清空积压无限循环调用。'


def upgrade_prompt(prompt):
    if not isinstance(prompt, str): return None
    lines = prompt.splitlines(keepends=True)
    if len(lines) < 2 or lines[0].rstrip('\r\n') != INTRO: return None
    first = lines[1].rstrip('\r\n')
    if first not in (OLD_STEP, NEW_STEP): return None
    if first == OLD_STEP:
        if sum(line.rstrip('\r\n') == OLD_STEP for line in lines) != 1: return None
        lines[1] = NEW_STEP + lines[1][len(first):]
    if len(lines) > 5:
        verify, finish = (lines[index].rstrip('\r\n') for index in (3, 5))
        # Treat verification and completion as one protocol pair. A custom or
        # quoted step must not silently lose its user's completion checks.
        if verify in (OLD_VERIFY, NEW_VERIFY) and finish in (OLD_FINISH, NEW_FINISH) and all(sum(line.rstrip('\r\n') == text for line in lines) == 1 for text in (verify, finish)):
            for index, old, new in [(3, verify, NEW_VERIFY), (5, finish, NEW_FINISH)]:
                lines[index] = new + lines[index][len(old):]
    return ''.join(lines)


def inspect_jobs(jobs):
    matches = [row for row in jobs if row.get('name') == 'fish-memory']
    if len(matches) > 1: raise ValueError('记忆整理任务重名，未修改。')
    if not matches: return None
    job = matches[0]; updated = upgrade_prompt(job.get('prompt'))
    return {'id': job['id'], 'prompt': job.get('prompt'), 'updated': updated,
            'change': updated is not None and updated != job.get('prompt')}


def apply_update(store):
    plan = inspect_jobs(store.load_jobs())
    if plan is None: return {'updated': False, 'reason': 'missing'}
    if not plan['change']: return {'updated': False, 'reason': 'custom_prompt' if plan['updated'] is None else 'already_current'}
    def apply(jobs, index, job):
        if job.get('name') != 'fish-memory' or sum(row.get('name') == 'fish-memory' for row in jobs) != 1 or job.get('prompt') != plan['prompt']:
            raise ValueError('记忆整理提示刚被修改，保留当前内容，请重新核对。')
        result = store.update_job(job['id'], {'prompt': plan['updated']})
        if not result or result.get('prompt') != plan['updated']: raise ValueError('记忆整理提示未保存，请核对任务。')
        return {'updated': True}
    result = store._with_job(plan['id'], apply)
    if result is None: raise ValueError('记忆整理任务刚被移除，未创建替代任务。')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true'); parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.worker: return runtime_command(Path(__file__), ['--worker'] + (['--dry-run'] if args.dry_run else []))
    sys.path.insert(0, str(ROOT/'.runtime/hermes-agent'))
    from cron import jobs
    # Select this project's native job store explicitly, including in isolated checks.
    with jobs.use_cron_store(ROOT/'.hermes'):
        plan = inspect_jobs(jobs.load_jobs())
        if args.dry_run:
            print(json.dumps({'would_update': bool(plan and plan['change']), 'custom_prompt': bool(plan and plan['updated'] is None)})); return 0
        if plan and plan['change']:
            folder = ROOT/'backups/memory-review-sources'/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
            folder.mkdir(parents=True, mode=0o700); shutil.copy2(ROOT/'.hermes/cron/jobs.json', folder/'jobs.json')
        print(json.dumps(apply_update(jobs), ensure_ascii=False)); return 0


if __name__ == '__main__': raise SystemExit(main())
