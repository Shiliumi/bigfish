#!/bin/zsh
cd "${0:A:h}"
scripts/fish cron pause fish-surf
scripts/fish cron pause fish-memory
print '\n已暂停自动活动。正在执行的任务会继续到本轮结束。按回车关闭窗口。'
read
