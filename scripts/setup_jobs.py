#!/usr/bin/env python3
"""Create or update the two Hermes routines without duplicating jobs."""
import json
from pathlib import Path
import subprocess
from datetime import datetime
import shutil

ROOT = Path(__file__).resolve().parents[1]
FISH = str(ROOT / "scripts/fish")


def main():
    store = ROOT / ".hermes/cron/jobs.json"
    existing = json.loads(store.read_text()).get("jobs", []) if store.exists() else []
    if store.exists():
        backup = ROOT / 'backups/automation' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True, mode=0o700)
        shutil.copy2(store, backup / 'jobs.json')
    wrappers = ROOT / '.hermes/scripts'
    wrappers.mkdir(parents=True, exist_ok=True)
    for name, schedule, filename in [
        ("fish-surf", "0 9,12,15,18,21 * * *", "surf-prompt.txt"),
        ("fish-memory", "30 22 * * *", "memory-prompt.txt"),
    ]:
        matches = [job for job in existing if job.get("name") == name]
        if len(matches) > 1:
            raise RuntimeError(f"发现多个 {name} 任务，请先在控制台去重。")
        prompt = (ROOT / "config" / filename).read_text()
        if matches:
            command = [FISH, "cron", "edit", matches[0]["id"], "--schedule", schedule, "--prompt", prompt]
        else:
            command = [FISH, "cron", "create", schedule, prompt, "--name", name]
        command += ["--workdir", str(ROOT), "--deliver", "local"]
        mode = 'surf' if name == 'fish-surf' else 'memory'
        wrapper = wrappers / f'fish-{mode}-gate.py'
        wrapper.write_text('import runpy,sys,json\ntry:\n'
                           + '    root = ' + repr(str(ROOT)) + '\n'
                           + '    sys.path.insert(0, root + "/scripts")\n'
                           + '    sys.argv = [root + "/scripts/activity_gate.py", ' + repr(mode) + ']\n'
                           + '    runpy.run_path(sys.argv[0], run_name="__main__")\n'
                           + 'except BaseException:\n'
                           + '    print(json.dumps({"wakeAgent": False, "error": True, "reason": "预检启动失败，本次不调用模型。"}, ensure_ascii=False))\n')
        wrapper.chmod(0o600)
        command += ['--script', wrapper.name]
        if matches:
            command += ["--no-continuity"]
        subprocess.run(command, check=True)
    subprocess.run([shutil.which('python3')or'python3',str(ROOT/'scripts/install_job_tools.py')],check=True)


if __name__ == "__main__":
    main()
