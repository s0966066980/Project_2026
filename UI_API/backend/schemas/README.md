# Backend Schemas 與 PostgreSQL Migrations

`backend/schemas/migrations/` 是正式 PostgreSQL schema source of truth；`membership_postgres.sql` 只是 migration 前的 legacy snapshot。

現有 forward migrations 為 `0001`–`0012`。

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
| `0012` | Versioned campaigns、recommendation decisions、visible touch events、order-item attribution |

`0012` 採 expand-only。若套用後需要恢復服務，舊的 `promotion_records`、`recommendation_events` 與
`analytics_event_log` 仍可繼續讀寫；修復方式是新增下一個 forward migration，不回寫或刪除 `0012`。

## 操作

```bash
cd UI_API
python backend/scripts/manage_postgres_migrations.py status
python backend/scripts/manage_postgres_migrations.py validate
python backend/scripts/manage_postgres_migrations.py apply
```

`apply` 需要 `DATABASE_URL`。
