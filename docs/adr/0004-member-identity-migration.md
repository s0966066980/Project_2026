# ADR-0004：Member Identity 採 UUID 與相容遷移

- Status: Accepted
- Implementation Status: Implemented in Milestone 1F (phone compatibility column retained)
- 日期：2026-07-13
- Owner：Member / Data / Security

## Context

目前 phone 同時作為會員 PostgreSQL primary key、repository lookup key 與登入識別。這使 PII 成為 domain identity，也阻礙電話變更、tenant scope、加密保存與跨品牌會員策略。

Milestone 1F 已在具備 PostgreSQL integration CI 與 migration checksum gate 的基線上實作此決策。既有 Kiosk phone login 與 legacy API 仍由 compatibility column 支援；新資料路徑可透過 feature flag 漸進切換，不在同一 release 移除相容 contract。

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
- `0006_member_uuid_pii_migration.sql` 已將 Member primary key 切換為 UUID，並以 `(tenant_id, phone_lookup_hash)` 保護新 lookup；相同 phone 可存在於不同 Tenant。
- Phone compatibility column 暫時保留，直到 UUID-preferred/UUID-only 的 production 指標與復原演練完成；它不得再作為公開長期 Domain ID。
- Admin 顯示與匯出只使用 masked phone；刪除新路徑會清除 ciphertext、lookup hash、consent 與 child records，並保存不含 PII 的 anonymized lifecycle row。
- Key Provider 是 application port。Development/Test 使用明確 deterministic adapter；Production/Staging 只接受部署環境或 Secret Manager 注入的版本化 keyring。
- 法務、隱私政策與 retention period 仍需人工審查，本 ADR 與程式測試不構成法律合規聲明。

## Alternatives

- 保留 phone 作為永久 primary key：拒絕，因為 PII 與 domain identity 綁定，電話變更與安全刪除成本過高。
- 只保存未加 pepper 的 phone hash：拒絕，電話號碼空間可枚舉，無法提供足夠保護。
- 一次性切換 Member UUID 並立即移除舊 contract：拒絕，缺少 dual write、backfill 與 verify 階段，部署與資料回復風險不可接受。
- 永久同步維護兩套 Member schema：拒絕；`migrations/*.sql` 是唯一正式 source of truth，legacy snapshot 不手動追平。
