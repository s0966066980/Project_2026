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

Pending upgrade/data preservation/isolation/clean validation integration.

## GREEN

Pending implementation.

## Security Verification

Pending principal-only scope, header override denial, repository filters, and no false RLS claim.

## Integration Verification

Pending target/full JSON/PostgreSQL/static/frontend/shell gates.

## Known Limitations

- PostgreSQL RLS is deferred until per-request database connection identity and a reliable RLS test strategy exist.
- Full RAG lifecycle governance remains Milestone 3C; 1E only establishes scoped metadata persistence.
