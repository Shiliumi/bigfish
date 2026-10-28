#!/bin/zsh
cd "${0:A:h}"
scripts/fish cron resume fish-surf
scripts/fish cron resume fish-memory
print '\n已恢复自动活动。按回车关闭窗口。'
read
