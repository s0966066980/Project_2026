# Backend Schemas 與 PostgreSQL Migrations

`backend/schemas/migrations/` 是正式 PostgreSQL schema source of truth；`membership_postgres.sql` 只是 migration 前的 legacy snapshot。

> 實作盤點：2026-07-14。現有 forward migrations 為 `0001`–`0011`。

## Migration 清單

| 版本 | 範圍 |
| --- | --- |
| `0001` | Membership commercial baseline |
| `0002` | Tenant/store/device commercial scope foundation |
| `0003` | Admin identity、RBAC、revocable sessions |
| `0004` | Device credentials、sessions、events |
| `0005` | Scoped availability/settings/promotion/interaction/RAG ownership 與 NOT NULL contracts |
| `0006` | Member UUID、keyed lookup、encrypted phone metadata 與 child references |
| `0007` | Order aggregate、item/pricing snapshots、idempotency、promotion usage、outcome、transactional outbox |
| `0008` | Durable background jobs、claim/visibility/retry/dead-letter controls |
| `0009` | Durable object-storage metadata；binary 留在 storage backend |
| `0010` | Durable RAG governance metadata；content 以 object reference 管理 |
| `0011` | Recommendation/promotion governance、fleet state/commands、analytics sink |

## 操作

```bash
cd UI_API
python backend/scripts/manage_postgres_migrations.py status
python backend/scripts/manage_postgres_migrations.py validate
python backend/scripts/manage_postgres_migrations.py apply
```

`apply` 需要 `DATABASE_URL`。CI 會在 disposable PostgreSQL 上驗證 migration、重複套用、scope integrity、Member PII、Order/outbox 與 worker production path。

## 維護規則

- 已發布 migration 不修改；修正一律新增下一個 forward migration。
- 破壞性變更採 `expand → dual write/backfill → verify → switch read → contract`。
- 新表使用明確 primary/foreign keys、必要 indexes、scope ownership 與可排序 timestamps。
- Secret、password、raw token、PII key material 不寫入 migration；bootstrap 由 trusted CLI 執行。
- Migration 變更需說明 backup、restore、rollback 或 roll-forward，並驗證 checksum、資料結果與冪等性。
- 商用 runtime 對 PostgreSQL fail closed；不得用 JSON fallback 掩蓋 migration/DB failure。
