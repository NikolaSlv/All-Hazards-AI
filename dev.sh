#!/usr/bin/env bash
set -euo pipefail

# 1) Ensure we’re in the repo root (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

# 2) Activate your existing venv
#    Adjust the path if you named it differently
if [ -f ".venv/Scripts/activate" ]; then
  source ".venv/Scripts/activate"
elif [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
else
  echo "No virtualenv found at .venv - proceeding without activation"
fi

# 3) Load .env if present
if [ -f ".env" ]; then
  echo "Loading environment variables from .env"
  export $(grep -Ev '^\s*#' .env | xargs)
fi

# 4) Launch Uvicorn in reload mode
echo "🚀 Launching FastAPI (uvicorn app.main:app)…"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
