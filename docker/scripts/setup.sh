#!/usr/bin/env bash
# First-run installer and launcher for the Project_2026 Docker stack.
#
# This script installs Docker/Compose on Debian or Ubuntu when needed, creates
# a local .env, validates the host-provided R1-Omni weights, builds the images,
# and starts the complete AI stack. R1-Omni weights remain host-provided, while
# the configured Ollama model is pulled automatically before the app starts.
set -Eeuo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKER_DIR="$REPO/docker"
cd "$REPO"

GPU=true
INSTALL_DEPS=true
SKIP_R1_CHECK=false

usage() {
  cat <<'EOF'
用法：
  bash docker/scripts/setup.sh [選項]

選項：
  --cpu              使用 CPU AI stack（預設使用 NVIDIA GPU）
  --gpu              明確使用 NVIDIA GPU（相容舊指令；目前為預設）
  --no-install       不安裝主機套件，只檢查現有 Docker/Compose
  --skip-r1-check    不檢查 R1-Omni 本地權重（權重缺少時 R1 服務不會健康）
  -h, --help         顯示說明

腳本會自動準備 .env 指定的 Ollama 模型。R1-Omni 權重不會自動下載，
必須先放在 .env 的 R1_MODELS_PATH。
EOF
}

die() {
  echo "錯誤：$*" >&2
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --cpu) GPU=false ;;
    --gpu) GPU=true ;;
    --no-install) INSTALL_DEPS=false ;;
    --skip-r1-check) SKIP_R1_CHECK=true ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知選項：$arg（使用 --help 查看用法）" ;;
  esac
done

if [[ "$(id -u)" == 0 ]]; then
  SUDO=()
elif command -v sudo >/dev/null 2>&1; then
  SUDO=(sudo)
elif [[ "$INSTALL_DEPS" == true ]]; then
  die "需要 sudo 權限安裝 Docker。請安裝 sudo，或以 root 執行。"
else
  SUDO=()
fi

run_root() {
  "${SUDO[@]}" "$@"
}

install_host_packages() {
  if [[ "$INSTALL_DEPS" != true ]]; then
    return
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    die "目前腳本的自動安裝只支援 Debian/Ubuntu（找不到 apt-get）。請先安裝 Docker Engine 與 Compose v2。"
  fi

  echo "[1/8] 安裝主機工具（curl、git、openssl、ss）..."
  run_root apt-get update
  run_root apt-get install -y ca-certificates curl git openssl iproute2

  if ! command -v docker >/dev/null 2>&1; then
    echo "[2/8] 安裝 Docker Engine 與 Compose plugin..."
    # Docker 官方 convenience installer also installs the v2 compose plugin.
    curl -fsSL https://get.docker.com | run_root sh
  else
    echo "[2/8] Docker 已存在，略過 Engine 安裝。"
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo "[2/8] 安裝 Docker Compose v2 plugin..."
    run_root apt-get install -y docker-compose-plugin || true
  fi
}

install_host_packages

command -v docker >/dev/null 2>&1 || die "找不到 docker。請安裝 Docker Engine 後重新執行。"

install_nvidia_toolkit() {
  [[ "$GPU" == true ]] || return

  command -v nvidia-smi >/dev/null 2>&1 \
    || die "預設安裝使用 GPU，但找不到 nvidia-smi。請先安裝 NVIDIA driver，或使用 --cpu。"

  if run_root docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
    echo "[GPU] Docker NVIDIA runtime 已設定。"
    return
  fi

  if ! command -v nvidia-ctk >/dev/null 2>&1; then
    [[ "$INSTALL_DEPS" == true ]] || die "找不到 nvidia-ctk。請移除 --no-install，讓腳本安裝 NVIDIA Container Toolkit。"
    command -v apt-get >/dev/null 2>&1 || die "GPU 自動安裝目前只支援 Debian/Ubuntu。"
    echo "[GPU] 安裝 NVIDIA Container Toolkit..."
    run_root apt-get install -y --no-install-recommends gnupg2
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
      | run_root gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' \
      | run_root tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    run_root apt-get update
    run_root apt-get install -y nvidia-container-toolkit
  fi

  echo "[GPU] 設定 Docker NVIDIA runtime..."
  run_root nvidia-ctk runtime configure --runtime=docker
  if command -v systemctl >/dev/null 2>&1; then
    run_root systemctl restart docker
  else
    die "找不到 systemctl，無法重新啟動 Docker daemon。請手動重啟 Docker 後再執行。"
  fi
}

