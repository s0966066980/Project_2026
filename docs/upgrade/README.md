# Commercial V1 Upgrade

The road from the current Transitional Modular Monolith to a Commercial V1
single-store Local-First Kiosk product, and the evidence produced along the way.

## Which document answers what

Two documents govern this work and they are not interchangeable.

| Question | Document |
| --- | --- |
| What is the strict completion state right now, and where is the evidence? | [`Project_2026_Execution_Plan.md`](../../Project_2026_Execution_Plan.md) |
| What remains to become Commercial V1, in what order, behind which gates? | [`commercial-v1-plan.md`](commercial-v1-plan.md) |

The execution plan remains the authority on **status**. This directory is the
authority on **route**. Where they disagree about what has been achieved, the
execution plan wins and the roadmap gets corrected — a second document that
quietly disagrees about state is worse than no second document.

Domain vocabulary stays in [`CONTEXT.md`](../../CONTEXT.md); decisions stay in
[`docs/adr/`](../adr/). Neither is superseded here.

## Layout

```text
docs/upgrade/
├── README.md              this file
├── commercial-v1-plan.md  the 45-item roadmap, 20 phases
├── baseline.md            the frozen starting point and its measurements
├── gates/                 per-item gate evidence
├── architecture/          structure decisions taken during the upgrade
├── test-results/          captured runs referenced by gate evidence
├── deployment/            release, installer and appliance evidence
├── recovery/              backup and restore drill evidence
└── hardware/              target-device evidence (blocked; see below)
```

## Two recorded exceptions to the roadmap

**Branch strategy.** Item 0.1 asks for an `upgrade/commercial-v1` branch and
forbids large refactors on `main`. The project owner directed on 2026-08-12
that work stays on a single independent `main`. This is a recorded decision,
not an oversight: the repository has one developer, CI runs on every push, and
a long-lived branch would buy divergence rather than protection. Every other
part of item 0.1 — clean tree, recorded baseline SHA — still applies, and is
recorded in `baseline.md`.

**Items already delivered before the roadmap was written.** The roadmap is
dated 2026-08-12 and lists as outstanding several things that landed earlier
that same day. Executing it literally would start by redoing finished work.
The current mapping is in the next section and is the authority on where to
start.

## Where the 45 items actually stand

Measured 2026-08-12 against `main`. Status here means repository evidence only;
it never promotes a Pilot gate.

### Delivered

| Item | Evidence |
| --- | --- |
| 02 Architecture dependency rules | `tests/test_architecture_boundaries.py`; three rules that had been matching nothing now match, and the eight real violations are a frozen shrink-only inventory |
| 04 Catalog | The one capability past the Module Independence Gate |
| 12 Operations (health half) | `/live` and `/ready` separated, `/ready` checks database, migration, scope and shared infrastructure; AI reports degraded without failing readiness (ADR-0060) |
| 13 Remove backend legacy (HTTP half) | Unversioned `/api/*` withdrawn, 67 to 0 (ADR-0062) |
| 14 PostgreSQL hardening | Fails closed on misconfiguration; 20/20 adapter coverage |
| 16 Outbox / worker reliability | Job state machine, bounded retry, dead letter, idempotency |
| 19 Shared / API client cleanup | Empty legacy allowlist; every browser call goes through `capabilityClients.js` |
| 24 Security | Container contract with 27 structural tests and 22/22 runtime checks (ADR-0061); rate limiting and upload bounds in place |
| 25 Observability (logging half) | Structured request logging with correlation, tenant, store and device fields |
| 36 Admin AI proposal workflow | Sidecar isolation, proposals never applied automatically (ADR-0034, ADR-0039, ADR-0040) |

### Delivered in the first upgrade batch

Evidence for each, including the mutations that prove the new rules can fail,
is in [`gates/README.md`](gates/README.md).

| Item | What changed |
| --- | --- |
| 01 Test infrastructure | Layer markers applied to every test file; selection verified; `tests/test_test_taxonomy.py` keeps them from rotting back into decoration |
| 1.3 Unversioned surface rule | Three rules over the mounted routes, mutation-verified |
| 1.3 Contract snapshot | 119 operations and 77 models captured, mutation-verified against rename, new obligation and route deletion |
| 9.2 Build metadata endpoint | `GET /api/v1/operations/build`; `config.APP_VERSION` is the single source shared with the OpenAPI version |
| 23 Model registry | `config/models/manifest.yaml` plus `validate_model_manifest.py`, verified against the host weights and the Ollama digest |
| 15 Migration hardening | CI rehearses the upgrade from the previous release before applying the newest migration |

### Still missing, and buildable here

| Item | Gap |
| --- | --- |
| 26/27 Backup and restore drill | One manual dump/restore is recorded; there is no repeatable script |
| 37/38 Performance and concurrency | No load or concurrency tests |

### Missing, and dependent on the above

28–33: release engineering, immutable images, installer, systemd, update,
rollback. None started.

### Blocked on inputs this repository cannot produce

40–45: fresh hardware install, 8h and 24h burn-in, Commercial Pilot Gate,
controlled store pilot, V1 release. These need the target Kiosk device and the
Pilot Configuration Authority, both already tracked as `ready-for-human` in the
execution plan. Item 18.1 of the roadmap forbids using a development machine as
evidence, so the workstation this was measured on cannot stand in.

### Partially delivered

The eight capability interfaces still reading `services`/`repositories`
(items 03, 05–11), frontend decomposition (17, 18), E2E breadth (20), AI
provider ports and the degradation matrix (21, 22), Payment/POS ports beyond
the manual adapter (34, 35), and failure injection breadth (39). Their exact
gaps are not re-catalogued here; the capability half is precisely described by
`CAPABILITIES_STILL_ON_LEGACY_LAYERS` in the architecture boundary test.
