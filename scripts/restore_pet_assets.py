#!/usr/bin/env python3
"""Restore the checksummed pet video Release without adding binaries to Git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def matches(path, expected):
    return path.is_file() and not path.is_symlink() and path.stat().st_size == expected['size'] and digest(path) == expected['sha256']


def restore(archive, metadata, destination):
    if not matches(archive, metadata):
        raise RuntimeError('素材包大小或 SHA-256 不符，未写入项目。')
    expected = metadata['files']
    # Do not extract paths, links, metadata or executable bits from an archive.
    with tempfile.TemporaryDirectory(prefix='pet-verify-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        with tarfile.open(archive, 'r:gz') as bundle:
            members = bundle.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)) or set(names) != set(expected):
                raise RuntimeError('素材包文件清单不符。')
            for member in members:
                if not member.isfile() or Path(member.name).name != member.name or member.size != expected[member.name]['size']:
                    raise RuntimeError('素材包包含不允许的条目。')
                target = staging / member.name
                with bundle.extractfile(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                if not matches(target, expected[member.name]):
                    raise RuntimeError('素材文件 SHA-256 不符。')
        # All files are verified before replacing any existing asset.
        destination.mkdir(parents=True, exist_ok=True)
        for name in expected:
            os.replace(staging / name, destination / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='使用本机已经下载的素材包')
    parser.add_argument('--repo', help='仓库迁移时覆盖下载位置，格式 owner/repo')
    parser.add_argument('--check', action='store_true', help='只检查本地视频，不下载、不修改')
    args = parser.parse_args()
    metadata = json.loads((ROOT / 'config/pet-assets.json').read_text())
    destination = ROOT / 'ui/public/pet'
    missing = [name for name, expected in metadata['files'].items() if not matches(destination / name, expected)]
    if not missing:
        print(f"桌宠素材完整：{len(metadata['files'])} 个文件通过 SHA-256 校验。")
        return
    if args.check:
        raise RuntimeError(f'{len(missing)} 个素材文件缺失或校验失败，请运行本脚本恢复素材。')
    if args.archive:
        restore(args.archive, metadata, destination)
    else:
        if not shutil.which('gh'):
            raise RuntimeError('请安装 GitHub CLI 并运行 gh auth login，或用 --archive 指定 Release 素材包。')
        with tempfile.TemporaryDirectory(prefix='bigfish-assets-') as temporary:
            subprocess.run(['gh', 'release', 'download', metadata['tag'], '--repo', args.repo or metadata['repository'], '--pattern', metadata['asset'], '--dir', temporary], check=True)
            restore(Path(temporary) / metadata['asset'], metadata, destination)
    print('桌宠素材已恢复，源码目录中的署名与素材许可继续适用。')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        raise SystemExit(str(error)) from None
