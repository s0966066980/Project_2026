# Backend Repositories

`repositories/` 隔離 JSON、PostgreSQL 與 Redis I/O。它是 persistence adapter 集合，不是業務規則層。

> 實作盤點：2026-07-14。

## Repository 分組

- Identity/scope：`admin_identity_repository.py`、`device_identity_repository.py`、`admin_audit_repository.py`。
- Member/session：`member_repository.py`、`member_session_repository.py`、`session_repository.py`。
- Catalog/commerce：`menu_repository.py`、`availability_repository.py`、`commercial_settings_repository.py`、`promotion_repository.py`。
- Ordering：`checkout_order_repository.py` 保存 Order aggregate、snapshots、idempotency 與 outbox。
- Interaction/recommendation：`interaction_event_repository.py`、`recommendation_event_repository.py`、`emotion_log_repository.py`、`log_repository.py`。
- RAG/object：`rag_asset_scope_repository.py`、`rag_governance_repository.py`、`object_storage_repository.py`。
- Async/shared：`worker_job_repository.py`、`postgres_worker_store.py`、`redis_shared_adapter.py`。
- PostgreSQL foundation：`postgres_utils.py` 處理 connection、migration plan/checksum、advisory lock 與 fail-closed backend selection。

`modules/identity/adapters/postgres.py` 是已抽離 Identity module 的 adapter；舊 `repositories/admin_identity_repository.py` 仍存在於相容路徑，勿擴大其跨模組責任。

## Storage 現況

- `development` / `test` 可使用 JSON compatibility data。
- `staging` / `pilot` / `production` 必須設定 PostgreSQL，且禁止 DB failure 靜默 fallback 到 JSON。
- Redis 提供 shared cache、rate limiting 與 lock，不是商業資料 Source of Truth。
- Object bytes 由 local/S3 storage service 處理；PostgreSQL repository 保存 metadata，不把 binary 塞入資料表。

## 維護規則

- Repository 不 import route，也不決定價格、推薦、promotion eligibility、權限或狀態轉移策略。
- 每個 scoped read/write 必須保留 tenant/store/device ownership，不能只靠前端過濾。
- 新 schema 使用 forward migration；已發布 migration 不改寫。
- Repository 變更至少跑最近的 unit test；PostgreSQL/Redis 路徑再跑對應 integration test。
- 不在 log/test output 顯示 raw credential、完整 PII、document content 或 production payload。
