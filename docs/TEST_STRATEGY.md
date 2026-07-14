# Test Strategy (Local-first)

## Goals

1. Daily edit loop finishes in minutes, not full-suite duration.
2. Core commercial risk (auth, scope, money, worker/outbox, PII) stays protected.
3. Integration uses host PostgreSQL/Redis without Docker.
4. Extended regression runs on milestone/release only.

## Tiers

| Tier | Scope | Command (planned) | When |
| --- | --- | --- | --- |
| 0 Static | ruff/mypy/compile/typecheck/syntax | `scripts/local/test_fast` partial | Every change |
| 1 Fast Core | `smoke or core or security` | `pytest -q -m "smoke or core or security"` | Every change |
| 2 Domain | affected domain markers | targeted pytest | Domain changes |
| 3 Integration | host Postgres (+ optional Redis) | `scripts/local/test_integration` | Milestone / PR main |
| 4 Extended | full backend + frontend unit + critical E2E | `scripts/local/test_full` | Milestone / release |
| 5 External | payment/cloud/pos/telemetry | manual | External only |

## Markers (to register in L4)

`smoke`, `core`, `security`, `identity`, `checkout`, `worker`, `rag`, `recommendation`, `fleet`, `analytics`, `api`, `integration`, `extended`, `external`

## Keep vs remove policy

See `CODEX_LOCAL_FIRST_ROADMAP.txt` section 5 and L0 classifications in `docs/TEST_INVENTORY.md`.

- **KEEP_CORE / KEEP_INTEGRATION**: never blind-delete.
- **REMOVE_REDUNDANT / MOVE_EXTENDED**: only after L4 with `docs/TEST_REMOVAL_LOG.md`.
- No skip/xfail/swallow to pass gates.

## L0 inventory summary

| Classification | Backend functions |
| --- | --- |
| KEEP_CORE | 238 |
| KEEP_INTEGRATION | 70 |
| MOVE_EXTENDED | 33 |
| REMOVE_REDUNDANT | 11 |

Frontend: keep v1 client, legacy allowlist, feature boundaries; critical E2E remains extended tier.

## Regenerating inventory

```bash
python3 tools/test_inventory.py --json docs/test_inventory_raw.json --md docs/TEST_INVENTORY.md
```
