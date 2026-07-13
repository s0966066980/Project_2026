# TDD — Milestones 7A–7C API Write + Frontend Cutover Freeze

## 7A RED/GREEN

- OpenAPI exposes v1 write operations for settings/availability/promotions/RAG/fleet/orders.
- Typed request DTOs with extra=forbid.

## 7B RED/GREEN

- v1Client post/put/patch available.
- Admin settings feature module uses v1 only.

## 7C RED/GREEN

- legacy-api-allowlist.json freezes residual fetch('/api/').
- Vitest fails on unlisted legacy fetches.

## Classification

PRODUCTION_PATH_PASS for typed write surface + allowlist freeze. Full UI feature migration remains incremental.
