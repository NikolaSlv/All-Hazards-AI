#!/usr/bin/env bash
set -euo pipefail

# ── 1) Ensure we’re in the repo root ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

# ── 2) Require existing venv ────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Error: Virtual environment not found at $VENV_DIR. Please run start.sh first." >&2
  exit 1
fi

# ── 3) Activate your existing venv ───────────────────────────────────────────
if [[ -f "$VENV_DIR/Scripts/activate" ]]; then
  source "$VENV_DIR/Scripts/activate"
elif [[ -f "$VENV_DIR/bin/activate" ]]; then
  source "$VENV_DIR/bin/activate"
else
  echo "Error: Couldn't find the activate script in $VENV_DIR" >&2
  exit 1
fi

# ── 4) Load .env if present ──────────────────────────────────────────────────
if [[ -f ".env" ]]; then
  echo "Loading environment variables from .env"
  set -a
  source .env
  set +a
fi

# ── 5) Prompt for CSV catalog regeneration ───────────────────────────────────
read -p "Run CSV catalog generation? (Y/N): " ans
ans="${ans^^}"  # uppercase
if [[ "$ans" == "Y" ]]; then
  echo "🔄 Regenerating CSV catalog…"
  python - << 'PYCODE'
from app.services.catalog_generation.csv_cat import save_csv_catalog
save_csv_catalog()
PYCODE
else
  echo "⏭️  Skipping catalog generation"
fi

# ── 6) Launch server (no auto-reload) ────────────────────────────────────────
echo "🚀 Launching FastAPI on http://localhost:8000/ (no reload) …"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000
