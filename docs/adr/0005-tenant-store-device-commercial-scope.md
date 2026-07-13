# ADR-0005：Tenant / Store / Device Commercial Scope

- Status: Accepted
- Implementation Status: Contract Enforced
- 日期：2026-07-13
- Owner：Commercial Platform / Data / Security

## Context

現有系統以單一門市與單一 Kiosk 運作，PostgreSQL 商業資料沒有一致的 ownership scope。商用化需要先建立 `Tenant → Store → Device` hierarchy，同時不能破壞既有 `/kiosk`、`/admin`、`/api/*`、WebSocket、JSON backend 或 phone-based member identity。

## Decision

採用下列 hierarchy：

```text
Tenant
└── Store
    └── Device
```

Ownership 定義如下：

- Tenant owns Store、Admin Scope、Member Scope 與 Business Data。
- Store owns Catalog Availability、Order、Session、Promotion Scope 與 Operational Data。
- Device owns Kiosk Runtime、Interaction Event、Session Origin 與 Device Health。

本階段以不可變 versioned migration 建立 `tenants`、`stores`、`devices`，並對實際存在的 PostgreSQL 表採 expand-first scope columns、legacy backfill、foreign keys 與 indexes。新 application records 使用 Python `uuid.uuid4()`；migration only legacy defaults 使用文件化 reserved UUID。

## Compatibility Strategy

- Default Tenant `00000000-0000-4000-8000-000000000001`。
- Default Store `00000000-0000-4000-8000-000000000002`。
- Legacy Kiosk `00000000-0000-4000-8000-000000000003`。
- 現有 unscoped repository method 由 server resolver 取得 Default Scope，再委派 scoped method。
- Legacy PostgreSQL rows backfill 到 Default Scope；舊 key、phone primary key 與 API contract 不刪除。
- Scope columns 暫時 nullable，以降低 existing database upgrade 的 table rewrite/lock 與未盤點資料風險；完整 `NOT NULL` enforcement 是後續 migration gate。
- JSON compatibility storage 僅支援 Default Scope，不宣稱具備多租戶隔離。

## Security Boundary

Commercial scope 只可來自 server configuration，或未來通過驗證的 Admin/Device identity。未驗證的 `X-Tenant-ID`、`X-Store-ID`、`X-Device-ID` 一律忽略，不得成為 tenant isolation boundary。Repository scoped query 必須帶明確 `CommercialScope` 並同時比對 ownership columns。

本 ADR 只建立資料與 server-side contract；不提供 Admin RBAC、Device Credential 或 client scope selector。

## Consequences

- Default Scope 保持單門市流程與既有 contract。
- Composite Store/Tenant foreign key 阻止 Device 指向其他 Tenant 的 Store。
- Scoped methods 可防止相同資料 ID 繞過 Tenant/Store filter。
- Nullable legacy columns 代表 isolation foundation 尚未等同完整 tenant isolation；production enforcement 前仍需資料驗證與 contract migration。
- Phone 仍是 global primary key，因此相同 phone 無法自然存在於不同 Tenant；此限制由 ADR-0004 Member UUID migration 解決。
- Foundation migration 0002 未虛構 availability/interaction schema；後續 0005 依正式 ownership matrix 建立 scoped PostgreSQL persistence，JSON 只保留 Default Scope compatibility。

## Contract Enforcement Addendum

Milestone 1E 以 forward migration `0005` 完成 core scope `NOT NULL`，並將 availability、settings version、promotion、interaction/intervention outcome 與 RAG ownership metadata 納入 PostgreSQL。Production caller 的 scope 由已驗證 Admin/Device principal 解析；未帶 scope 的方法只保留 Default Scope compatibility。

PostgreSQL RLS 暫不啟用。Application 目前使用共用 database connection identity，無法讓 database policy可信地區分每個 Admin/Device request；在缺少 transaction-local identity 與 isolation integration strategy 時啟用 RLS 會造成錯誤安全感。現階段以 parameterized scoped query、composite FK、unique/index 與 integrity validator 強制邊界；未來導入 RLS 必須使用新 ADR 與 forward migration。

## Alternatives

- 信任 client scope headers：拒絕，header 可偽造，不能作 isolation boundary。
- 一次替所有資料加入 Tenant/Store/Device：拒絕，ownership 不一致且會製造錯誤 scope。
- 立即將所有 scope column 設為 `NOT NULL`：延後，existing database migration lock 與未知 legacy rows 風險較高。
- 同時修改 `membership_postgres.sql`：拒絕；它是 legacy snapshot，正式 source of truth 是 migrations。
- 同步實作 RBAC、Device Credential 或 Member UUID：拒絕，超出本 Milestone 且增加破壞性 migration 風險。
