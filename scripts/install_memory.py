#!/usr/bin/env python3
"""Install the project-owned memory adapter without editing Hermes upstream."""
import argparse
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    destination = ROOT / '.hermes/plugins/fish-episodes'
    if destination.exists():
        backup = ROOT / 'backups/memory-adapter' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(destination, backup)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('__init__.py', 'plugin.yaml'):
        shutil.copy2(ROOT / 'plugins/fish-episodes' / name, destination / name)
    shutil.copy2(ROOT / 'scripts/fish_journal.py', destination / 'journal.py')
    shutil.copy2(ROOT / 'scripts/personality.py', destination / 'growth.py')
    shutil.copy2(ROOT / 'scripts/fish_conversation.py', destination / 'conversation.py')
    shutil.copy2(ROOT / 'scripts/fish_matters.py', destination / 'matters.py')
    semantic=destination/'semantic';semantic.mkdir(exist_ok=True)
    (semantic/'__init__.py').write_text('"""Project-bound optional semantic helpers."""\n')
    for name in ('fish_journal.py','fish_semantic_cache.py','fish_embeddings.py','fish_embedding_process.py','fish_embedding_worker.py','fish_semantic_recall.py'):
        shutil.copy2(ROOT/'scripts'/name,semantic/name)
    if args.activate:
        config = ROOT / '.hermes/config.yaml'
        if config.exists():
            backup = ROOT / 'backups/memory-adapter' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-config')
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config, backup / 'config.yaml')
        subprocess.run([str(ROOT / 'scripts/fish'), 'config', 'set', 'memory.provider', 'fish-episodes'], check=True)
    print('本地回忆适配已安装；重启 Hermes 内部接口并开启新对话后生效。')


if __name__ == '__main__':
    main()
