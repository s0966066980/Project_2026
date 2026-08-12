# P7 Legacy Closure Inventory — repository evidence

> 2026-08-12 snapshot, updated after the unversioned surface was withdrawn.
> This document records repository checks only; it does not promote
> target-device, customer-evidence, provider, or Pilot gates.

## Passed static boundaries

| Boundary | Check | Result |
| --- | --- | --- |
| Capability package | Ten manifest keys expose `__init__.py`, `contracts.py`, `interface.py` | Passed |
| Production route imports | No production route imports `modules.*` or `repositories.*` directly | Passed |
| Frontend transport | Admin/Kiosk feature source calls shared `httpClient.js`; raw `fetch` remains only in shared transport | Passed |
| Capability ownership | Route-to-capability ownership map and published `__all__` checks | Passed |
| Identity transport | Admin principal resolution is reached through `capabilities.identity_access` | Passed |
| Operations transport | Realtime observability writes are reached through `capabilities.operations_configuration` | Passed |
| Recommendation transport | AI push composition is reached through `capabilities.recommendation_analytics` | Passed |
| Versioned route split | Monolithic `routes/v1_routes.py` deleted; context, campaign, operations, knowledge, and fleet compatibility modules registered independently | Passed |
| Admin/Kiosk capability clients | Campaign, Knowledge/RAG, Operations, Recommendation, Member (including export/detail/write/delete), diagnostics, push-copy, Project Analyst, and Kiosk v1 calls are owned by `frontend/shared/api/capabilityClients.js`; feature modules no longer assemble `/api/v1` URLs | Passed |
| Identity shims | Unused `services/admin_access_service.py` and `services/admin_identity_service.py` removed | Passed |
| Single published prefix | Unversioned `/api/*` withdrawn; `admin_identity_routes.py` deleted and `core_routes.py` reduced to page entry points ([ADR-0062](../adr/0062-serve-one-versioned-http-prefix.md)) | Passed |
| Capability layer inventory | Eight capability interfaces still read `services`/`repositories`, frozen in `CAPABILITIES_STILL_ON_LEGACY_LAYERS` and allowed only to shrink | Open — 8 of 10 |
| Python quality | Backend Ruff; capability/Optimization mypy (44 files) | Passed |

The exact candidate static/security suite covers these ownership checks; the
running stack publishes **101 `/api/v1` paths and zero unversioned `/api/*`
paths**, down from 93 versioned beside 67 unversioned, and the committed
catalog contract matches the generated schema. This remains repository
evidence, not a full module gate.

The development-only `demo_routes.py`, `diagnostic_routes.py`, and
`debug_routes.py` remain outside the production route boundary and are covered
by their explicit route-contract tests. `diagnostic_routes.py` is now reached
only through `v1_diagnostic_routes.py`; `/api/demo/*` and `/api/debug/*` stay
unversioned on purpose, because they are flag-gated development routes that
answer 404 in a commercial runtime, not contracts.

## Remaining P7 work

1. Move the eight capability interfaces off `services`/`repositories` so each
   owns its data, emptying `CAPABILITIES_STILL_ON_LEGACY_LAYERS`. This is the
   substance of P7 now that the transport prefix is settled; collapsing a URL
   says nothing about who owns the rows behind it.
2. Remove the horizontal `services/repositories/modules` files as each
   capability takes ownership, along with the compatibility shims that remain
   under `services/` (for example `admin_authorization_service.py`, which
   documents itself as removable once callers cut over).
3. Remove legacy tables/columns/jobs/settings and generated artifacts only after
   forward migrations and rollback/repair evidence exist.

The former item "prove runtime legacy telemetry is zero" is closed by removal
rather than by measurement: the paths it would have measured no longer exist.
4. The executable local portion of the 20-part final candidate matrix has now
   been rerun against the captured runtime/test images, including PostgreSQL
   dump/restore and a PostgreSQL-backed runtime restart; remaining matrix rows
   are limited to their documented Pilot, target-device, provider, authorization,
   and runtime-telemetry proof.

### Measured compatibility consumers

The repository search on 2026-08-12 found these shared browser owners of the
versioned envelope (feature modules no longer assemble compatibility URLs):

- `frontend/shared/api/capabilityClients.js`: the single browser capability
  client seam (campaign, RAG, operations, recommendation, member, diagnostics,
  push-copy, Project Analyst, and kiosk);
- `frontend/shared/apiClient.js`: the kiosk application facade, which delegates
  v1 quote, menu pricing, and commercial touch calls to that seam; and
- `frontend/shared/api/v1Client.ts`: the typed versioned transport and error
  envelope owner.

No runtime consumer imports the deleted `routes/v1_routes.py`; the split,
capability-owned versioned modules are the only versioned registrations. The shared owners remain until the runtime
telemetry window and server-side route removal evidence are complete. Member
Admin detail, verified-preference, delete, and CSV export now use the canonical
`/api/v1/members` surface; the legacy `/api/members` routes remain only as a
compatibility registration for the zero-telemetry observation window. The exact
PostgreSQL-backed runtime returned `/live` and `/ready` before and after restart
with 20/20 adapters covered and migration head `0028`; the live Redis
integration against the candidate passed 9/9 tests.

## Non-replaceable inputs

Target Kiosk hardware, Pilot Configuration Authority, customer-evidence
authorization/retention/egress review, and Codex/Claude/Grok CLI credentials are
not available and are intentionally not simulated by repository tests.
