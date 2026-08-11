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

目前 Compose 是 development/local profile。它包含裝置驗證 Admin 與 diagnostic routes，不得直接當成 Pilot 安全部署。後續 Pilot profile 必須使用主機外部 secrets、Redis、備份還原與 fail-closed 設定。
