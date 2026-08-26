#!/bin/bash
# One-time setup. Needs no administrator rights: every component installs
# into your home directory or this folder.
set -e
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "[1/4] Installing uv (user-local)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[2/4] Python 3.11 + dependencies..."
uv python install 3.11
uv venv --python 3.11 .venv
uv pip install --python .venv -r requirements.txt

if [ ! -x ".mm-tess/bin/tesseract" ]; then
  echo "[3/4] Tesseract 5 (user-local, no admin)..."
  MM="$HOME/.local/mm/bin/micromamba"
  if [ ! -x "$MM" ]; then
    mkdir -p "$HOME/.local/mm"
    ( cd "$HOME/.local/mm" && curl -Ls https://micro.mamba.pm/api/micromamba/$(uname -s | tr '[:upper:]' '[:lower:]')-64/latest | tar -xj bin/micromamba )
  fi
  MAMBA_ROOT_PREFIX="$HOME/.local/mm" "$MM" create -y -q -p ./.mm-tess -c conda-forge tesseract
else
  echo "[3/4] Tesseract already present."
fi

echo "[4/4] Models and dictionaries..."
.venv/bin/python -m mubsir.fetch_models
echo
echo "Setup complete. Run ./run.command (macOS) or python -m mubsir.webui"
