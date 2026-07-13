# ADR-0004：Member Identity 採 UUID 與相容遷移

- Status: Accepted
- Implementation Status: Deferred
- 日期：2026-07-13
- Owner：Member / Data / Security

## Context

目前 phone 同時作為會員 PostgreSQL primary key、repository lookup key 與登入識別。這使 PII 成為 domain identity，也阻礙電話變更、tenant scope、加密保存與跨品牌會員策略。

本 ADR 只保存目標身分模型與遷移決策。Milestone 0.5 不修改 Database Schema、會員 ID、Phone Primary Key、API contract 或 Kiosk/Admin 流程；實作延後至具備 PostgreSQL integration CI 與 migration 強化基線的後續里程碑。

## Decision

採用以下目標會員身分與 PII 設計：

- `Member UUID` 作為內部 domain 與 database primary key。
- `phone_lookup_hash` 用於 exact lookup；hash 必須是 tenant-scoped，並使用 managed pepper。
- `phone_encrypted` 保存可恢復的電話 PII，使用 managed key，金鑰由 KMS 或 Secret Manager 管理。
- `phone_masked` 僅用於顯示、稽核與不需要還原原文的情境。
- Consent、privacy、retention 與 timestamps 使用明確型別並保留可追蹤性。

遷移採 `expand → dual write → backfill → verify → switch read → contract`。遷移期間保留既有 phone API contract，內部則逐步改以 Member UUID reference 運作。

## Consequences

- Member UUID 將 domain identity 與電話 PII 分離，可支援電話變更、安全刪除與後續 tenant isolation。
- tenant-scoped lookup hash、managed pepper、encrypted phone 與 managed key 增加 key rotation、權限與事故處理責任。
- 遷移需要 dual read/dual write metrics、collision handling、backfill checkpoint、verify gate 與 rollback/roll-forward 計畫。
- OTP、PIN 或其他 authentication proof 必須與 identity migration 分開設計；phone lookup 本身不是 authentication。
- 在 Implementation Status 仍為 Deferred 時，現有 Schema、Phone Primary Key、會員 API 與 UI 流程維持不變。

## Alternatives

- 保留 phone 作為永久 primary key：拒絕，因為 PII 與 domain identity 綁定，電話變更與安全刪除成本過高。
- 只保存未加 pepper 的 phone hash：拒絕，電話號碼空間可枚舉，無法提供足夠保護。
- 一次性切換 Member UUID 並立即移除舊 contract：拒絕，缺少 dual write、backfill 與 verify 階段，部署與資料回復風險不可接受。
- 在本 Milestone 直接修改 Schema：延後；Milestone 0.5 僅穩定工程基線，不執行會員資料遷移。
