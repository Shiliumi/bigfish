#!/usr/bin/env python3
"""Start the local Bigfish UI and its existing Hermes transport on demand."""
import argparse
from pathlib import Path
import shutil
import os
import secrets
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:9120"


def reachable(url, marker):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return marker in response.read().decode("utf-8", errors="replace")
    except (OSError, TimeoutError):
        return False


def wait_for(url, marker):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if reachable(url, marker):
            return
        time.sleep(0.5)
    raise RuntimeError("界面没有及时启动，请查看 .setup/ 中的日志。")


def start():
    subprocess.run([shutil.which("python3") or "/opt/homebrew/bin/python3", str(ROOT / "scripts/service.py"), "start"], check=True)
    logs = ROOT / ".setup"
    logs.mkdir(exist_ok=True)
    credential = logs / "hermes-api.key"
    if not credential.exists():
        descriptor = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output: output.write(secrets.token_hex(32) + "\n")
    credential.chmod(0o600)
    token = credential.read_text().strip()
    def backend_ready():
        try:
            request = urllib.request.Request("http://127.0.0.1:9119/api/status?profile=default", headers={"X-Hermes-Session-Token": token})
            with urllib.request.urlopen(request, timeout=3) as response: return response.status == 200
        except (OSError, TimeoutError): return False
    if not backend_ready():
        with (logs / "hermes-api.log").open("a") as output:
            environment = dict(os.environ, HERMES_DASHBOARD_SESSION_TOKEN=token)
            subprocess.Popen([str(ROOT / "scripts/fish"), "serve", "--isolated", "--host", "127.0.0.1", "--port", "9119"], cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if backend_ready(): break
            time.sleep(0.5)
        else: raise RuntimeError("Hermes 内部接口没有及时启动，请查看 .setup/hermes-api.log。")
    if not reachable(URL + "/health", "bigfish-desktop"):
        if not (ROOT / "ui/dist/index.html").is_file():
            raise RuntimeError("请先在项目中执行 npm run build --prefix ui。")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("找不到 Node.js，请先安装 Node.js。")
        with (logs / "studio-local.log").open("a") as output:
            subprocess.Popen([node, str(ROOT / "ui/server/index.mjs")], cwd=ROOT / "ui", stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        wait_for(URL + "/health", "bigfish-desktop")
    print("大肥鱼应用内部服务已就绪。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    start()
    if not args.no_open:
        app = Path("/Applications/大肥鱼.app")
        if not app.exists(): app = Path.home() / "Applications/大肥鱼.app"
        if not app.exists(): raise RuntimeError("请先运行 scripts/build_app.py 安装 Mac 应用。")
        subprocess.run(["/usr/bin/open", str(app)], check=True)
