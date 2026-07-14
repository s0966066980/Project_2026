# UI_API 核心應用

`UI_API/` 是 Project_2026 的核心應用，包含 FastAPI、Kiosk、Admin、RAG、菜單資料、runtime 設定與自動化測試。

## 責任

- 提供現有 `/kiosk`、`/admin`、`/api/*` 與 WebSocket。
- 管理菜單、會員、訂單、活動、供應狀態、推薦、RAG、語音、情緒分析與事件。
- 支援 JSON compatibility storage 與 PostgreSQL。
- 提供健康檢查、audit、observability 與 production boundary。

## 結構

```text
UI_API/
├── main.py              # FastAPI 入口
├── config.py            # 現行環境與 runtime settings
├── backend/             # API、service、repository、schema、realtime
├── frontend/            # Kiosk、Admin、shared frontend
├── menu_data/           # 菜單來源
├── rag_documents/       # RAG 原始知識
├── learning_data/       # 本機 runtime 資料，不提交內容
├── tests/               # Backend tests
├── requirements.txt     # 完整 runtime 依賴
└── requirements-ci.txt  # CPU-only CI 依賴
```

## 啟動

建議從 Repository 根目錄：

```bash
bash scripts/start_emotion_llama.sh
# 或
bash scripts/start_r1_omni.sh
```

只啟動核心應用：

```bash
cd UI_API
python main.py
```

## 驗證

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

CI 另執行 Ruff、mypy 與 application import check，實際範圍以 `.github/workflows/ci.yml` 為準。

## 邊界

- Route 只處理 transport、authentication、authorization、validation 與 response。
- Service 負責 workflow 與業務規則，不依賴 FastAPI Request/Response。
- Repository 負責資料來源，不反向 import service/route。
- 新跨層 contract 優先使用明確 schema，不擴大大型無型別 `dict`。
- Kiosk 與 Admin 不互相 import business state。
- 大型模型不應成為核心 API process 的必要 import 或啟動條件。
- 新架構方向與工作邊界見 [`AGENTS.md`](../AGENTS.md)。
