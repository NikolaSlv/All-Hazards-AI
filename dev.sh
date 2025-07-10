#!/usr/bin/env bash
set -euo pipefail
# ──────────────────────────────────────────────────────────────────────────
# dev.sh
#   Hot-reload FastAPI *only*; the heavy LLM runs in its own gRPC process.
# ──────────────────────────────────────────────────────────────────────────

# 1) repo root -------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

# 2) ensure venv -----------------------------------------------------------
VENV_DIR=".venv"
[[ -d "$VENV_DIR" ]] || { echo "❌  .venv missing – run ./start.sh first."; exit 1; }

if   [[ -f "$VENV_DIR/Scripts/activate" ]]; then source "$VENV_DIR/Scripts/activate"   # Win
elif [[ -f "$VENV_DIR/bin/activate"   ]]; then source "$VENV_DIR/bin/activate"         # *nix
else echo "❌  activate script not found in $VENV_DIR"; exit 1
fi

# 3) .env ------------------------------------------------------------------
[[ -f .env ]] && { echo "📄  Loading .env"; set -a; source .env; set +a; }

# 4) optional catalogue regeneration ---------------------------------------
regen() {
  local prompt="$1" pycall="$2" answer
  read -rp "$prompt (Y/N): " answer
  answer=${answer^^}
  if [[ "$answer" == "Y" ]]; then
    echo "🔄  Regenerating …"
    python - <<PY
import importlib
mod, fn = "$pycall".rsplit(".", 1)
getattr(importlib.import_module(mod), fn)()
PY
  else
    echo "⏭️  Skipped"
  fi
}

regen "Regenerate CSV catalogue?"    "app.services.catalog_generation.csv_cat.save_csv_catalog"
regen "Regenerate PDF catalogue?"    "app.services.catalog_generation.pdf_cat.save_pdf_catalog"
regen "Regenerate script catalogue?" "app.services.catalog_generation.script_cat.save_script_catalog"

# 5) launch FastAPI with hot reload (watch only app/, ignore protobuf stubs)
echo "🚀  FastAPI dev server on http://localhost:8000  (auto-reload)"
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir app \
  --reload-exclude model_server.py \
  --reload-exclude '*_pb2.py' \
  --reload-exclude '*_pb2_grpc.py'
