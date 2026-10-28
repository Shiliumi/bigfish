#!/bin/zsh
cd "${0:A:h}"
python3 scripts/service.py start || exit 1
exec scripts/fish cron run fish-surf
