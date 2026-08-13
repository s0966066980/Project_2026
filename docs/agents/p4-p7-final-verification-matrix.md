# P4–P7 最終驗證矩陣

> Snapshot: 2026-08-13, updated after Checkout outbox reliability and the unversioned HTTP surface were
> withdrawn. This is an evidence ledger, not a completion claim.
> Repository-only checks use the current worktree mounted read-only into the
> `project-2026:test` container. A row is **PASSED** only when its evidence
> covers the row's full scope; narrower evidence is marked **PARTIAL**.

## Status vocabulary

- **PASSED** — current evidence covers the complete row scope.
- **PARTIAL** — repository or unit evidence exists, but the row requires a
  broader runtime, artifact, or consumer proof.
- **BLOCKED** — a named external input is unavailable and cannot be replaced by
  repository code or a fake.
- **NOT RUN** — an executable check remains to be run after the exact candidate
  artifact is available.

## Matrix

| # | Verification row | Current evidence | Status | Remaining proof / blocker |
|---:|---|---|---|---|
| 1 | Candidate build and digest capture | Current worktree candidate runtime image `project-2026:p7-final-verify` built successfully; runtime digest `sha256:c171c8d12a75b49d780fc5735e193cdd61507d1636b2b105020f2e366143f4f4`; test digest `sha256:207fa27df9d5f13761297cb5c7cd31b9729ade2ab278afc0f5bf03785fd81345`; Dockerfile layering and docs-copy regression tests pass | PARTIAL | A clean commit/attestation, base-image digest pinning, and the second full AI cache-build evidence still require the release builder/registry. |
| 2 | Fresh, upgrade, reapply migration and checksum reconciliation | Exact candidate image applied a fresh temporary PostgreSQL database twice: both runs `29 applied / 0 pending`, all migration states `applied`, no checksum mismatch; the current smoke run applies migration `0029` for Checkout outbox reliability | PARTIAL | Pilot-owned existing-upgrade/backup reconciliation and production restore authority remain outside this runner. |
| 3 | Python 3.10/3.12, Ruff, format, mypy, all tests | Candidate Python 3.10 suite: 285 app tests + 71 isolated sidecar/proposal tests = 356 passed; the prior Python 3.12 read-only suite passed 355 tests, and the new pure Dockerfile-context regression passed in the candidate test image; candidate Ruff check and format check now pass over the whole tree rather than a hand-listed path set; mypy passes over its full declared scope, 63 files | PARTIAL | Release CI attestation and a fresh Python 3.12 rerun for the new regression remain outside this local runner. |
| 4 | PostgreSQL and Redis integration | Exact candidate PostgreSQL adapter/schema/status/migration-contract run **8 passed**; fresh/reapply 28/0 with matching checksums; exact candidate Redis live integration 9 passed (TTL, rate limit, scope, lock) | PARTIAL | Redis degradation and full domain E2E still require the final deployment topology. |
| 5 | Frontend typecheck, syntax, coverage, build, Playwright | Syntax, typecheck, build, 127 Vitest tests, coverage (93.18% statements / 80.57% branches / 94.91% functions / 93.30% lines), and exact-candidate local Playwright 5/5 passed | PARTIAL | Target-device media/browser acceptance remains unavailable. |
| 6 | Architecture imports, raw fetch, legacy literals, OpenAPI drift | Exact candidate focused static/security suite (architecture, capability independence, Docker layering, generated API, HTTP surface, legacy closure, Pilot security) **54 passed**; the generated catalog contract matches; the candidate publishes 101 `/api/v1` paths and zero unversioned `/api/*` paths; production route legacy-import allowlist and `modules.*`/`repositories.*` zero-use AST gates pass; feature raw-fetch gate pass; the capability boundary rules were repaired after they were found matching nothing, and the eight real violations are now a frozen inventory | PARTIAL | Full semantic OpenAPI/client drift and release-artifact provenance still require the release candidate process. |
| 7 | Device/Admin auth, store scope, permissions | Existing auth, permission, scope, and diagnostic route tests | PARTIAL | Same-artifact PostgreSQL and device-credential issuance/revocation evidence is required. |
| 8 | Member, Guest, Catalog, Campaign, Recommendation flows | Existing catalog, campaign, member, recommendation, and guest repository tests | PARTIAL | Complete Admin/Kiosk consumer E2E and module independence ledgers remain. |
| 9 | Touch and Voice ordering, Checkout Outcome Unknown, Payment Pending | Checkout, voice-turn, playback, and restart tests | PARTIAL | Same-artifact touch+voice E2E and recovery evidence remains. |
| 10 | RAG publication, retrieval, and recovery | RAG retained-flow, visibility, retrieval-configuration, and worker tests | PARTIAL | PostgreSQL/index filesystem checksum, durable restart, and final-candidate recovery evidence remains. |
| 11 | Emotion modes, live AV, and retention | P2 emotion contract/single-pass/observation tests and 30-day repository contracts | PARTIAL | Live AV and target-device media acceptance are unavailable. |
| 12 | Project Analyst isolation, proposals, and provider profiles | Sidecar isolation, allowlist, proposal, and fail-closed profile tests | PARTIAL | Codex/Claude/Grok CLI installations and credentials are explicitly deferred by owner. |
| 13 | Optimization evidence, privacy, reports, and egress | P4 tests, 0028 migration tests, local Ollama `LOCAL_ONLY` probe, strict schema rejection, TTL/audit tests | PARTIAL | Customer-evidence authorization, encrypted-at-rest and provider-egress deployment evidence are explicitly deferred. |
| 14 | Docker read-only, cap-drop, restart, warm-up, degradation | Candidate Docker build succeeded; exact candidate Dockerfile/Pilot security focused tests pass (including 27 security-contract cases); the isolated smoke stack returns healthy app/worker services after applying migration `0029` | PARTIAL | Pilot authority and final shared-infrastructure degradation topology are unavailable. |
| 15 | Backup/restore and Pilot Recovery Objective | Final candidate custom-format PostgreSQL dump/restore completed; restored database passed `status --require-clean` with `28 applied / 0 pending` and matching checksums | PARTIAL | RPO/RTO observation and backup separation still require Pilot runtime authority. |
| 16 | Target Kiosk VAD/noisy-store/STT/LLM/TTS/camera/soak | Repository VAD/reducer/media degradation tests | BLOCKED | Target Kiosk, microphone/camera/browser/AudioWorklet and physical soak are unavailable. |
| 17 | Secret/path/network/provider egress and audit | Static security tests, allowlists, and local-only analyzer policy | PARTIAL | Customer authorization and final deployment/network/mount proof are unavailable. |
| 18 | Raw media absence and all 30-day TTLs | P2 emotion and P4 Optimization Lab retention tests | PARTIAL | Cross-capability final-artifact retention audit remains. |
| 19 | Legacy compatibility surface is zero | Unversioned `/api/*` withdrawn in full: the running stack publishes 101 `/api/v1` paths and 0 unversioned `/api/*`, down from 93 beside 67. Seven non-duplicate paths were given versioned homes first (Optimization Lab, Admin health report and its two incident actions); `admin_identity_routes.py` deleted; `core_routes.py` reduced to page entry points. Withdrawn paths answer 404 on the live stack ([ADR-0062](../adr/0062-serve-one-versioned-http-prefix.md)) | PASSED | None for the transport surface. The horizontal-layer half of legacy closure is tracked separately as row 20 and in the P7 inventory. |
| 20 | Ten Module Independence ledgers and Admin/Kiosk 2/2 | Ten published capability packages, versioned route ownership tests, Identity/Operations/Recommendation transport boundary tests, 101-path candidate catalog, and frontend checks. All ten capability interfaces no longer read `services`/`repositories`; `CAPABILITIES_STILL_ON_LEGACY_LAYERS` is empty and the boundary is enforced with no allowlist | PARTIAL | Full data-authority, PostgreSQL, restart, E2E, consumer-zero, and per-module ledgers are not yet passed. |

