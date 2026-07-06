# UI_API 模組說明

`UI_API/` 是本專案的核心應用，包含 FastAPI 後端、Kiosk 前端、Admin 後台、RAG 文件、菜單資料、runtime 設定與測試。

## 模組責任

- 提供 Kiosk 與 Admin 靜態頁面。
- 提供所有 API routes。
- 管理會員、推薦、RAG、語音、情緒分析與事件紀錄。
- 支援 JSON 與 PostgreSQL 儲存 backend。
- 管理本機 runtime 設定與 learning data。

## 主要結構

```text
UI_API/
├── main.py              # FastAPI 入口
├── config.py            # 環境變數與 runtime settings
├── backend/             # 後端 API、service、repository
├── frontend/            # Kiosk、Admin、shared frontend
├── menu_data/           # 菜單資料
├── rag_documents/       # RAG 原始文件
├── learning_data/       # runtime 資料
├── tests/               # 自動化測試
├── requirements.txt     # Python 依賴
└── requirements-lock.txt
```

## 後端分層

- `backend/routes`：HTTP API 入口。
- `backend/services`：業務邏輯。
- `backend/repositories`：資料存取。
- `backend/schemas`：資料庫 schema 與資料結構。
- `backend/realtime`：WebSocket 連線與事件推送。
- `backend/bootstrap`：啟動流程與 server helper。
- `backend/utils`：共用工具。

## 前端分層

- `frontend/kiosk`：顧客自助點餐端。
- `frontend/admin`：門市後台。
- `frontend/shared`：共用 API client、HTTP client、realtime client、UI helper 與樣式。

## 啟動

建議從專案根目錄使用腳本：

```bash
bash scripts/start_emotion_llama.sh
```

或：

```bash
bash scripts/start_r1_omni.sh
```

直接啟動 UI_API：

```bash
cd UI_API
python main.py
```

## 測試

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

## 維護重點

- routes 不放複雜業務邏輯。
- services 不處理 HTTP 細節。
- repositories 不反向 import services 或 routes。
- Kiosk 與 Admin 前端不互相 import。
- RAG 原始文件應維持可版本化與可重建。
