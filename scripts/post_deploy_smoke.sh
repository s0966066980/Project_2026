#!/usr/bin/env bash
# Post-deploy smoke: liveness, readiness and optional metric endpoint.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CURL_BIN="${CURL_BIN:-curl}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
SLEEP_SECONDS="${SLEEP_SECONDS:-2}"

if ! command -v "$CURL_BIN" >/dev/null 2>&1; then
  echo "ERROR: curl is required for post-deploy smoke." >&2
  exit 1
fi

echo "== post-deploy: base URL $BASE_URL =="

wait_for() {
  local path="$1"
  local attempt=1
  while (( attempt <= MAX_ATTEMPTS )); do
    if "$CURL_BIN" -fsS "${BASE_URL}${path}" >/tmp/project2026_smoke_body.$$ 2>/tmp/project2026_smoke_err.$$; then
      echo "OK ${path}"
      cat /tmp/project2026_smoke_body.$$
      echo
      return 0
    fi
    echo "waiting for ${path} (attempt ${attempt}/${MAX_ATTEMPTS})"
    sleep "$SLEEP_SECONDS"
    attempt=$((attempt + 1))
  done
  echo "ERROR: ${path} did not become healthy" >&2
  cat /tmp/project2026_smoke_err.$$ >&2 || true
  return 1
}

wait_for "/live"
wait_for "/ready"

if "$CURL_BIN" -fsS "${BASE_URL}/api/v1/health/metrics" >/tmp/project2026_metrics.$$ 2>/dev/null; then
  echo "OK metrics endpoint present"
else
  echo "metrics endpoint optional — skipped"
fi

rm -f /tmp/project2026_smoke_body.$$ /tmp/project2026_smoke_err.$$ /tmp/project2026_metrics.$$
echo "post-deploy smoke completed"
