# Milestone 1E — Commercial Scope Contract Enforcement TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 1E.

- As an authenticated Admin or Device, every production data operation uses scope derived from my verified principal.
- As a tenant/store owner, another scope cannot read or mutate my operational records even when IDs collide.
- As an existing single-store deployment, legacy APIs continue through the Default Scope compatibility adapter.
- As an operator, scope completeness and hierarchy are machine-verifiable before enforcing NOT NULL.

## Scope Matrix

- Core contract: members tenant; sessions/orders/recommendations tenant+store+origin device; audit tenant+optional store.
- New formal persistence: availability, settings versions, promotions, interactions, intervention outcomes, RAG asset scope metadata.
- Deferred/non-production: demo fixtures, debug session logs, ephemeral model/cache data.

## Initial RED

Command:

```bash
UI_API/.venv/bin/python -m pytest -q UI_API/tests/test_commercial_scope_contract_enforcement.py
```

Result: **RED — 4 failed, 1 passed**. Intended failures prove the missing 0005 migration, principal adapters, scoped operational repository methods, and validator coverage. The existing route guard already passes and becomes a regression boundary.

## Boundary RED

The contract test initially failed four boundaries: no 0005 contract migration, no principal adapters, no scoped operational persistence, and incomplete validator coverage. A later full JSON run exposed one legacy route-test adapter returning `None` instead of a principal; the compatibility branch was kept unscoped only for that mocked legacy shape, while authenticated runtime paths remain scoped.

## GREEN

- `0005_commercial_scope_contract_enforcement.sql` contracts core ownership and adds formal operational tables.
- Admin/Device principals are converted to `CommercialScope` before service/repository calls.
- Availability, settings versions, promotions, interactions/outcomes and RAG ownership metadata use scoped PostgreSQL persistence.
- Default Scope JSON adapters remain backward compatible; ownership-level helpers distinguish tenant/store/device compatibility.
- Contract tests: **5 passed**. Full JSON backend: **236 passed**.

## Security Verification

- Scope comes from authenticated `AdminPrincipal` or `DevicePrincipal`; unverified scope headers remain ignored.
- Parameterized repository filters and composite hierarchy foreign keys enforce ownership.
- Integrity output contains only table/type/count and no PII or connection data.
- RLS is explicitly deferred because the shared database identity cannot safely represent per-request identity; documentation does not claim RLS protection.

## Integration Verification

- PostgreSQL 1D → 1E upgrade/data preservation/isolation/reapply/clean test: **PASS**.
- Full PostgreSQL integration matrix: **5 passed**.
- Migration apply + `validate --require-clean`: **PASS**, five checksums clean.
- `validate_commercial_scope.py --require-complete`: **PASS**, zero violations.
- Ruff affected scope, Ruff format production scope, mypy and application import: **PASS**.
- Frontend type/syntax and shell syntax: **PASS**.
- Python 3.10 runtime: **NOT RUN locally** (runtime unavailable; retained in CI matrix).

## Known Limitations

- PostgreSQL RLS is deferred until per-request database connection identity and a reliable RLS test strategy exist.
- Full RAG lifecycle governance remains Milestone 3C; 1E only establishes scoped metadata persistence.
- JSON compatibility storage is Default Scope only and does not provide multi-tenant or per-device isolation.
