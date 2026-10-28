#!/usr/bin/env python3
"""Install project-owned persona and settings, keeping secrets and memories intact."""
from pathlib import Path
import shutil
import os
import re
import subprocess
import json
from personality import render_style

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".hermes"


def main():
    for name in ["memories", "logs", "cron", "skills"]:
        (STATE / name).mkdir(parents=True, exist_ok=True)
    for name in ["reports", "data", "backups"]:
        (ROOT / name).mkdir(exist_ok=True)
    STATE.chmod(0o700)
    current = STATE / "config.yaml"
    version = re.search(r"^_config_version:\s*(\d+)\s*$", current.read_text(), re.M) if current.exists() else None
    config = (ROOT / "config/config.yaml").read_text().replace("__PROJECT_ROOT__", str(ROOT))
    if version:
        config = "_config_version: " + version.group(1) + "\n" + config
    (STATE / "config.yaml").write_text(config)
    soul = (ROOT / "config/SOUL.md").read_text()
    profile = ROOT / "data/personality/profile.json"
    if profile.exists():
        soul = render_style(soul, json.loads(profile.read_text()).get("traits", []))
    (STATE / "SOUL.md").write_text(soul)
    seeds = {
        "MEMORY.md": "我是大肥鱼，运行在用户的 Mac。工作目录中的 INTERESTS.md 是冲浪主题配置。详细见闻在 reports/，已读链接在 data/surf-state.json；核心记忆只保留简短、经核实、以后有用的信息。",
        "USER.md": "用户使用中文交流，想拥有可以自动更新长期记忆、使用本地浏览器自主冲浪的 AI 大肥鱼。用户选择 DeepSeek 官方 API，希望以爸爸和爱冲浪的小鲸鱼女儿的关系相处。",
    }
    for name, text in seeds.items():
        target = STATE / "memories" / name
        if not target.exists():
            target.write_text(text + "\n")
    surf_state = ROOT / "data/surf-state.json"
    if not surf_state.exists():
        surf_state.write_text('{"version": 1, "visited": []}\n')
    env = STATE / ".env"
    lines = env.read_text().splitlines() if env.exists() else []
    if not any(line.startswith("HERMES_TIMEZONE=") for line in lines):
        lines.append("HERMES_TIMEZONE=Asia/Shanghai")
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write("\n".join(lines) + "\n")
    env.chmod(0o600)
    launcher = ROOT / ".runtime/hermes-agent/.hermes/bin/hermes"
    if launcher.exists():
        subprocess.run([str(ROOT / "scripts/fish"), "config", "migrate"], check=True, stdout=subprocess.DEVNULL)
    print("大肥鱼人设、模型、记忆与冲浪配置已安装。")


if __name__ == "__main__":
    main()
