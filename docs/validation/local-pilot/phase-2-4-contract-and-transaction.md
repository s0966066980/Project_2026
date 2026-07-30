# Phases 2–4 — Contract and Transaction Convergence

- Evidence date: 2026-07-28 (Asia/Taipei)
- Status: **Automated engineering gate passed; Phase 4 operator sign-off pending**
- Revision: `723f87c` on `main`
- Worktree: dirty; evidence applies to the tested working tree, not only the revision
- Runtime profile: `local-pilot`
- Database fingerprint: `e2343247250475d8`
- PostgreSQL: 18, primary, single-host topology
- Migration head: `0022_checkout_pickup_number` (22 applied, none pending)

## Phase 2 — Identity and authorization

The runtime uses password-authenticated durable Admin sessions and database-owned
device sessions. Anonymous Admin access is rejected, permissions come from the
central catalog, and the active RAG permissions are `rag.read`, `rag.write`, and
`rag.publish`. The superseded `rag.review` capability is not an active permission.

The complete backend run includes the identity, RBAC, v1 contract, member,
commercial-scope, and security suites and finished with **514 passed** and no
failures.

## Phase 3 — Frontend and transport contracts

The shared API client, Admin authentication fixture, Voice Turn durable event
protocol, and RAG Admin shapes are aligned with their backend contracts. Current
evidence:

| Command family | Result |
| --- | ---: |
| Vitest unit suite | 20 files, 64 tests passed |
| TypeScript typecheck | passed |
| JavaScript syntax check | passed |
| Vite production build | passed |
| Playwright | 14 of 14 passed |

Playwright covers authenticated Admin navigation plus the current Kiosk member,
ordering, voice, and Admin emotion diagnostic browser flows.

## Phase 4 — Core transaction loop

The automated module, route, and browser coverage now exercises guest/member
entry, menu readiness, server-authoritative cart/quote values, confirmation
idempotency, pickup-number projection, Payment Pending, worker delivery, and the
defined recovery cases. The full backend and browser suites are green.

The repository does not contain a signed record from the designated human store
operator for one guest and one member order on this exact working tree. That is
an acceptance-evidence gap, not a known failing transaction. Phase 4 therefore
cannot be represented as formally operator-approved until that short real-machine
check is signed in the Phase 7 record.

## Gate conclusion

Phases 2 and 3 pass. Phase 4 implementation and automated evidence pass; its
formal exit gate remains pending only for designated-operator evidence. No P0 or
P1 defect was observed in these phases.
