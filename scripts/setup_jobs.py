#!/usr/bin/env python3
"""Create or update the two Hermes routines without duplicating jobs."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FISH = str(ROOT / "scripts/fish")


def main():
    store = ROOT / ".hermes/cron/jobs.json"
    existing = json.loads(store.read_text()).get("jobs", []) if store.exists() else []
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
        if name == "fish-surf":
            command += ["--continuity"]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
