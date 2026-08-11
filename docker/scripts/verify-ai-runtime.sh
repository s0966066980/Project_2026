#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

COMPOSE_FILES=(
  -f docker/compose.yaml
  -f docker/compose.ai.yaml
  -f docker/compose.ai-gpu.yaml
)

dc() {
  docker compose --env-file "$REPO/.env" "${COMPOSE_FILES[@]}" "$@"
}

env_get() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env
}

command -v nvidia-smi >/dev/null 2>&1 || {
  echo "FAIL: host cannot run nvidia-smi" >&2
  exit 1
}

model_name="$(env_get OLLAMA_MODEL || true)"
model_name="${model_name:-qwen3.5:4b}"

echo "[1/5] Host NVIDIA driver"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

echo "[2/5] Compose services"
dc config --quiet
dc ps
test -n "$(dc ps -q ollama)" || { echo "FAIL: ollama container is not running" >&2; exit 1; }
test -n "$(dc ps -q r1-omni)" || { echo "FAIL: r1-omni container is not running" >&2; exit 1; }
test -n "$(dc ps -q app)" || { echo "FAIL: app container is not running" >&2; exit 1; }

echo "[3/5] GPU visibility inside both AI containers"
dc exec -T ollama nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
dc exec -T r1-omni nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

echo "[4/5] R1-Omni model and CUDA readiness"
dc exec -T app python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://r1-omni:7890/health", timeout=15) as response:
    payload = json.load(response)
print(json.dumps(payload, ensure_ascii=False))
assert payload.get("status") == "ok", payload
assert payload.get("model_loaded") is True, payload
assert payload.get("device") == "cuda", payload
PY

echo "[5/5] App-to-Ollama inference and VRAM residency (${model_name})"
dc exec -T app python - "$model_name" <<'PY'
import json
import sys
import time
import urllib.request

model = sys.argv[1]
request = urllib.request.Request(
    "http://ollama:11434/api/generate",
    data=json.dumps({
        "model": model,
        "prompt": "只回覆 GPU_OK",
        "stream": False,
        "think": False,
        "keep_alive": "5m",
        "options": {"num_predict": 16},
    }).encode(),
    headers={"Content-Type": "application/json"},
)
started = time.monotonic()
with urllib.request.urlopen(request, timeout=180) as response:
    generated = json.load(response)
elapsed = time.monotonic() - started
assert generated.get("response", "").strip(), generated

with urllib.request.urlopen("http://ollama:11434/api/ps", timeout=15) as response:
    running = json.load(response)
entry = next((row for row in running.get("models", []) if row.get("name") == model or row.get("model") == model), None)
assert entry is not None, running
size = int(entry.get("size") or 0)
size_vram = int(entry.get("size_vram") or 0)
assert size_vram > 0, entry
ratio = (size_vram / size * 100) if size else 0
print(json.dumps({
    "model": model,
    "response": generated.get("response", "").strip()[:120],
    "elapsed_seconds": round(elapsed, 2),
    "size_bytes": size,
    "size_vram_bytes": size_vram,
    "vram_residency_percent": round(ratio, 1),
}, ensure_ascii=False))
PY

echo "PASS: R1-Omni is on CUDA and Ollama inference is using GPU VRAM."
