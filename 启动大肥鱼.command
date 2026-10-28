#!/bin/zsh
cd "${0:A:h}"
if [[ -d "/Applications/大肥鱼.app" ]]; then
  exec /usr/bin/open "/Applications/大肥鱼.app"
fi
if [[ -d "$HOME/Applications/大肥鱼.app" ]]; then
  exec /usr/bin/open "$HOME/Applications/大肥鱼.app"
fi
exec python3 scripts/ui.py
