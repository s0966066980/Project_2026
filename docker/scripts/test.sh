#!/usr/bin/env sh
set -eu

REPO="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
COMPOSE_FILES="-f docker/compose.yaml"
COMPOSE_ENV="--env-file .env"

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-project-2026-smoke}"
export COMPOSE_PROJECT_NAME

# A separate project name isolates containers and volumes but not host ports,
# so this script used to die with "port is already allocated" whenever a stack
# was running — which is most of the time on a development host. Every check
# below runs inside the app container against 127.0.0.1:8000, so the published
# port is only there for a human; give the smoke run its own and stop the
# collision.
APP_PORT="${SMOKE_APP_PORT:-18000}"
export APP_PORT

cleanup() {
    docker compose $COMPOSE_ENV $COMPOSE_FILES down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cleanup
docker compose $COMPOSE_ENV $COMPOSE_FILES config --quiet
docker compose $COMPOSE_ENV $COMPOSE_FILES build
docker compose $COMPOSE_ENV $COMPOSE_FILES --profile test build test
docker compose $COMPOSE_ENV $COMPOSE_FILES --profile test run --rm --no-deps test

docker compose $COMPOSE_ENV $COMPOSE_FILES up --detach --wait

docker compose $COMPOSE_ENV $COMPOSE_FILES exec -T app python -c "import json, urllib.request; live=json.load(urllib.request.urlopen('http://127.0.0.1:8000/live')); ready=json.load(urllib.request.urlopen('http://127.0.0.1:8000/ready')); assert live['status']=='live'; assert ready['ready'] is True"
docker compose $COMPOSE_ENV $COMPOSE_FILES exec -T app python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/kiosk').status == 200; assert urllib.request.urlopen('http://127.0.0.1:8000/admin').status == 200"

docker compose $COMPOSE_ENV $COMPOSE_FILES ps
echo "Docker smoke test passed."
