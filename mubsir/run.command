#!/bin/bash
# mubsir - double-click to start (macOS)
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "First run: setting up. This happens once."
  bash setup.sh || { echo "Setup failed."; read -r -p "Press Enter to close."; exit 1; }
fi
exec .venv/bin/python -m mubsir.webui
