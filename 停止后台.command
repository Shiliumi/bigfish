#!/bin/zsh
cd "${0:A:h}"
python3 scripts/service.py stop
print '\n后台已停止。控制台可单独关闭。按回车关闭窗口。'
read
