# ADR-0004：會員 Identity 採 UUID 與 Backward-compatible Migration

- 狀態：Accepted for planning；implementation deferred to Milestone 2
- 日期：2026-07-13

## Context

目前 phone 是會員 PostgreSQL primary key、repository lookup key 與登入 credential。此設計使 PII 成為 domain identity，也無法自然支援 tenant scope、電話變更、加密或跨品牌會員策略。

## Decision

目標 member identity：

- `id UUID` 作為 domain/database primary key。
- `tenant_id UUID` 作為必要 scope。
- `phone_lookup_hash` 用於 exact lookup，hash 必須 tenant-scoped 並使用 managed pepper。
- `phone_encrypted` 儲存可恢復 PII；金鑰由 KMS/Secret Manager 管理。
- `phone_masked` 僅用於顯示與 audit。
- Consent、privacy、retention 與 timestamps 使用明確型別。

採 expand → dual write → backfill → verify → switch read → contract。舊 phone API contract 在 migration period 保持可用，但內部立即轉換為 UUID member reference。

## Consequences

- 能支援電話變更、tenant isolation、PII encryption 與安全刪除。
- Migration 需要 dual-read/dual-write metrics、collision handling、backfill checkpoint 與 rollback。
- OTP/PIN 或其他 authentication proof 必須和 identity migration 分開設計，不能把 phone lookup 當 authentication。

## Guardrail

Milestone 0 不新增欄位、不回填、不改 primary key、不修改會員 UI 或 API。執行細節記錄於 `docs/commercialization/MEMBER_MIGRATION_PLAN.md`。
