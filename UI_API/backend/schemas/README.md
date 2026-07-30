# Backend Schemas 與 PostgreSQL Migrations

`backend/schemas/migrations/` 是正式 PostgreSQL schema source of truth；`membership_postgres.sql` 只是 migration 前的 legacy snapshot。

現有 forward migrations 為 `0001`–`0015`。

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
| `0013` | 清除 retired summer promotion operational records；保留已成交訂單的 immutable pricing snapshots |
| `0014` | Governed Document lifecycle 新增 explicit approved/rejected review states |
| `0015` | RAG 知識新增 indexing/index_failed 背景索引狀態 |
| `0016` | Store-scoped RAG Intelligence Studio state |
| `0017` | Knowledge Publication durable lifecycle、attempt、batch 與 audit |
| `0018` | Voice Turn durable phase journal |
| `0019` | Cart、Checkout Quote、Order 與 outbox |
| `0020` | Ordering Entry Flow durable state |
| `0021` | Ad Hoc Retrieval Check proof 與 RAG Readiness Confirmation |
| `0022` | Checkout pickup number |
| `0023` | Menu item push copy |
| `0024` | Push copy batches |
| `0025` | Store-scoped menu catalog master (`store_menu_items`); `menu.json` is seed-only |

`0012` 採 expand-only。若套用後需要恢復服務，舊的 `promotion_records`、`recommendation_events` 與
`analytics_event_log` 仍可繼續讀寫；修復方式是新增下一個 forward migration，不回寫或刪除 `0012`。

`0014` 只擴充 `rag_document_versions.status` 的合法值。若需回復舊版應用程式，先停止產生
`approved`／`rejected` rows；已存在的新狀態不可直接套回舊 CHECK constraint，修復需使用新的
forward migration 或先完成狀態資料轉換。

`0015` 同樣只向前擴充狀態 constraint。舊 review 狀態仍可讀取，新 knowledge API
只會產生 draft、indexing、index_failed、published、retired。

## 操作

```bash
cd UI_API
python backend/scripts/manage_postgres_migrations.py status
python backend/scripts/manage_postgres_migrations.py validate
python backend/scripts/manage_postgres_migrations.py apply
```

`apply` 需要 `DATABASE_URL`。