install_nvidia_toolkit

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files docker.service >/dev/null 2>&1; then
  run_root systemctl enable --now docker >/dev/null 2>&1 || true
fi

# A newly added docker group is not active until the user logs in again. Use
# sudo for this run when the unprivileged socket is not available yet.
DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if [[ "$(id -u)" != 0 ]] && sudo docker info >/dev/null 2>&1; then
    DOCKER=(sudo docker)
  else
    die "目前使用者無法連線 Docker daemon。請執行 'sudo usermod -aG docker $USER'，重新登入後再執行。"
  fi
fi

if ! "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  die "找不到 Docker Compose v2。請安裝 docker-compose-plugin，或使用 Docker Desktop。"
fi

dc() {
  # Compose resolves interpolation from the directory of the first compose
  # file. Always make the repository-level Docker environment explicit so the
  # setup script and Compose cannot silently use different defaults.
  "${DOCKER[@]}" compose --env-file "$REPO/.env" "${COMPOSE_FILES[@]}" "$@"
}

env_get() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env
}

env_set() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '\n%s=%s\n' "$key" "$value" >> .env
  fi
}

echo "[3/8] 建立環境設定..."
created_env=false
generated_admin_password=""
if [[ ! -f .env ]]; then
  [[ -f "$DOCKER_DIR/.env.example" ]] || die "找不到 docker/.env.example。"
  cp "$DOCKER_DIR/.env.example" .env
  chmod 600 .env
  created_env=true
fi

# Generate safe local defaults when the file is new or still contains the
# example placeholders. Existing non-placeholder values are never overwritten.
current_pg_password="$(env_get POSTGRES_PASSWORD || true)"
current_admin_password="$(env_get ADMIN_MANAGER_PASSWORD || true)"
if [[ "$created_env" == true || -z "$current_pg_password" || "$current_pg_password" == replace-with-* ]]; then
  env_set POSTGRES_PASSWORD "$(openssl rand -hex 24)"
fi
if [[ "$created_env" == true || -z "$current_admin_password" || "$current_admin_password" == replace-with-* ]]; then
  generated_admin_password="$(openssl rand -hex 24)"
  env_set ADMIN_MANAGER_PASSWORD "$generated_admin_password"
fi

COMPOSE_FILES=(-f "$DOCKER_DIR/compose.yaml" -f "$DOCKER_DIR/compose.ai.yaml")
if [[ "$GPU" == true ]]; then
  COMPOSE_FILES+=(-f "$DOCKER_DIR/compose.ai-gpu.yaml")
fi

port_in_use() {
  local port="$1"
  ss -H -ltn 2>/dev/null | awk -v port=":${port}" '$4 == port || $4 ~ port "$"' | grep -q .
}

compose_service_owns_port() {
  local service="$1" port="$2" container_id
  container_id="$(dc ps -q "$service" 2>/dev/null || true)"
  [[ -n "$container_id" ]] || return 1
  "${DOCKER[@]}" inspect \
    --format '{{range $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println .HostPort}}{{end}}{{end}}' \
    "$container_id" 2>/dev/null | grep -qx "$port"
}

