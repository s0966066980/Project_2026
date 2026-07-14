#!/usr/bin/env bash
# Diagnose local environment. Prints PASS/WARN/FAIL only (no secret values).
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

ensure_runtime_dirs
fail=0
warn=0

pass() { echo "PASS: $*"; }
warn_() { echo "WARN: $*"; warn=$((warn + 1)); }
fail_() { echo "FAIL: $*"; fail=$((fail + 1)); }

echo "=== Project_2026 local doctor ==="
echo "repo=$REPO_ROOT"

# Python
PY="$(python_bin || true)"
if [[ -n "${PY:-}" ]]; then
  pass "python available ($PY)"
  if "$PY" -c "import fastapi, pydantic" 2>/dev/null; then
    pass "core python imports (fastapi, pydantic)"
  else
    fail_ "core python imports missing — run scripts/local/setup.sh"
  fi
else
  fail_ "python3 not found"
fi

# Node (frontend optional for API-only)
if command -v node >/dev/null 2>&1; then
  pass "node available"
else
  warn_ "node not found (frontend typecheck/e2e unavailable)"
fi

# .env
if [[ -f "$REPO_ROOT/.env" ]]; then
  pass ".env present"
  if grep -E '^(ADMIN_API_TOKEN|DATABASE_URL|OBJECT_STORAGE_SIGNING_SECRET)=CHANGE_ME' "$REPO_ROOT/.env" >/dev/null 2>&1; then
    warn_ "placeholder CHANGE_ME secrets still present in .env"
  fi
else
  warn_ ".env missing (copy from .env.example)"
fi

# Storage backend
storage="$(grep -E '^MEMBER_STORAGE_BACKEND=' "$REPO_ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\"' || true)"
storage="${storage:-json}"
echo "INFO: MEMBER_STORAGE_BACKEND=$storage"

if [[ "$storage" == "postgres" ]]; then
  if [[ -n "${DATABASE_URL:-}" ]] || grep -E '^DATABASE_URL=.+' "$REPO_ROOT/.env" >/dev/null 2>&1; then
    pass "DATABASE_URL configured for postgres mode"
  else
    fail_ "postgres mode without DATABASE_URL"
  fi
  if command -v pg_isready >/dev/null 2>&1; then
    if pg_isready >/dev/null 2>&1; then
      pass "pg_isready accepts connections"
    else
      fail_ "PostgreSQL not accepting connections"
    fi
  else
    warn_ "pg_isready not installed"
  fi
else
  pass "JSON storage mode (postgres not required)"
fi

# Redis optional
if [[ -n "${REDIS_URL:-}" ]] || grep -E '^REDIS_URL=.+' "$REPO_ROOT/.env" >/dev/null 2>&1; then
  if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli ping >/dev/null 2>&1; then
      pass "Redis ping OK"
    else
      warn_ "REDIS_URL set but redis-cli ping failed"
    fi
  else
    warn_ "REDIS_URL set but redis-cli missing"
  fi
else
  warn_ "Redis not configured (optional for local-dev)"
fi

# Ports
if port_in_use "$API_PORT"; then
  pass "API port $API_PORT is listening"
else
  warn_ "API port $API_PORT not listening (start with scripts/local/start.sh)"
fi

# Runtime dirs
for d in "$PID_DIR" "$LOG_DIR" "$OBJ_DIR"; do
  if [[ -d "$d" ]]; then
    pass "dir $d"
  else
    fail_ "missing $d"
  fi
done

# Docker not required
if command -v docker >/dev/null 2>&1; then
  warn_ "docker binary present but not required for local runtime"
else
  pass "docker not installed (expected for Local-first)"
fi

# Optional AI
if curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  pass "Ollama reachable (optional)"
else
  warn_ "Ollama not reachable (optional; checkout must still work)"
fi

echo "=== summary: fail=$fail warn=$warn ==="
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0
