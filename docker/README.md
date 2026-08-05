# Project_2026 Docker 安裝與啟動

Compose 檔案集中在本目錄；Docker 的唯一有效環境檔是專案根目錄的 `.env`。
以下指令都從專案根目錄執行。

Docker 只使用專案根目錄的 `.env`。手動執行 Compose 時請加上
`--env-file .env`；`UI_API/.env` 只供原生 Conda `emotion_ui` 啟動的 UI_API
使用，不要把兩個檔案互相複製。`docker/scripts/setup.sh` 已固定使用根目錄 `.env`。

本文件只包含首次安裝、模型放置與日後啟動流程。R1-Omni 權重使用主機本地檔案，不會打包進 Docker image，也不會由腳本下載。

## 1. 準備專案與 R1-Omni 權重

將專案放到主機後，確認四組權重位於：

```text
R1-Omni/models/
├── R1-Omni-0.5B/
├── bert-base-uncased/
├── siglip-base-patch16-224/
└── whisper-large-v3/
```

預設 `.env` 設定為：

```dotenv
R1_MODELS_PATH=../R1-Omni/models
```

如果權重放在其他位置，請先修改 `.env` 的 `R1_MODELS_PATH`。權重必須由使用者自行準備，`docker/scripts/setup.sh` 不會下載 R1-Omni。

## 2. 第一次安裝與啟動（Ubuntu／Debian）

CPU 主機：

```bash
cd ~/Project_2026
bash docker/scripts/setup.sh
```

GPU 主機：

```bash
cd ~/Project_2026
bash docker/scripts/setup.sh --gpu
```

腳本會自動：

1. 安裝 Docker Engine、Docker Compose v2 與必要工具。
2. 建立 `.env`，並在第一次執行時產生資料庫與 Admin 密碼。
3. 檢查 R1-Omni 本地權重。
4. 建置 image 並啟動 PostgreSQL、app、worker、Ollama 與 R1-Omni。

GPU 主機需先安裝 NVIDIA driver；`--gpu` 會在 Ubuntu／Debian 自動安裝 NVIDIA Container Toolkit。

腳本完成時會顯示 Admin 登入密碼，密碼也會保存在專案根目錄的 `.env`。

## 3. 安裝 Ollama 模型

Docker image 不會自動下載 Ollama 模型。首次啟動後手動執行：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml exec ollama ollama pull qwen3.5:4b
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml exec ollama ollama list
```

如果 `.env` 的 `OLLAMA_MODEL` 不是 `qwen3.5:4b`，請將指令中的模型名稱換成相同名稱。

Ollama 模型會保存於 Docker named volume；不要使用 `down --volumes`，否則會刪除模型與資料。

## 4. 日後啟動環境

CPU：

```bash
cd ~/Project_2026
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml up -d --wait
```

GPU：

```bash
cd ~/Project_2026
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up -d --wait
```

如果修改了 Dockerfile 或程式碼，需要重新建置：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

## 5. 查看狀態與停止

查看服務：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml ps
```

服務網址：

```text
Kiosk: http://127.0.0.1:8000/kiosk
Admin: http://127.0.0.1:8000/admin
R1-Omni: http://127.0.0.1:7890
```

停止服務但保留資料、模型與權重掛載：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml down
```

再次啟動時，重新執行第 4 節的 CPU 或 GPU 指令即可。

## 6. NVIDIA NIM（可選）

只使用本地 Ollama 時，不需要 NVIDIA NIM API key；在 Admin「功能設定 → AI 模型」選擇「僅本機」即可。

若要使用 NVIDIA NIM，將以下內容加入 `.env`：

```dotenv
NVIDIA_API_KEY=nvapi-你的金鑰
NVIDIA_API_BASE_URL=https://integrate.api.nvidia.com/v1
```

然後重新建立 app 與 worker：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml up -d --force-recreate app worker
```