echo "[4/8] 檢查主機連接埠與 R1-Omni 權重..."
ollama_port="$(env_get OLLAMA_PORT || true)"
ollama_port="${ollama_port:-11434}"
if port_in_use "$ollama_port" && ! compose_service_owns_port ollama "$ollama_port"; then
  if [[ "$ollama_port" == 11434 ]]; then
    new_port=11435
    while port_in_use "$new_port"; do
      new_port=$((new_port + 1))
    done
    env_set OLLAMA_PORT "$new_port"
    ollama_port="$new_port"
    echo "主機 11434 已被其他 Ollama/程序使用，Docker Ollama 改用 ${ollama_port}。"
  else
    die "OLLAMA_PORT=${ollama_port} 已被占用，請修改 .env 後重新執行。"
  fi
fi

if [[ "$SKIP_R1_CHECK" != true ]]; then
  models_path="$(env_get R1_MODELS_PATH || true)"
  models_path="${models_path:-../R1-Omni/models}"
  if [[ "$models_path" == "./R1-Omni/models" ]]; then
    models_path="../R1-Omni/models"
    env_set R1_MODELS_PATH "$models_path"
    echo "已將舊版 R1_MODELS_PATH 更新為 $models_path。"
  fi
  if [[ "$models_path" = /* ]]; then
    models_root="$models_path"
  else
    models_root="$DOCKER_DIR/$models_path"
  fi

  required_files=(
    "R1-Omni-0.5B/config.json"
    "R1-Omni-0.5B/model.safetensors"
    "bert-base-uncased/vocab.txt"
    "siglip-base-patch16-224/config.json"
    "siglip-base-patch16-224/model.safetensors"
    "whisper-large-v3/config.json"
    "whisper-large-v3/model.safetensors"
  )
  missing=()
  for relative_file in "${required_files[@]}"; do
    [[ -f "$models_root/$relative_file" ]] || missing+=("$relative_file")
  done
  if (( ${#missing[@]} > 0 )); then
    echo "R1_MODELS_PATH=$models_path"
    printf '缺少：%s\n' "${missing[@]}"
    die "請先將四組 R1-Omni 本地權重放入上述目錄，再重新執行；腳本不會自動下載權重。"
  fi
  echo "R1-Omni 本地權重檢查通過（Docker 將以唯讀方式掛載）。"
else
  echo "略過 R1-Omni 權重檢查。"
fi

echo "[5/8] 驗證 Compose 設定..."
dc config --quiet

echo "[6/8] 建置 image（R1 權重不會打包進 image）..."
dc build app worker r1-omni

model_name="$(env_get OLLAMA_MODEL || true)"
model_name="${model_name:-qwen3.5:4b}"
app_port="$(env_get APP_PORT || true)"
app_port="${app_port:-8000}"
r1_omni_port="$(env_get R1_OMNI_PORT || true)"
r1_omni_port="${r1_omni_port:-7890}"

echo "[7/8] 啟動 Ollama 並準備模型 ${model_name}..."
dc up -d --wait ollama
dc exec -T ollama ollama pull "$model_name"

echo "[8/8] 啟動完整 AI stack..."
dc up -d --wait

echo
echo "完成。服務狀態："
dc ps
if [[ -n "$generated_admin_password" ]]; then
  echo
  echo "首次建立的 Admin 登入資訊（已保存於 .env）："
  echo "  帳號：admin"
  echo "  密碼：${generated_admin_password}"
fi
echo
echo "R1-Omni：使用主機本地權重，未下載任何 R1 權重。"
echo "Ollama 模型：${model_name}（已準備完成）"
echo "Kiosk：http://127.0.0.1:${app_port}/kiosk"
echo "Admin：http://127.0.0.1:${app_port}/admin"
echo "R1-Omni：http://127.0.0.1:${r1_omni_port}"
echo "Ollama 對外網址：http://127.0.0.1:${ollama_port}"
echo
echo "日後啟動：${DOCKER[*]} compose ${COMPOSE_FILES[*]} up -d --wait"
echo "停止但保留資料：${DOCKER[*]} compose ${COMPOSE_FILES[*]} down"
