#!/usr/bin/env bash
#
# 一鍵啟動：情緒模型 = Emotion-LLaMA
#
# 會依序拉起（缺哪個才補哪個，已在跑的不重啟）：
#   1. 把後台 EMOTION_PROVIDER 設成 emotion_llama
#   2. Ollama (serve + 確認模型)            :11434
#   3. Emotion-LLaMA /predict server        :7889
#   4. UI_API 主服務 (POS + 後台)           :9000 / 9001
#
# main.py 在前景執行；按 Ctrl-C 會把「本腳本啟動的」背景服務一起關掉
# （原本就在跑的 Ollama / Emotion-LLaMA 不會被動到）。
#
# 用法：  bash scripts/start_emotion_llama.sh
set -euo pipefail

# ── 路徑與環境 ────────────────────────────────────────────────
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_PY="${UI_PY:-/home/oliver/anaconda3/envs/emotion_ui/bin/python}"
LLAMA_PY="${LLAMA_PY:-/home/oliver/anaconda3/envs/emotion_ollama/bin/python}"
OLLAMA_BIN="${OLLAMA_BIN:-/usr/local/bin/ollama}"
MODEL_NAME="${MODEL_NAME:-qwen3.5:4b}"
APP_PORT="${APP_PORT:-9000}"
ADMIN_PORT="${ADMIN_PORT:-9001}"
OPEN_BROWSER="${OPEN_BROWSER:-true}"
POS_URL="http://127.0.0.1:${APP_PORT}/pos"
ADMIN_URL="http://127.0.0.1:${ADMIN_PORT}/admin"
export APP_PORT ADMIN_PORT

LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"

# 記錄本腳本啟動的背景 PID，結束時收掉
STARTED_PIDS=()

cleanup() {
  echo ""
  echo "🧹 收拾本腳本啟動的背景服務…"
  for pid in "${STARTED_PIDS[@]:-}"; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  echo "✅ 已結束。"
}
trap cleanup EXIT INT TERM

# ── 小工具 ────────────────────────────────────────────────────
port_open() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

open_browser() {
  if [[ "$OPEN_BROWSER" != "true" ]]; then
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$ADMIN_URL" >/dev/null 2>&1 || true
    xdg-open "$POS_URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$ADMIN_URL" >/dev/null 2>&1 || true
    open "$POS_URL" >/dev/null 2>&1 || true
  fi
}

wait_for_port() {  # wait_for_port <port> <名稱> <秒數>
  local port="$1" name="$2" timeout="${3:-60}" i=0
  while ! port_open "$port"; do
    i=$((i + 1))
    if [[ $i -gt $((timeout * 2)) ]]; then
      echo "❌ $name 等待逾時（port $port 未就緒，>${timeout}s）"
      return 1
    fi
    sleep 0.5
  done
  return 0
}

# ── 1. 切換情緒模型為 emotion_llama ───────────────────────────
echo "⚙️  設定 EMOTION_PROVIDER = emotion_llama …"
( cd "$REPO/UI_API" && "$UI_PY" -c "import config; config.save_settings({'EMOTION_PROVIDER':'emotion_llama'})" )

# ── 2. Ollama ─────────────────────────────────────────────────
if port_open 11434; then
  echo "✓ Ollama 已在執行 (:11434)"
else
  echo "🚀 啟動 Ollama serve …"
  "$OLLAMA_BIN" serve >"$LOG_DIR/ollama.log" 2>&1 &
  STARTED_PIDS+=("$!")
  wait_for_port 11434 "Ollama" 30
  echo "✓ Ollama 就緒"
fi
# 確認模型存在（缺了才拉，pull 已存在的模型會很快跳過）
if ! "$OLLAMA_BIN" list 2>/dev/null | grep -q "${MODEL_NAME%%:*}"; then
  echo "⬇️  拉取模型 $MODEL_NAME（首次較久）…"
  "$OLLAMA_BIN" pull "$MODEL_NAME"
fi

# ── 3. Emotion-LLaMA /predict server (:7889) ──────────────────
if port_open 7889; then
  echo "✓ Emotion-LLaMA 已在執行 (:7889)"
else
  echo "🚀 啟動 Emotion-LLaMA (:7889) …"
  ( cd "$REPO/Emotion-LLaMA" && exec "$LLAMA_PY" app_EmotionLlamaClient.py \
      --cfg-path eval_configs/demo.yaml --port 7889 ) \
      >"$LOG_DIR/emotion_llama.log" 2>&1 &
  STARTED_PIDS+=("$!")
  echo "   （模型載入中，log: logs/emotion_llama.log）"
  wait_for_port 7889 "Emotion-LLaMA" 180
  echo "✓ Emotion-LLaMA 就緒"
fi

# ── 4. UI_API 主服務 (:9000 / :9001) ──────────────────────────
if port_open "$APP_PORT" || port_open "$ADMIN_PORT"; then
  echo "⚠️  ${APP_PORT}/${ADMIN_PORT} 已被占用，主服務可能已在跑 —— 略過啟動 main.py。"
  echo "    若要重啟，請先停掉既有的 main.py。"
  echo ""
  echo "👉 POS: $POS_URL   後台: $ADMIN_URL"
  echo "👉 RAG: 後台 > RAG 知識庫，可直接清空 Chroma 並重新讀取 rag_documents"
  echo "（Ctrl-C 結束本腳本並收掉自己啟動的背景服務）"
  open_browser
  wait
else
  echo "🚀 啟動 UI_API 主服務 …"
  echo ""
  echo "👉 POS: $POS_URL   後台: $ADMIN_URL"
  echo "👉 RAG: 後台 > RAG 知識庫，可直接清空 Chroma 並重新讀取 rag_documents"
  echo "（前景執行，Ctrl-C 結束全部）"
  echo "────────────────────────────────────────────"
  cd "$REPO/UI_API"
  ( sleep 3; open_browser ) &
  exec "$UI_PY" main.py
fi
