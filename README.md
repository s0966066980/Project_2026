# Project_2026 — Smart Ordering Kiosk

Project_2026 是以 Docker Compose 執行的單店智慧自助點餐系統。核心應用採模組化單體：同一個 FastAPI 版本提供 Kiosk、Admin 與 API，可靠背景工作由獨立 worker 執行；PostgreSQL、Ollama 與 R1-Omni 則是獨立容器。

目前定位是本機／LAN 開發與單店封閉式 Pilot 的產品基礎，尚未取得 production certification。第一個 Pilot 的交易邊界是可靠建立待付款訂單，再由現場櫃台人工收款；AI、語音與情緒服務故障不得阻止基本點餐。

## 系統架構

```text
Browser
├── Kiosk  顧客點餐
└── Admin  門市管理
      │
      ▼
FastAPI application
├── HTTP / WebSocket API
├── Ordering / Member / Campaign / RAG modules
├── Identity / RBAC / Settings
└── Health / Diagnostics
      │
      ├── PostgreSQL
      ├── Reliable worker / transactional outbox
      ├── Ollama
      └── R1-Omni
```

Docker Compose 啟動六個服務：

| Service | 功能 |
| --- | --- |
| `app` | FastAPI、Kiosk、Admin 與 API |
| `worker` | Durable jobs、RAG publication 與 order outbox |
| `postgres` | PostgreSQL 18 runtime data |
| `migrate` | 啟動時執行 forward migrations，成功後退出 |
| `ollama` | 本機文字模型服務 |
| `r1-omni` | 多模態情緒模型服務 |

Conda 不再是支援的 Project runtime。開發、驗證與部署證據都以 Docker image 和 Compose stack 為準。

## 一鍵安裝與啟動

### 主路徑：NVIDIA GPU

支援 Debian／Ubuntu。主機必須先有可用的 NVIDIA driver，安裝腳本會處理 Docker Engine、Compose plugin 與 NVIDIA Container Toolkit。

```bash
git clone https://github.com/s0966066980/Project_2026.git
cd Project_2026
bash docker/scripts/setup.sh
```

腳本會自動：

1. 安裝並啟用 Docker 與必要主機工具。
2. 設定 NVIDIA Container Toolkit。
3. 建立專案根目錄 `.env` 並產生隨機 PostgreSQL／Admin 密碼。
4. 驗證 R1-Omni 本機權重。
5. 建置 app、worker 與 R1-Omni images。
6. 啟動 Ollama 並拉取 `.env` 的 `OLLAMA_MODEL`。
7. 執行 migrations，啟動完整 stack 並等待 health checks 通過。
8. 顯示 Admin 登入資訊與服務網址。

### CPU 模式

沒有 NVIDIA GPU 時使用：

```bash
bash docker/scripts/setup.sh --cpu
```

CPU 模式可用於功能驗證，但 R1-Omni 與大型語言模型可能非常慢。

若 Docker 與 NVIDIA Container Toolkit 已安裝，可加上 `--no-install` 略過主機套件安裝：

```bash
bash docker/scripts/setup.sh --no-install
```

## R1-Omni 權重

R1-Omni 權重不會被提交到 Git、打包進 image 或由 setup 自動下載。預設必須放在：

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

如果權重位於其他主機目錄，修改根目錄 `.env`：

```dotenv
R1_MODELS_PATH=/absolute/path/to/R1-Omni/models
```

容器會將該目錄唯讀掛載到 `/models`。setup 在 build 前檢查必要檔案，缺少時會列出精確路徑並停止。

## 服務網址

預設只綁定本機 loopback：

```text
Kiosk:   http://127.0.0.1:8000/kiosk
Admin:   http://127.0.0.1:8000/admin
Live:    http://127.0.0.1:8000/live
Ready:   http://127.0.0.1:8000/ready
R1-Omni: http://127.0.0.1:7890
Ollama:  http://127.0.0.1:11434
```

若連接埠已被占用，setup 可能更新 `.env`，完成畫面會顯示實際網址。只有在可信任 LAN 中需要其他裝置存取時，才將 `BIND_ADDRESS` 改成 `0.0.0.0`。

## 日常操作

GPU stack：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up -d --wait
```

查看狀態與 log：

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
  logs -f app worker
```

修改程式或 Dockerfile 後重新建置：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

停止服務但保留 PostgreSQL、模型與 cache：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  down
```

不要使用 `down --volumes`，除非確定要刪除資料庫、Ollama 模型與 AI cache。

## 驗證

核心 Docker smoke test：

```bash
docker/scripts/test.sh
```

AI image dependency smoke test：

```bash
docker/scripts/test-ai.sh
```

快速確認正在運行的服務：

```bash
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:7890/health
```

## 專案結構

```text
Project_2026/
├── docker/                 # Dockerfiles、Compose 與一鍵 setup
├── UI_API/                 # 能力後端、獨立 Admin/Kiosk、worker 與 tests
├── R1-Omni/                # 情緒模型服務；權重位於 models/ 且不入 Git
├── config/profiles/        # 待由 Docker Pilot external config 取代的過渡設定
├── docs/adr/               # 架構決策紀錄
├── CONTEXT.md              # 專案 domain glossary
├── Project_2026_Project_Completeness_Roadmap.md
└── tools/                  # 非 production 的一次性工具
```

更完整的 Docker 操作說明見 [docker/README.md](docker/README.md)，核心應用邊界見 [UI_API/README.md](UI_API/README.md)，能力遷移與清理流程見 [Project Roadmap](Project_2026_Project_Completeness_Roadmap.md)，R1 權重與服務合約見 [R1-Omni/README.md](R1-Omni/README.md)。

## 目前限制

- Compose 目前仍是 development/local profile，不等於安全的 Pilot deployment。
- Redis 尚未加入主要 Compose stack。
- Payment/POS 目前只有 manual adapter。
- CI、不可變 image 發布、備份還原、監控與回滾仍是後續 Pilot readiness gates。
- AI、RAG、STT、TTS 或 R1-Omni 無法使用時，核心菜單、購物車與訂單確認必須維持可用。
