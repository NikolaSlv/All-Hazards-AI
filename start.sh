#!/usr/bin/env bash
set -euo pipefail
# ── start.sh ──────────────────────────────────────────────────────────────
# • Creates/updates the venv and installs requirements
# • Optionally regenerates the CSV & script catalogues (interactive prompts)
# • Regenerates gRPC stubs into the repo root
# • Launches FastAPI (no reload) while an external LLM micro-service runs
#   via ./start_llm.sh

# 0) Move to repo root ------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

# 1) Create venv if missing -------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
  echo "🐍  Creating virtualenv in $VENV_DIR …"
  python -m venv "$VENV_DIR"
fi

# 2) Activate venv (handles Windows & POSIX layouts) -----------------------------
if [[ -f "$VENV_DIR/Scripts/activate" ]]; then     # Windows
  source "$VENV_DIR/Scripts/activate"
elif [[ -f "$VENV_DIR/bin/activate" ]]; then       # Linux/macOS/WSL
  source "$VENV_DIR/bin/activate"
else
  echo "❌  Could not find activate script in $VENV_DIR" >&2
  exit 1
fi

# 3) Upgrade pip & install/upgrade deps ------------------------------------------
echo "⬆️  Upgrading pip & wheel …"
python -m pip install --upgrade --quiet pip wheel

echo "📦 Installing requirements.txt …"
pip install --no-cache-dir -r requirements.txt

# 4) Regenerate gRPC stubs into the root directory -------------------------------
echo "🛠️  Generating gRPC Python stubs in ./"
python -m grpc_tools.protoc \
  -I proto \
  --python_out=. \
  --grpc_python_out=. \
  proto/model.proto

# 5) Load .env if present --------------------------------------------------------
if [[ -f ".env" ]]; then
  echo "📄  Loading .env"
  set -a
  source .env
  set +a
fi

# 6) Optional catalogue regeneration ---------------------------------------------
regen() {
  local prompt="$1" pycall="$2" answer
  read -rp "$prompt (Y/N): " answer
  answer=${answer^^}
  if [[ "$answer" == "Y" ]]; then
    echo "🔄  Regenerating …"
    python - <<PY
import importlib
mod, fn = "$pycall".rsplit(".",1)
getattr(importlib.import_module(mod), fn)()
PY
  else
    echo "⏭️  Skipped"
  fi
}
regen "Regenerate CSV catalogue?"    "app.services.catalog_generation.csv_cat.save_csv_catalog"
regen "Regenerate script catalogue?" "app.services.catalog_generation.script_cat.save_script_catalog"

# 7) Launch FastAPI (no reload; LLM runs in separate process) ---------------------
echo "🚀  Starting FastAPI on http://localhost:8000  (no reload)"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000
