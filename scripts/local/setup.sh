#!/usr/bin/env bash
# Create venv, install dependencies, ensure runtime dirs. No Docker.
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

ensure_runtime_dirs
cd "$UI_API_DIR"

if [[ ! -d .venv ]]; then
  echo "Creating UI_API/.venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
if [[ -f requirements-ci.txt ]]; then
  python -m pip install -r requirements-ci.txt
else
  python -m pip install -r requirements.txt
fi

if [[ ! -f "$REPO_ROOT/.env" && -f "$REPO_ROOT/.env.example" ]]; then
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  echo "Created .env from .env.example — edit secrets locally; do not commit."
fi

echo "setup: OK"
echo "  python=$(python_bin)"
echo "  runtime=$RUNTIME_DIR"
echo "  next: scripts/local/doctor.sh && scripts/local/start.sh"
