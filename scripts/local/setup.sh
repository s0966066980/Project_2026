#!/usr/bin/env bash
# Create venv, install dependencies, ensure runtime dirs. No Docker.
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

PROFILE="${1:-}"
WITH_AI=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-local-dev}"; shift 2 ;;
    --with-ai) WITH_AI=1; shift ;;
    *) shift ;;
  esac
done
PROFILE="${PROFILE:-${APP_PROFILE:-local-dev}}"

ensure_runtime_dirs
cd "$UI_API_DIR"

if [[ ! -d .venv ]]; then
  echo "Creating UI_API/.venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null

case "$PROFILE" in
  local-dev|test|ci)
    python -m pip install -r requirements-dev.txt
    ;;
  local-pilot|local-postgres|local-full)
    python -m pip install -r requirements-local-core.txt
    if [[ "$WITH_AI" == "1" ]]; then
      python -m pip install -r requirements-local-ai.txt
    fi
    ;;
  *)
    echo "WARN: unknown profile $PROFILE; installing local-core"
    python -m pip install -r requirements-local-core.txt
    ;;
esac

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  if [[ "$PROFILE" == "local-pilot" && -f "$REPO_ROOT/config/profiles/local-pilot.env.example" ]]; then
    cp "$REPO_ROOT/config/profiles/local-pilot.env.example" "$REPO_ROOT/.env"
    echo "Created .env from config/profiles/local-pilot.env.example — edit secrets locally."
  elif [[ -f "$REPO_ROOT/.env.example" ]]; then
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    echo "Created .env from .env.example — edit secrets locally; do not commit."
  fi
fi

echo "setup: OK"
echo "  profile=$PROFILE"
echo "  python=$(python_bin)"
echo "  runtime=$RUNTIME_DIR"
echo "  next: scripts/local/doctor.sh && scripts/local/start.sh"
