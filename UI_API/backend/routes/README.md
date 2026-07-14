# Backend Routes

`routes/` 是 FastAPI HTTP/WebSocket transport。所有 route 由 `api/route_registry.py` 註冊，再由 `api/router.py` 注入 dependency container。

> 實作盤點：2026-07-14。

## Route 群組

- Core/UI：`core_routes.py` 提供 `/`、`/kiosk`、`/pos`、`/admin`、settings、health、logs、stats 與 legacy checkout。
- Catalog：`menu_routes.py`、`availability_routes.py` 提供菜單、POS banner 與供應狀態。
- Identity：`admin_identity_routes.py` 提供 Admin login/logout/me/rotate；`device_identity_routes.py` 提供 Device session 與 credential issue/rotate/revoke。
- Member：`member_routes.py` 提供登入、註冊、abandoned order、Admin list/export/detail/delete 與 audit logs。
- Recommendation/intervention：`ai_push_routes.py`、`recommendation_event_routes.py`、`interaction_routes.py`。
- Voice/emotion：`voice_routes.py`、`passive_voice_routes.py`、`emotion_routes.py`。
- RAG/promotion：`rag_routes.py` 提供 status、documents、reviews、alerts、rebuild/validate 與 structured promotions。
- Realtime：`realtime_routes.py` 提供 `/ws/{client_type}/{session_id}`，驗證 origin 與 Admin/Device/legacy token。
- Typed v1：`v1_routes.py` 提供 `/api/v1` 統一 response/error envelope、Admin RBAC 與 typed DTO。
- Dev-only：`demo_routes.py`、`test_routes.py`、`debug_routes.py`；商用環境預設關閉。

## `/api/v1` 現況

Read surface 包含 auth principal、commercial context、members、orders、promotions、recommendations、audits、settings 與 RAG reviews。Write surface 包含 settings patch、availability put、promotion create、RAG document create/review/publish/rollback、fleet command 與 order transition。

這些 contracts 已 typed，但目前集中在單一 `v1_routes.py`，且直接依賴部分 service/repository。後續應按 domain 漸進移至 `modules/<domain>/api.py`，保持 URL、operation ID、envelope 與權限相容。

## 維護規則

- Route 只處理 authentication/authorization、rate limit、validation、HTTP mapping 與 request/trace context。
- 不在 route 直接讀寫 JSON/PostgreSQL/Redis/檔案，也不新增 route → repository 依賴。
- Kiosk、Admin、Device 與 WebSocket 使用各自 server policy；query-string token 只保留 legacy/demo 相容。
- 新公開 contract 優先使用 `/api/v1/*`、Pydantic DTO、唯一 operation ID 與 safe error envelope。
- Demo/test/debug route 在 `staging`、`pilot`、`production` 必須 fail closed。
- Route 變更至少執行對應 route/contract/security tests。
