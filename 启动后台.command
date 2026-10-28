#!/bin/zsh
cd "${0:A:h}"
python3 scripts/service.py start
print '\n按回车关闭窗口。'
read
