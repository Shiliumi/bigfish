#!/usr/bin/env python3
"""Build and install the local native macOS app; retain the project as its data directory."""
from pathlib import Path
import plistlib
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "desktop/build"
BUNDLE = BUILD / "大肥鱼.app"
INSTALL = Path("/Applications/大肥鱼.app") if os.access("/Applications", os.W_OK) else Path.home() / "Applications/大肥鱼.app"


def main():
    resources = BUNDLE / "Contents/Resources"
    executable = BUNDLE / "Contents/MacOS/Bigfish"
    executable.parent.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    iconset = BUILD / "AppIcon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    source = ROOT / "desktop/assets/character.png"
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            target = iconset / f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            subprocess.run(["sips", "-z", str(size * scale), str(size * scale), str(source), "--out", str(target)], check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(resources / "AppIcon.icns")], check=True)
    shutil.copy2(source, resources / "character.png")
    if (resources / "pet").exists(): shutil.rmtree(resources / "pet")
    shutil.copytree(ROOT / "ui/public/pet", resources / "pet", ignore=shutil.ignore_patterns("*.webm"))
    for name in ("ATTRIBUTION.md", "LICENSE-ASSETS.txt"):
        shutil.copy2(ROOT / "desktop/assets" / name, resources / name)
    info = {
        "CFBundleName": "大肥鱼", "CFBundleDisplayName": "大肥鱼", "CFBundleExecutable": "Bigfish",
        "CFBundleIdentifier": "local.aifish.desktop", "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.8.0", "CFBundleVersion": "10", "CFBundleIconFile": "AppIcon",
        "CFBundleURLTypes": [{"CFBundleURLName":"local.aifish.desktop", "CFBundleURLSchemes":["bigfish"]}],
        "LSMinimumSystemVersion": "13.0", "NSHighResolutionCapable": True,
        "NSDocumentsFolderUsageDescription": "大肥鱼需要读写本项目中的记忆、探索笔记和本地配置。",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "FishProjectRoot": str(ROOT), "NSHumanReadableCopyright": "鲸鱼娘图标：可以叫我云大人 / 雾雪 · kiriyuki.com · 个人非商业使用",
    }
    (BUNDLE / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    subprocess.run(["xcrun", "swiftc", "-swift-version", "5", "-O", str(ROOT / "desktop/Bigfish.swift"), str(ROOT / "desktop/FloatingPet.swift"), str(ROOT / "desktop/PetBehavior.swift"), str(ROOT / "desktop/PetDock.swift"), str(ROOT / "desktop/PetGreeting.swift"), str(ROOT / "desktop/PetPeek.swift"), "-o", str(executable), "-framework", "Cocoa", "-framework", "WebKit", "-framework", "UserNotifications", "-framework", "AVFoundation", "-framework", "QuartzCore"], check=True)
    executable.chmod(0o755)
    subprocess.run(["codesign", "--force", "--sign", "-", "--identifier", "local.aifish.desktop", str(BUNDLE)], check=True)
    INSTALL.parent.mkdir(parents=True, exist_ok=True)
    if INSTALL.exists():
        current = plistlib.loads((INSTALL / "Contents/Info.plist").read_bytes())
        if current.get("FishProjectRoot") != str(ROOT):
            raise RuntimeError("应用目录已有其他大肥鱼，未覆盖。")
        shutil.rmtree(INSTALL)
    shutil.copytree(BUNDLE, INSTALL)
    shortcut = ROOT / "大肥鱼.app"
    if not shortcut.exists() and not shortcut.is_symlink():
        shortcut.symlink_to(INSTALL)
    login = Path.home() / "Library/LaunchAgents/local.aifish.desktop.plist"
    if login.exists() and str(INSTALL) not in str(plistlib.loads(login.read_bytes())):
        raise RuntimeError("登录项名称已被其他应用占用，未修改。")
    login.parent.mkdir(parents=True, exist_ok=True)
    login.write_bytes(plistlib.dumps({"Label": "local.aifish.desktop", "ProgramArguments": ["/usr/bin/open", "-g", str(INSTALL), "--args", "--background"], "RunAtLoad": True, "LimitLoadToSessionType": "Aqua"}))
    login.chmod(0o600)
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", str(INSTALL)], check=True)
    print(f"已安装：{INSTALL}")
    print("登录后会在后台运行；关闭窗口继续接收来信，菜单中可退出。")


if __name__ == "__main__":
    main()
