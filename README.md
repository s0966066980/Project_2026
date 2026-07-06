# Smart Ordering Kiosk 智慧自助點餐系統

本專案是一套面向自助點餐機與門市後台的智慧點餐平台。核心應用位於 `UI_API/`，並可選擇串接 `Emotion-LLaMA/` 或 `R1-Omni/` 作為多模態情緒分析服務。

目前系統已具備 Kiosk 自助點餐、Admin 後台、會員手機登入、會員推薦、整體推薦、語音點餐、RAG 知識庫、結構化活動、推薦事件紀錄、PostgreSQL 儲存升級、健康檢查與本機啟動腳本。

## 專案現況分析

### 目前架構

```text
Project_2026/
├── UI_API/           # 主要 FastAPI 應用、Kiosk、Admin、RAG、測試
├── Emotion-LLaMA/    # 可選情緒分析模型服務
├── R1-Omni/          # 可選多模態情緒分析模型服務
├── scripts/          # 本機啟動、PostgreSQL 備份與還原
├── tools/            # 非 production path 的 demo 與維運工具
└── docs/             # 專案後續改善與模組規劃
```

### 核心分層

- `frontend/kiosk`：顧客自助點餐端，負責菜單、購物車、會員登入、語音點餐、推薦顯示與結帳。
- `frontend/admin`：門市後台，負責設定、會員管理、RAG、活動、推薦事件、健康檢查與測試工具。
- `backend/routes`：API 入口，只處理 HTTP request / response、權限與呼叫 service。
- `backend/services`：業務邏輯層，包含會員、推薦、RAG、語音、情緒分析、活動、事件與健康檢查。
- `backend/repositories`：資料存取層，隔離 JSON 與 PostgreSQL。
- `backend/schemas`：資料庫 schema 與跨層資料結構。
- `rag_documents`：RAG 原始知識文件來源。

### 架構優點

- 後端已逐步形成 `routes -> services -> repositories` 的分層。
- 會員資料已具備 JSON 與 PostgreSQL 切換路徑。
- 推薦系統已開始整合會員偏好、活動、供應狀態、RAG verified offer 與事件紀錄。
- Admin 已涵蓋商用營運會需要的維運面板：會員、RAG、活動、健康檢查與推薦事件。
- 啟動腳本已可協助本機啟動 UI、Ollama、模型服務與 PostgreSQL。

### 目前主要風險

- `frontend/admin/admin.js`、`frontend/admin/admin.html`、`frontend/kiosk/app.js`、`frontend/shared/styles.css` 仍偏大，後續應拆模組。
- Admin 與 Kiosk 雖已分目錄，但前端狀態與 API 呼叫仍可再抽象化。
- RAG、推薦、活動與會員上下文已整合，但仍需要更完整的商用監控與回歸測試。
- Emotion-LLaMA / R1-Omni 屬大型模型服務，商用部署時應獨立 process 或容器。
- 第三方模型與資料授權需要在商用前逐項確認。

## 功能總覽

- Kiosk 自助點餐：菜單瀏覽、購物車、會員手機登入、結帳與訂單完成流程。
- Admin 後台：設定、會員、RAG、結構化活動、推薦事件、健康檢查。
- 會員推薦：根據會員點餐紀錄、常點品項、互動事件與活動資料產生推薦上下文。
- 整體推薦：結合熱門品項、供應狀態、活動與 RAG verified offer。
- 結構化活動：Admin 可設定會員限定活動、推薦加權、加購優惠價與 Kiosk 活動廣告詞。
- 語音模式：支援語音點餐，並可帶入會員與推薦上下文。
- RAG 知識庫：支援 Markdown、TXT、JSON、CSV 來源；目前文件政策以 README 與 TXT/JSON/CSV 為主。
- PostgreSQL：會員與推薦事件可升級到 PostgreSQL backend。
- 模型服務：可選 Emotion-LLaMA 或 R1-Omni 作為情緒分析 provider。

## 模組 README

- [UI_API](UI_API/README.md)
- [UI_API backend](UI_API/backend/README.md)
- [UI_API frontend](UI_API/frontend/README.md)
- [UI_API RAG documents](UI_API/rag_documents/README.md)
- [UI_API tests](UI_API/tests/README.md)
- [Emotion-LLaMA](Emotion-LLaMA/README.md)
- [R1-Omni](R1-Omni/README.md)
- [scripts](scripts/README.md)
- [tools](tools/README.md)
- [docs](docs/README.md)

後續改善與可新增模組請看 [docs/FUTURE_MODULES.md](docs/FUTURE_MODULES.md)。

## 安裝

依賴檔依子專案管理：

| 子專案 | 依賴檔 |
| --- | --- |
| UI_API backend | `UI_API/requirements.txt` |
| UI_API frontend | `UI_API/frontend/package.json` |
| Emotion-LLaMA | `Emotion-LLaMA/requirements.txt` |
| R1-Omni | `R1-Omni/requirements.txt` |

建議環境：

```bash
conda create -n emotion_ui python=3.10 -y
conda activate emotion_ui
pip install -r UI_API/requirements.txt
```

若使用前端檢查工具：

```bash
cd UI_API/frontend
npm install
```

## 本機啟動

使用 Emotion-LLaMA：

```bash
bash scripts/start_emotion_llama.sh
```

使用 R1-Omni：

```bash
bash scripts/start_r1_omni.sh
```

預設網址：

```text
Kiosk: http://127.0.0.1:9000/kiosk
Admin:  http://127.0.0.1:9001/admin
```

## 常用環境變數

| 變數 | 用途 |
| --- | --- |
| `APP_ENV` | `development`、`staging`、`production` |
| `APP_PORT` | Kiosk / API port |
| `ADMIN_PORT` | Admin port |
| `SECURITY_ENFORCED` | 是否強制 token 驗證 |
| `ADMIN_API_TOKEN` | Admin API token |
| `KIOSK_DEVICE_TOKEN` | Kiosk device token |
| `MEMBER_STORAGE_BACKEND` | `json` 或 `postgres` |
| `DATABASE_URL` | PostgreSQL DSN |
| `MODEL_NAME` | Ollama 模型名稱 |
| `POSTGRES_ENABLED` | 啟動腳本是否處理 PostgreSQL |

## PostgreSQL

啟動腳本會使用 `scripts/lib_postgres.sh` 準備本機 PostgreSQL。預設連線資訊：

```text
POSTGRES_USER=ui_api_user
POSTGRES_PASSWORD=ui_api_password
POSTGRES_DB=ui_api_migration_test
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

可手動備份與還原：

```bash
bash scripts/backup_postgres.sh
bash scripts/restore_postgres.sh backups/postgres/<dump-file>.dump
```

## 測試

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

前端語法檢查：

```bash
find UI_API/frontend -type f -name '*.js' -print0 | xargs -0 -n1 node --check
```

腳本語法檢查：

```bash
bash -n scripts/start_emotion_llama.sh
bash -n scripts/start_r1_omni.sh
```

## 文件整理規則

本次文件整理後，專案只保留：

- 各模組 `README.md`
- `docs/FUTURE_MODULES.md`

RAG 知識內容若不是 README，應使用 `.txt`、`.json` 或 `.csv`，避免文件散落成多份規劃檔。

## 商用前檢查

- 使用 PostgreSQL backend。
- 設定 production token 與 CORS allowlist。
- 關閉 demo、test、debug routes。
- 將 UI_API、Ollama、Emotion-LLaMA / R1-Omni 與 PostgreSQL 拆開部署。
- 補上瀏覽器端 smoke test 與推薦流程回歸測試。
- 逐項確認第三方模型、資料與圖片授權。
