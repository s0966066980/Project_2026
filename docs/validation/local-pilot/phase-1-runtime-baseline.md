# Phase 1 — Reproducible Runtime Baseline

> Historical evidence note: this record captures the first passing baseline. The
> current migration head, emotion diagnostic contract, and complete regression
> results are recorded in the later phase records in this directory; they
> supersede those portions of this point-in-time record without rewriting it.

- Date: 2026-07-28 (Asia/Taipei)
- Status: **Passed**
- Revision: `723f87c` on `main`
- Worktree: dirty; evidence applies to the working tree, not only the revision above
- Target profile: `local-pilot`
- Running profile during final evidence capture: `local-pilot`

## Exit gate

Phase 1 passes only when one documented environment contract starts the local stack, the real startup safety contract passes, all automated commands run to completion, and the manual real-machine checklist has evidence.

Current result: **passed**. One repository-external environment contract starts the local stack, the real startup safety contract passes, all test commands execute to completion, and the actual local browser flows have runtime evidence.

## Emotion runtime incident

### Failure

`start_r1_omni.sh` started the R1-Omni process successfully, but the Admin emotion test capability reported disabled. The persisted `settings.json` value for `EMOTION_LLAMA_ENABLED` overrode the launcher's selected runtime provider.

### Fix

- Treat an explicit valid `EMOTION_LLAMA_ENABLED` process value as runtime profile state.
- Export `EMOTION_LLAMA_ENABLED=true` from both R1-Omni launchers.
- Keep persisted settings as fallback when the process value is absent or invalid.
- Cover the precedence rule and both launchers with regression tests.

### Runtime evidence

- Running UI process: `EMOTION_PROVIDER=r1_omni`
- Running UI process: `EMOTION_LLAMA_ENABLED=true`
- R1 health: `status=ok`, `model_loaded=true`
- Admin capability seam: `enabled=true`, provider `r1_omni`, `status=ready`, `model_loaded=true`
- UI liveness: `status=live`
- UI readiness: `ready=true`

The `/ready` response field `degraded_optional_dependencies=[llm, emotion, rag]` is currently a static declaration of non-required AI dependencies. It is not an observed failure list and is not the Admin test-page capability result.

Authenticated browser verification succeeded with the durable Admin identity. The Admin test page displayed `R1-Omni 已就緒`; a real two-second fake-camera capture completed paired analysis and rendered two result cards from the running R1-Omni service.

## Secure local-pilot identity

Trusted bootstrap now provisions the existing single-store scope without changing its IDs, creates one durable Admin with complete RBAC, issues one store-scoped device credential, and writes secrets only to repository-external private files:

- `/home/oliver/.config/project-2026/local-pilot.env` (`0600`)
- `/home/oliver/.config/project-2026/secrets/admin-login.json` (`0600`)
- `/home/oliver/.config/project-2026/secrets/device-1-provisioning.json` (`0600`)

No raw password, device credential, session token, database URL, or signing secret is printed or committed. The bootstrap is idempotent: it synchronizes Admin RBAC, retains an existing private credential bundle, and will not overwrite secret bundles.

The Kiosk now stays locked until `/api/device/auth/session` confirms a database-owned identity. First-time setup accepts `key_id` and `credential` once, exchanges them for an HttpOnly SameSite session cookie, clears the credential input, and does not place the credential in browser storage. A fresh Chromium context verified the locked state, exchange, scope, cleared input, and authenticated WebSocket.

## Persistence evidence

The running service reports:

- backend: PostgreSQL
- topology: single local host
- endpoint: `127.0.0.1:55432/project_2026`
- PostgreSQL server major: 18
- connection: primary and healthy
- adapter coverage: 19 of 19, complete
- migration head: `0021_rag_readiness_confirmation`
- pending migrations: none
- commercial scope: healthy
- shared infrastructure: skipped because it is not configured for single-host local use

No SQLite/PostgreSQL conflict is present in this running profile. SQLite remains an isolated profile/test implementation; PostgreSQL is the effective commercial runtime backend.

## Automated evidence

| Check | Result | Phase 1 interpretation |
|---|---:|---|
| Provisioning/profile/security focused backend suite | 44 passed | Runtime profile, private files, device identity, and safety contract pass |
| Full backend suite | 494 passed, 11 failed | Command completed; the same known permission/auth/emotion-text contracts are classified downstream |
| Frontend unit suite | 64 passed | Includes three Kiosk device provisioning tests |
| Frontend syntax and production build | passed | Completed |
| Frontend typecheck | failed | Existing RAG Admin, voice-turn protocol, and shared API typing debt; assigned to Phase 3 and Phase 5 |
| Playwright E2E | 3 passed, 10 failed | Runner completes all 13 tests; failures expose downstream Admin auth, ordering-entry/pickup, and voice behavior |
| Actual Kiosk provisioning browser smoke | passed | Locked before provisioning, authenticated afterward, scope matched, WebSocket open |
| Actual Admin emotion browser smoke | passed | Durable manager session, provider ready, paired two-second analysis completed |

The Playwright server no longer uses the rejected legacy `MEMBER_STORAGE_BACKEND=json` selector. It starts an isolated SQLite test profile so runner failures represent product behavior instead of bootstrap failure.

## Pilot safety contract

The validator and application startup now execute the same safety contract. `local-pilot` correctly fixes its identity to:

- `APP_ENV=pilot`
- `DATABASE_BACKEND=postgresql`
- `DATABASE_TOPOLOGY=single`
- `SECURITY_ENFORCED=true`
- demo, test, and debug modes disabled

The contract now passes with:

- development-only manager authentication disabled;
- legacy Admin and Kiosk tokens disabled;
- durable Admin and device sessions enabled;
- private member-reference and object-signing secrets configured;
- tenant, store, and device scope IDs configured;
- ngrok disabled and enforced fail-closed for the local HTTP Pilot;
- demo, test, debug, and unsafe routes disabled.

Redis/shared infrastructure remains an optional warning for the current single-host topology.

## Downstream work exposed by Phase 1

These failures do not invalidate the reproducible runtime baseline, but they remain release blockers in their owning phases:

1. Align the Admin permission catalog and v1/member test authentication contracts, including `rag.review` and session statistics.
2. Complete RAG Admin and shared API TypeScript contracts.
3. Resolve ordering-entry policy behavior and pickup-number projection in Kiosk E2E.
4. Restore voice response/draft degradation behavior.
5. Align the text-emotion prompt language contract.

Phase 2 must start from this passing Pilot runtime rather than reintroducing development principals or legacy tokens.
