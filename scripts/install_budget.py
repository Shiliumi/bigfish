#!/usr/bin/env python3
"""Install the project budget extension, preserving configuration on upgrade."""
from pathlib import Path
from datetime import datetime
import shutil
import subprocess
from fish_budget import Budget

ROOT=Path(__file__).resolve().parents[1]


def main():
    destination=ROOT/'.hermes/plugins/fish-budget'
    marker=destination/'.bigfish-installed'
    first=not marker.exists()
    if destination.exists():
        backup=ROOT/'backups/budget-adapter'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(destination,backup)
    destination.mkdir(parents=True,exist_ok=True)
    for name in ('__init__.py','plugin.yaml'):shutil.copy2(ROOT/'plugins/fish-budget'/name,destination/name)
    shutil.copy2(ROOT/'scripts/fish_budget.py',destination/'budget.py')
    with Budget(ROOT) as ledger:
        if first:
            setting=ledger.settings();ledger.save({**setting,'enabled':True})
    if first:
        config=ROOT/'.hermes/config.yaml'
        if config.exists():
            backup=ROOT/'backups/budget-adapter'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup.mkdir(parents=True,mode=0o700);shutil.copy2(config,backup/'config.yaml')
        subprocess.run([str(ROOT/'scripts/fish'),'plugins','enable','fish-budget'],check=True)
        marker.write_text('installed\n');marker.chmod(0o600)
    print('后台鱼粮适配已安装；首次默认每日 200 万总 token，已有额度设置保留。需重启内部接口和后台服务。')


if __name__=='__main__':main()
