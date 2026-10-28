#!/bin/zsh
cd "${0:A:h}"
python3 scripts/service.py status
scripts/fish cron list
print '\n按回车关闭窗口。'
read
