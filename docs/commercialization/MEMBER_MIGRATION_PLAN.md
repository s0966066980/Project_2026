# 會員 Identity Backward-compatible Migration Plan

狀態：Planning only；Milestone 0 不執行 schema 或資料變更

## Current Model

- `members.phone` 是 primary key。
- Member session、order、preference 與 service lookup 依賴 phone。
- phone 同時扮演 lookup identifier 與登入 proof，存在 PII 與 authentication 風險。
- JSON 與 PostgreSQL backend 必須在 transition period 同時被考慮。

## Target Model

```text
members
├── id UUID PRIMARY KEY
├── tenant_id UUID NOT NULL
├── phone_lookup_hash BYTEA/TEXT NOT NULL
├── phone_encrypted BYTEA NOT NULL
├── phone_masked TEXT NOT NULL
├── consent_version TEXT
├── privacy_version TEXT
├── retention_until TIMESTAMPTZ
├── created_at TIMESTAMPTZ NOT NULL
└── updated_at TIMESTAMPTZ NOT NULL
```

所有 member foreign key 改指向 `member_id`；store/device/session context 另外保存，不把 phone 複製到事件與訂單。

## Preconditions

- Tenant model 與 default tenant mapping 已建立。
- Encryption key、lookup pepper、rotation 與 disaster recovery policy 已核准。
- OTP/PIN authentication ADR 已完成。
- Production backup 與 restore drill 通過。
- Member data retention、deletion 與 consent policy 已確認。

## Migration Phases

### Phase 0：Inventory and Dry Run

- 統計 member/order/session/preference/event 筆數與 phone 格式。
- 找出 invalid/duplicate/collision/deleted record。
- 產生不含明文 phone 的 dry-run report。
- 定義 backfill throughput、checkpoint 與 abort threshold。

Rollback：無寫入。

### Phase 1：Expand

- 新增 nullable `members.id`、`tenant_id`、hash/encrypted/masked/timestamps。
- 關聯表新增 nullable `member_id`。
- 新增 unique/index，但暫不移除 phone constraint。
- Migration 只新增，不改現有讀寫。

Rollback：停止新程式並保留新增 nullable 欄位；不做 destructive down migration。

### Phase 2：Dual Write

- Compatibility repository 在新/舊會員寫入時同時維護 UUID 與 legacy phone 欄位。
- 每次 dual write 產生 metric，不記錄明文 phone。
- 新 session/auth flow 內部優先使用 UUID，legacy API 在入口轉換。

Rollback：feature flag 切回 legacy read/write；保留已寫入新欄位。

### Phase 3：Backfill

- 使用可重入、分批、具 checkpoint 的 worker job。
- UUID 穩定生成並持久化；不得每次重跑產生不同 ID。
- 使用 tenant-scoped lookup hash 與 managed encryption key。
- 關聯表依 legacy phone 回填 member_id。

Rollback：停止 job；已完成 batch 保留。修正後由 checkpoint 繼續，不反向刪除。

### Phase 4：Verify

- 比對 entity/relationship count、orphan、hash uniqueness、decrypt sample、consent/retention。
- Shadow read 同時查 legacy/new model，記錄 mismatch metric。
- 針對登入、history、checkout、recommendation、export/delete 執行 integration test。

Abort threshold：任何跨 tenant mapping、無法解密、錯綁 order/session 或不可解釋 count mismatch。

### Phase 5：Switch Read

- Feature flag 將 production read 切到 UUID/new columns。
- Legacy API 透過 compatibility lookup，response contract 不變。
- 持續 dual write一個完整觀察期。

Rollback：立即切回 legacy read；新欄位與 dual write 保留以供分析。

### Phase 6：Contract

僅在觀察期、restore drill、audit 與 legacy usage 歸零後：

- 將新欄位改為 NOT NULL。
- Foreign key 切到 member UUID。
- 移除 phone 作為 PK/關聯鍵。
- 明文 phone legacy column 在 retention/backup policy允許後移除。
- 移除 dual write 與 compatibility code。

Contract phase 不提供自動 destructive rollback；使用 pre-contract backup 與 roll-forward migration。

## Authentication Migration

Identity migration 不等於 authentication。OTP/PIN flow 必須：

- 不洩漏會員是否存在。
- 具 per-IP/per-device/per-identifier rate limit。
- OTP 短效、單次、hashed storage、attempt limit。
- 成功後簽發短效 member session，不把 phone 當 session credential。
- 具 tenant/store/device scope 與 audit。

## Required Tests

- Migration forward/checksum/idempotency/resume。
- Duplicate/invalid phone 與 hash collision。
- Dual-write partial failure。
- Shadow-read mismatch。
- Tenant isolation。
- Key rotation/decrypt failure。
- Member export/delete/retention。
- Legacy API compatibility。
- Backup restore 後 migration resume。

## Metrics

- backfill processed/failed/remaining。
- dual-write success/failure。
- shadow-read mismatch rate。
- legacy lookup usage。
- OTP request/success/failure/lockout（不含 PII label）。
