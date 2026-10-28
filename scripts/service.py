#!/usr/bin/env python3
"""Manage this project's macOS login service with unprotected launchd log paths."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LABEL = "local.aifish.gateway"
DOMAIN = f"gui/{os.getuid()}"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
LOGS = Path.home() / "Library/Logs/AI-Fish"


def check_owner():
    if PLIST.exists():
        existing = plistlib.loads(PLIST.read_bytes())
        if existing.get("EnvironmentVariables", {}).get("HERMES_HOME") != str(ROOT / ".hermes"):
            raise RuntimeError("此服务名已由另一个项目使用，未修改它。")


def loaded():
    return subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True).returncode == 0


def wait_ready():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True, text=True)
        if "\tstate = running" in state.stdout:
            status = subprocess.run([str(ROOT / "scripts/fish"), "cron", "status"], capture_output=True, text=True, timeout=10)
            if "Gateway is running" in status.stdout:
                return
        time.sleep(0.5)
    raise RuntimeError("后台尚未就绪，请查看 ~/Library/Logs/AI-Fish/ 中的日志。")


def definition():
    launcher = str(ROOT / ".runtime/hermes-agent/.hermes/bin/hermes")
    stdout = LOGS / "gateway.log"
    stderr = LOGS / "gateway.error.log"
    command = [launcher, "--run-module", "hermes_cli.stderr_timestamp", "--error-log", str(stderr), "--", launcher, "gateway", "run", "--external-supervisor"]
    shell = f"exec {shlex.join(command)} >> {shlex.quote(str(stdout))} 2>> {shlex.quote(str(stderr))}"
    js = 'ObjC.import("stdlib"); ' + f"const status=$.system({json.dumps(shell)}); " + "const signal=status & 127; $.exit(status === -1 ? 1 : signal === 0 ? (status >> 8) & 255 : 128 + signal);"
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/osascript", "-l", "JavaScript", "-e", js],
        "WorkingDirectory": str(Path.home()),
        "StandardOutPath": str(stdout),
        "StandardErrorPath": str(stderr),
        "EnvironmentVariables": {
            "HERMES_HOME": str(ROOT / ".hermes"),
            "HERMES_SUPERVISED_CHILD": "1",
            "HERMES_TIMEZONE": "Asia/Shanghai",
            "TZ": "Asia/Shanghai",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Background",
        "SoftResourceLimits": {"NumberOfFiles": 4096},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "start", "stop", "status", "uninstall"])
    action = parser.parse_args().action
    check_owner()
    if action == "install":
        if loaded():
            raise RuntimeError("服务正在运行；如需重新安装，请先停止服务。")
        LOGS.mkdir(mode=0o700, parents=True, exist_ok=True)
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_bytes(plistlib.dumps(definition()))
        PLIST.chmod(0o600)
        subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)], check=True)
        wait_ready()
        print("大肥鱼后台已安装，将在登录后自动启动。")
    elif action == "start":
        if not PLIST.exists():
            raise RuntimeError("请先运行 python3 scripts/service.py install。")
        if not loaded():
            subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)], check=True)
        subprocess.run(["launchctl", "kickstart", f"{DOMAIN}/{LABEL}"], check=True)
        wait_ready()
        print("大肥鱼后台已启动。")
    elif action in {"stop", "uninstall"}:
        if loaded():
            subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], check=True)
        if action == "uninstall" and PLIST.exists():
            PLIST.unlink()
        print("大肥鱼后台已停止。" if action == "stop" else "已移除大肥鱼登录服务，数据仍保留。")
    else:
        result = subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True, text=True)
        if result.returncode:
            print("大肥鱼后台未运行。")
            return
        print("大肥鱼登录服务：", flush=True)
        for line in result.stdout.splitlines():
            if any(key in line for key in ["state =", "pid =", "last exit code ="]):
                print(line.strip())
        subprocess.run([str(ROOT / "scripts/fish"), "cron", "status"], check=True)


if __name__ == "__main__":
    main()
