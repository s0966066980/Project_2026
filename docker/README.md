# Project_2026 Docker Runtime

Docker Compose 是 Project_2026 唯一支援的 application runtime。Kiosk、Admin、API、worker、PostgreSQL、Ollama 與 R1-Omni 都由本目錄的 Docker 定義啟動；不需要 Conda。

Docker development stack 只使用專案根目錄 `.env`。`docker/scripts/setup.sh` 會在第一次執行時從 `docker/.env.example` 建立該檔並產生隨機密碼。

## 一鍵啟動

GPU 是主要路徑，適用於已安裝 NVIDIA driver 的 Debian／Ubuntu：

```bash
cd ~/Project_2026
bash docker/scripts/setup.sh
```

沒有 NVIDIA GPU 時：

```bash
bash docker/scripts/setup.sh --cpu
```

常用選項：

```text
--cpu            使用 CPU AI stack
--gpu            明確使用 GPU；與預設相同
--no-install     不安裝 Docker／主機套件
--skip-r1-check  略過 R1 權重檢查；缺權重時服務不會健康
```

setup 會安裝 Docker、設定 GPU runtime、驗證 R1 權重、建置 images、自動拉取 `.env` 的 Ollama 模型，最後啟動 stack 並等待健康檢查。

## R1-Omni 權重

setup 不下載 R1 權重。預設 `R1_MODELS_PATH=../R1-Omni/models` 是相對於 `docker/`，實際位置為：

```text
R1-Omni/models/
├── R1-Omni-0.5B/
│   ├── config.json
│   └── model.safetensors
├── bert-base-uncased/
│   └── vocab.txt
├── siglip-base-patch16-224/
│   ├── config.json
│   └── model.safetensors
└── whisper-large-v3/
    ├── config.json
    └── model.safetensors
```

其他位置可在根目錄 `.env` 使用絕對路徑：

```dotenv
R1_MODELS_PATH=/srv/project-2026/models
```

權重以唯讀方式掛載到 R1 容器 `/models`，不會進入 image。

## Compose 分層

| File | 用途 |
| --- | --- |
| `compose.yaml` | PostgreSQL、migration、app、worker 與 test profile |
| `compose.ai.yaml` | AI dependencies、Ollama 與 CPU R1-Omni |
| `compose.ai-gpu.yaml` | 將 Ollama／R1 切換為 NVIDIA GPU |
| `compose.pilot.yaml` | Local Pilot 硬化契約；必須放在最後一個 `-f` |

GPU 手動啟動：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up -d --wait
```

CPU 手動啟動：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  up -d --wait
```

手動 Compose 不會替你拉取模型；需要時執行：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  exec ollama ollama pull qwen3.5:4b
```

一鍵 setup 已自動執行這一步。

## 服務與資料

```text
Kiosk:   http://127.0.0.1:8000/kiosk
Admin:   http://127.0.0.1:8000/admin
Ready:   http://127.0.0.1:8000/ready
R1-Omni: http://127.0.0.1:7890
Ollama:  http://127.0.0.1:11434
```

實際 port 由根目錄 `.env` 決定；setup 遇到 Ollama port 衝突時會選擇可用 port 並更新 `.env`。

Named volumes 保存：

- `postgres_data`：PostgreSQL 資料。
- `app_data`：application runtime data。
- `ollama_models`：已拉取的 Ollama 模型。
- `ai_cache`：STT、RAG 與 Hugging Face cache。
- `shared_media`：app 與 R1 間的受控暫存媒體。

`docker compose down` 會保留 volumes。不要執行 `down --volumes`，除非確定要刪除資料與模型。

## 更新與除錯

修改程式碼後，必須重新 build；程式碼會被複製進 image，不使用本機 Python runtime：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  ps

docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  logs -f app worker ollama r1-omni
```

## 驗證腳本

```bash
docker/scripts/test.sh
docker/scripts/test-ai.sh
```

`test.sh` 建置核心 runtime/test image、執行測試並啟動暫存 PostgreSQL stack。`test-ai.sh` 驗證 AI image dependencies，不下載 R1 權重或執行長時間 GPU inference。

## 安全邊界

`compose.yaml`、`compose.ai.yaml` 與 `compose.ai-gpu.yaml` 合起來是 development/local profile：`APP_ENV=development`、`SECURITY_ENFORCED=false`、diagnostic routes 開啟、PostgreSQL URL 內嵌預設密碼。**它不是 Pilot，也不能用來宣告 Local Pilot Readiness。**

## Local Pilot 硬化 profile

`compose.pilot.yaml` 是 Pilot runtime 契約（[ADR-0061](../docs/adr/0061-run-the-pilot-on-a-read-only-container-contract.md)）。它對 `migrate`、`app`、`worker` 套用 `read_only: true`、`cap_drop: [ALL]`、`no-new-privileges:true` 與 non-root uid 10001，只保留 `/tmp` 一個 `nosuid,nodev` tmpfs 作為可寫面；runtime data 仍在 `app_data` volume，model cache 與 media temp 在 AI overlay 的 named volumes。

`postgres`、`ollama`、`r1-omni` 維持 upstream runtime 契約，不在本 overlay 範圍內。

### 1. 建立主機外部設定授權

設定與 secrets 必須在 repository 之外，且屬於 container runtime principal：

```bash
install -d -m 0700 ~/.config/project-2026
cp config/profiles/local-pilot.env.example ~/.config/project-2026/pilot.env
# 填入真實值後：
printf 'postgresql://project_2026:<password>@postgres:5432/project_2026\n' \
  > ~/.config/project-2026/database_url
cp ~/.config/project-2026/database_url ~/.config/project-2026/migration_database_url
sudo chown 10001:10001 ~/.config/project-2026/{pilot.env,database_url,migration_database_url}
sudo chmod 0600 ~/.config/project-2026/{pilot.env,database_url,migration_database_url}
```

檔案權限寬於 0600 會被啟動流程拒絕；container 以 uid 10001 執行，其他 ownership 一律 fail closed。

### 2. 建立 least-privilege 資料庫角色

Pilot profile 宣告 `DATABASE_RUNTIME_ROLE=project_runtime`，migration 會授權它，但不會建立它。未先建立會讓第一次 migration 直接失敗：

```bash
bash docker/scripts/provision-pilot-database-role.sh
```

目前 application 仍以 owning role 連線；把 runtime 連線改到這個 least-privilege role 屬於 Operations & Configuration 的收斂債。

### 3. 啟動 Pilot

`compose.pilot.yaml` 必須是最後一個 `-f`，才能覆蓋 development 預設與 `compose.ai.yaml` 的 diagnostic route：

```bash
export PILOT_ENV_FILE=~/.config/project-2026/pilot.env
export PILOT_DATABASE_URL_FILE=~/.config/project-2026/database_url
export PILOT_MIGRATION_DATABASE_URL_FILE=~/.config/project-2026/migration_database_url

docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  -f docker/compose.pilot.yaml \
  up -d --wait
```

三個 `PILOT_*` 變數缺任何一個，`docker compose config` 會直接失敗，不會退回 development 預設啟動。

### 4. 驗證硬化確實生效

```bash
bash docker/scripts/verify-pilot-security.sh
```

檢查 read-only rootfs、空的 capability bounding set、`NoNewPrivs`、non-root principal、rootfs 寫入被拒、allowlist 路徑可寫、secrets 私有可讀且未進入環境變數，以及 diagnostic/demo/debug routes 不存在。

結構契約本身由 required check `UI_API/tests/test_pilot_container_security.py` 守住。
