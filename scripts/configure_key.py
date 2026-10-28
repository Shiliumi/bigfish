#!/usr/bin/env python3
"""Configure DeepSeek locally without putting credentials in shell history."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".hermes" / ".env"


def read_key():
    if not ENV.exists():
        return os.environ.get("DEEPSEEK_API_KEY", "")
    for line in ENV.read_text().splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            return line.partition("=")[2].strip().strip("\"'")
    return ""


def verify(key):
    req = urllib.request.Request(
        "https://api.deepseek.com/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            models = json.load(response)
        return [model["id"] for model in models.get("data", [])]
    except urllib.error.HTTPError as error:
        messages = {401: "密钥无效，请检查后重新输入。", 402: "DeepSeek 账户余额不足。", 429: "请求过于频繁，请稍后重试。"}
        raise RuntimeError(messages.get(error.code, f"DeepSeek 返回 HTTP {error.code}。")) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("暂时无法连接 DeepSeek，请检查网络后重试。") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialog", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        key = read_key()
        if not key:
            print("尚未配置 DeepSeek API Key。")
            return 2
    elif args.dialog:
        result = subprocess.run(
            ["osascript", "-e", 'display dialog "请在本机输入 DeepSeek 官方 API Key。密钥仅保存到此项目的私有配置文件，不会显示在聊天中。" default answer "" with hidden answer buttons {"取消", "保存并验证"} default button "保存并验证" with title "配置大肥鱼"', "-e", "text returned of result"],
            capture_output=True, text=True,
        )
        if result.returncode:
            print("已取消配置；可以稍后双击「配置模型.command」。")
            return 2
        key = result.stdout.strip()
    else:
        key = getpass.getpass("DeepSeek API Key（输入不显示）: ").strip()
    if not key or not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
        print("未输入有效格式的 API Key。")
        return 2
    try:
        models = verify(key)
    except RuntimeError as error:
        print(str(error))
        return 1
    if not args.check:
        ENV.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        content = ENV.read_text() if ENV.exists() else ""
        lines = [line for line in content.splitlines() if not line.startswith("DEEPSEEK_API_KEY=")]
        lines.append(f"DEEPSEEK_API_KEY={key}")
        fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write("\n".join(lines) + "\n")
        ENV.chmod(0o600)
    print("DeepSeek 密钥验证成功。可用模型：" + ", ".join(models))
    return 0


if __name__ == "__main__":
    sys.exit(main())
