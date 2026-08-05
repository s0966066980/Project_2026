#!/usr/bin/env sh
set -eu

REPO="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
BASE_FILES="-f docker/compose.yaml -f docker/compose.ai.yaml"

dc() {
    docker compose --env-file "$REPO/.env" $BASE_FILES "$@"
}

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-project-2026-ai-smoke}"
export COMPOSE_PROJECT_NAME
BUILDKIT_PROGRESS="${BUILDKIT_PROGRESS:-plain}"
export BUILDKIT_PROGRESS

cleanup() {
    dc down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

dc config --quiet
dc build app worker r1-omni

dc run --rm --no-deps app python -c "import os; assert os.environ.get('ENABLE_DIAGNOSTIC_ROUTES') == 'true', 'authenticated Ollama model-list route is disabled'; print('PASS: Ollama model-list route enabled')"

dc run --rm --no-deps app python -c "import chromadb, edge_tts, fastembed, faster_whisper, jieba, rank_bm25; print('PASS: UI AI dependencies import')"
dc run --rm --no-deps r1-omni python -c "import torch, transformers, decord, timm; from humanomni import model_init; print('PASS: R1 dependencies import', torch.__version__)"

echo "AI image smoke test passed."