## Current executable evidence

```text
Backend read-only candidate suite: 285 app + 71 isolated sidecar/proposal = 356 passed
Python 3.12 read-only suite: 355 passed (pre-regression baseline)
Backend Ruff check and format: passed over the whole tree
mypy over its full declared scope: 63 files passed
P4/Docker/capability focused tests: 18 passed; final static/security focused suite: 54 passed
Candidate PostgreSQL adapter/schema/status/migration-contract: 8 passed; fresh/reapply: 28/0
Candidate PostgreSQL backup/restore: final candidate dump restored; status 28/0 with matching checksums
Candidate Redis shared integration: 9 passed
Exact PostgreSQL-backed runtime restart: `/live` + `/ready` passed before and after restart; 20/20 adapters, migration head 0029
Frontend syntax/typecheck/build: passed
Frontend Vitest: 130 passed; coverage 93.18% statements, 80.57% branches, 94.91% functions, 93.30% lines
Exact-candidate Playwright: 5 passed
Candidate runtime image digest: sha256:c171c8d12a75b49d780fc5735e193cdd61507d1636b2b105020f2e366143f4f4
Candidate test image digest: sha256:207fa27df9d5f13761297cb5c7cd31b9729ade2ab278afc0f5bf03785fd81345
Candidate OpenAPI surface: 101 /api/v1 paths, 0 unversioned /api/* paths
Local Ollama qwen3.5:4b: four allowed metric objects returned under LOCAL_ONLY
Malformed/echo Ollama envelope: rejected; no synthetic/cloud fallback
```

## Non-replaceable blockers

The following are intentionally not implemented or simulated: Codex/Claude/Grok
CLI and credentials, customer-evidence authorization/retention/egress approval,
Pilot Configuration Authority, and target Kiosk hardware. They keep rows 12,
13, 14, 15, 16, 17, and the final Project Completion claim open.
