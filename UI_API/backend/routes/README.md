# routes 模組說明

`routes/` 是 FastAPI API 入口層。

## 責任

- 接收 HTTP request。
- 執行 token / rate limit / query / form parsing。
- 呼叫 service。
- 回傳 response。

## 主要 routes

- `core_routes.py`：核心頁面、菜單、checkout 等流程。
- `member_routes.py`：會員登入、註冊、管理查詢。
- `ai_push_routes.py`：AI 推薦。
- `voice_routes.py`：語音點餐。
- `rag_routes.py`：RAG 文件、Chroma 重建、審核與活動管理。
- `recommendation_event_routes.py`：推薦事件紀錄與 dashboard。
- `v1_routes.py`：typed、versioned Admin read surface 與一致 pagination/envelope；實際授權沿用共用 server policy。
- `availability_routes.py`：供應狀態。
- `emotion_routes.py`：情緒分析。
- `realtime_routes.py`：WebSocket。
- `demo_routes.py`、`test_routes.py`、`debug_routes.py`：開發與測試用途，production 必須關閉。

## 維護規則

- 不在 route 寫大型業務邏輯。
- 不在 route 直接讀寫 JSON / PostgreSQL。
- 新增 Admin API 時要確認 production 權限。
- 新公開 contract 使用 `/api/v1/*`、Pydantic DTO、唯一 operation ID 與 safe error envelope；legacy route 保留相容。
- 新增 Kiosk API 時要確認 kiosk token 與 rate limit。
