#!/usr/bin/env bash
set -euo pipefail

# ── 0) Always run from this script’s directory ───────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

# ── 1) Create venv if needed ────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
  echo "🆕  Creating virtualenv in $VENV_DIR …"
  python -m venv "$VENV_DIR"
fi

# ── 2) Activate it (Windows or POSIX layout) ────────────────────────────────
if [[ -f "$VENV_DIR/Scripts/activate" ]]; then          # Windows
  # shellcheck disable=SC1090
  source "$VENV_DIR/Scripts/activate"
elif [[ -f "$VENV_DIR/bin/activate" ]]; then             # Linux/macOS/WSL
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
else
  echo "❌ Could not find activate script in $VENV_DIR" >&2
  exit 1
fi

# ── 3) Upgrade build tooling & install deps (skip pip cache) ────────────────
echo "⬆️  Upgrading pip & wheel …"
python -m pip install --upgrade pip wheel --no-cache-dir

echo "📦 Installing requirements.txt (no cache) …"
pip install --no-cache-dir -r requirements.txt

# ── 4) Load .env if present ─────────────────────────────────────────────────
if [[ -f ".env" ]]; then
  echo "🌿 Loading .env …"
  # shellcheck disable=SC2046
  export $(grep -E -v '^\s*#' .env | xargs)
fi

# ── 5) Launch the dev server ────────────────────────────────────────────────
echo "🚀  Starting uvicorn on http://localhost:8000/ …"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
