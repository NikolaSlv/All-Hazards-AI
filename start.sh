#!/usr/bin/env bash
set -euo pipefail

# Always run from the script’s directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

# 1) Create venv if needed
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtualenv in $VENV_DIR…"
  python -m venv "$VENV_DIR"
fi

# 2) Activate it
if [ -f "$VENV_DIR/Scripts/activate" ]; then
  source "$VENV_DIR/Scripts/activate"
elif [ -f "$VENV_DIR/bin/activate" ]; then
  source "$VENV_DIR/bin/activate"
else
  echo "Could not find activate script in $VENV_DIR" >&2
  exit 1
fi

# 3) Install/upgrade pip and then requirements
echo "Upgrading pip via python -m pip…"
python -m pip install --upgrade pip

echo "Installing requirements.txt…"
pip install -r requirements.txt

# 4) Load .env if present
if [ -f ".env" ]; then
  echo "Loading .env…"
  export $(grep -Ev '^\s*#' .env | xargs)
fi

# 5) Run the server
echo "🚀 Starting uvicorn on http://localhost:8000/ …"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
