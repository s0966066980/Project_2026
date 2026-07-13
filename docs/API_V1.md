# API v1 Contract

`/api/v1` 是新商業整合的 typed、versioned HTTP contract。既有 `/api/*` 在 caller 完成遷移前維持相容，不會因 v1 建立而刪除或改變。

## 共通契約

- 成功回應使用 `data` 與 `meta`；`meta` 包含 `req_` 前綴的 `request_id` 與 UTC timestamp。
- 集合使用 `page`、`page_size`、`total`、`total_pages`，並以明確 query schema 驗證 filter 與 sort。
- UUID 與 timestamp 由 Pydantic DTO 驗證，不直接公開 repository record。
- 失敗回應使用 `error.code`、安全訊息、`request_id` 與有限 validation details；不回傳 stack、SQL、credential 或原始 exception。
- 每個 operation 使用唯一 `v1_` operation ID、領域 tag、typed response 與 OpenAPI auth metadata，可供 client generation。

## Authentication 與 Scope

Admin read surface 支援 HttpOnly `admin_session` cookie 或 Bearer credential。實際認證與 permission enforcement 由共用 server policy 執行，OpenAPI security declaration 不取代授權。

Commercial scope 只來自已驗證 Admin principal 與 server-side store assignment。未驗證的 `X-Tenant-ID`、`X-Store-ID`、`X-Device-ID` 不會覆寫 scope。

## 第一階段 Read Surface

依 caller migration 順序提供 auth/me、commercial context、member、order、promotion、recommendation、audit、settings 與 RAG review read contract。Write contract 暫時保留既有 API，待 caller 與 idempotency contract 個別遷移。

## Compatibility

Legacy routes 保留既有 response/error shape。只有 `/api/v1/*` 使用統一 envelope；client 應以 OpenAPI schema 生成或維護 typed adapter，不應混用兩種 response shape。
