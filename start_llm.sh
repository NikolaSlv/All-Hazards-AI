#!/usr/bin/env bash
set -euo pipefail
# ──────────────────────────────────────────────────────────────────────────
# start_llm.sh
#   Keeps the Meta-Llama model resident in a dedicated gRPC micro-service.
#   Run this once (separate terminal / tmux pane) BEFORE running dev.sh.
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

# 3) .env (for HF_TOKEN etc.) ---------------------------------------------
[[ -f .env ]] && { echo "📄  Loading .env"; set -a; source .env; set +a; }

# 4) make sure project root is on PYTHONPATH ------------------------------
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

# 5) launch gRPC model-server ---------------------------------------------
echo "🚀  Starting LLM gRPC server (app/services/model_server.py) on port 50051 …"
python -m app.services.model_server
