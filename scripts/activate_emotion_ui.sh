#!/usr/bin/env bash
# 供 Project_2026 啟動腳本 source；統一啟用 UI_API 的 Conda 執行環境。

CONDA_ROOT="${CONDA_ROOT:-/home/oliver/anaconda3}"
CONDA_SH="$CONDA_ROOT/etc/profile.d/conda.sh"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "❌ 找不到 Conda 初始化腳本：$CONDA_SH" >&2
  return 1
fi

# conda.sh 在 nounset 模式下不保證安全，啟用完成後恢復呼叫端設定。
set +u
source "$CONDA_SH"
conda activate emotion_ui
set -u

if [[ "${CONDA_DEFAULT_ENV:-}" != "emotion_ui" ]]; then
  echo "❌ 無法啟用 Conda emotion_ui 環境。" >&2
  return 1
fi

UI_PY="$(command -v python)"
export UI_PY

"$UI_PY" - <<'PY'
import importlib
import sys

required = ("faster_whisper", "fastembed", "edge_tts")
missing = []
for package in required:
    try:
        importlib.import_module(package)
    except Exception as exc:
        missing.append(f"{package} ({exc})")

if missing:
    print("❌ emotion_ui 缺少必要的語音/RAG 套件：" + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)

print(f"✓ UI_API Python：{sys.executable}（Conda emotion_ui）")
PY

