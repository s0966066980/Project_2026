#!/usr/bin/env bash
# Collect the runtime half of the Pilot container security evidence.
#
# The structural half — that the overlay declares the contract — is a required
# check (UI_API/tests/test_pilot_container_security.py). This script proves the
# kernel actually applied it to the running containers, which no YAML assertion
# can show.
#
# It reads the running stack and writes nothing to it beyond probe files it
# removes again. It is not a substitute for target-device admission.
#
# Usage:
#   PILOT_ENV_FILE=... PILOT_DATABASE_URL_FILE=... PILOT_MIGRATION_DATABASE_URL_FILE=... \
#     bash docker/scripts/verify-pilot-security.sh

set -euo pipefail

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-project-2026}"
SERVICES=("app" "worker")
FAILURES=0

note() { printf '%s\n' "$*"; }
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

require_container() {
  local name="$1"
  if ! docker inspect "$name" >/dev/null 2>&1; then
    fail "container ${name} is not running; bring the Pilot stack up first"
    return 1
  fi
  return 0
}

check_kernel_contract() {
  local name="$1"
  local readonly_rootfs cap_add user

  readonly_rootfs="$(docker inspect "$name" --format '{{.HostConfig.ReadonlyRootfs}}')"
  [ "$readonly_rootfs" = "true" ] && pass "${name}: read-only root filesystem" ||
    fail "${name}: root filesystem is writable"

  cap_add="$(docker inspect "$name" --format '{{.HostConfig.CapAdd}}')"
  [ "$cap_add" = "[]" ] && pass "${name}: no capability added back" ||
    fail "${name}: capabilities added back without evidence: ${cap_add}"

  user="$(docker inspect "$name" --format '{{.Config.User}}')"
  case "$user" in
    0 | 0:* | root | root:*) fail "${name}: runs as root (${user})" ;;
    "") fail "${name}: no explicit runtime principal" ;;
    *) pass "${name}: non-root runtime principal ${user}" ;;
  esac

  # The bounding set is the claim that matters: an empty CapBnd means the
  # process cannot regain a capability even if something later tries.
  local bounding
  bounding="$(docker exec "$name" sh -c 'grep ^CapBnd /proc/1/status' | awk '{print $2}')"
  [ "$bounding" = "0000000000000000" ] && pass "${name}: empty capability bounding set" ||
    fail "${name}: capability bounding set is ${bounding}"

  local nnp
  nnp="$(docker exec "$name" sh -c 'grep ^NoNewPrivs /proc/1/status' | awk '{print $2}')"
  [ "$nnp" = "1" ] && pass "${name}: privilege escalation disabled" ||
    fail "${name}: NoNewPrivs is ${nnp}"
}

check_write_boundary() {
  local name="$1"

  # Writing outside the allowlist must fail. A silent success here means the
  # read-only claim is decoration.
  local blocked
  blocked="$(docker exec "$name" python -c '
import os
paths = ["/app/UI_API/.probe", "/.probe", "/usr/local/.probe", "/etc/.probe", "/home/project2026/.probe"]
writable = []
for path in paths:
    try:
        open(path, "w").write("probe")
        os.remove(path)
        writable.append(path)
    except OSError:
        pass
print(",".join(writable) if writable else "NONE")
')"
  [ "$blocked" = "NONE" ] && pass "${name}: root filesystem writes rejected" ||
    fail "${name}: writable root filesystem paths: ${blocked}"

  # The allowlisted paths must still work, or the hardening has broken the app
  # in a way health checks may not surface until a customer hits it.
  local usable
  usable="$(docker exec "$name" python -c '
import os
paths = ["/tmp/.probe", "/var/lib/project-2026/.probe"]
broken = []
for path in paths:
    try:
        open(path, "w").write("probe")
        os.remove(path)
    except OSError as error:
        broken.append(f"{path}({error.errno})")
print(",".join(broken) if broken else "NONE")
')"
  [ "$usable" = "NONE" ] && pass "${name}: allowlisted writable paths usable" ||
    fail "${name}: allowlisted paths not writable: ${usable}"
}

check_secret_handling() {
  local name="$1"

  local report
  report="$(docker exec "$name" python -c '
import os
problems = []
for secret in ("pilot_env", "database_url", "migration_database_url"):
    path = f"/run/secrets/{secret}"
    try:
        info = os.stat(path)
    except OSError:
        problems.append(f"{secret}:missing")
        continue
    if info.st_mode & 0o077:
        problems.append(f"{secret}:mode{oct(info.st_mode & 0o777)}")
    if not open(path).read().strip():
        problems.append(f"{secret}:unreadable")
print(",".join(problems) if problems else "NONE")
')"
  [ "$report" = "NONE" ] && pass "${name}: secrets present, private and readable" ||
    fail "${name}: secret problems: ${report}"

  # The credential must reach the process without becoming an environment
  # variable, where any diagnostic dump would carry it.
  local leaked
  leaked="$(docker exec "$name" python -c '
import os
secret = open("/run/secrets/database_url").read().strip()
password = secret.split(":")[2].split("@")[0] if secret.count(":") >= 2 else ""
hits = [key for key, value in os.environ.items() if password and password in str(value)]
print(",".join(hits) if hits else "NONE")
')"
  [ "$leaked" = "NONE" ] && pass "${name}: database credential absent from the environment" ||
    fail "${name}: database credential exposed in: ${leaked}"
}

check_disabled_routes() {
  local base="${PILOT_BASE_URL:-http://127.0.0.1:8000}"
  local path code
  for path in /api/ollama/models /api/demo /api/debug; do
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 8 "${base}${path}" || echo 000)"
    [ "$code" = "404" ] && pass "route ${path} absent (${code})" ||
      fail "route ${path} answered ${code}; it must be absent in the Pilot profile"
  done

  code="$(curl -s -o /dev/null -w '%{http_code}' -m 8 "${base}/ready" || echo 000)"
  [ "$code" = "200" ] && pass "/ready answers 200" || fail "/ready answered ${code}"
}

note "Pilot container security verification — project ${PROJECT_NAME}"
note ""

for service in "${SERVICES[@]}"; do
  container="${PROJECT_NAME}-${service}-1"
  if require_container "$container"; then
    check_kernel_contract "$container"
    check_write_boundary "$container"
    check_secret_handling "$container"
  fi
  note ""
done

check_disabled_routes
note ""

if [ "$FAILURES" -eq 0 ]; then
  note "All Pilot container security checks passed."
  exit 0
fi

note "${FAILURES} Pilot container security check(s) failed."
exit 1
