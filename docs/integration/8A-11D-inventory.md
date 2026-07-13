# Milestones 8A–11D Inventory — Real Environment, Compatibility, External Pilot

## 8A Production-like Staging Stack

| Item | Status |
| --- | --- |
| `deploy/compose.staging.yml` | Present (API/Worker/Postgres/Redis topology) |
| Env templates | `deploy/env-templates/*` |
| Docker image build in this environment | **NOT RUN** (Docker unavailable) |
| Classification | Contract complete; full stack boot **EXTERNAL/OPS exercise** |

## 8B Actual Backup / Restore Drill

| Item | Status |
| --- | --- |
| Dry-run record script | `scripts/record_restore_drill.sh` |
| Isolated restore against real backup | **EXTERNAL_BLOCKED** — requires operator TARGET_DATABASE_URL + backup artifact |
| Classification | Dry-run only must not be claimed as actual restore PASS |

## 8C Failure Injection and Recovery

| Item | Status |
| --- | --- |
| Unit failure contracts | `tests/test_failure_injection_recovery.py` |
| Worker unknown handler fail-closed | PASS |
| Outbox ACK before published | PASS |
| Analytics idempotent duplicate | PASS |
| LLM timeout budget | PASS |
| Full chaos on staging multi-node | OPS exercise beyond this environment |

## 8D External Telemetry / Measured SLO

| Item | Status |
| --- | --- |
| Metrics contract | Present (observability_service) |
| Exporter / dashboard / paging | **EXTERNAL_BLOCKED** |
| Measured SLO report | **EXTERNAL_BLOCKED** (targets only in PILOT_SLO.md) |

## 9A–9E Compatibility Contract

| Milestone | Internal action | Not done (requires production evidence / external) |
| --- | --- | --- |
| 9A Member phone compatibility | Documented freeze; dual/uuid modes remain flags | Contract remove of phone column |
| 9B Legacy admin/device token | Production fail-fast can disable flags | Full removal of flag code |
| 9C WebSocket query token | Inventory only | Full removal |
| 9D JSON production path | Commercial runtime requires postgres | Dev JSON remains |
| 9E Legacy API write | v1 write exists; allowlist freezes expansion | Full deletion of legacy writes |

## 10A–10D External Provider Pilot

All require real merchant/cloud/POS credentials or pilot authority:

- 10A Payment sandbox certification — **EXTERNAL_BLOCKED**
- 10B Cloud object storage / KMS — **EXTERNAL_BLOCKED**
- 10C POS adapter pilot — **EXTERNAL_BLOCKED**
- 10D Controlled pilot readiness sign-off — **EXTERNAL_BLOCKED**

## 11A–11D Post-Pilot

Require pilot runtime evidence:

- 11A Defect burn-down from pilot — **EXTERNAL_BLOCKED**
- 11B Capacity/SLO evidence — **EXTERNAL_BLOCKED**
- 11C HA decision revisit — deferred ADR-0010 until pilot evidence
- 11D Production launch decision — **EXTERNAL_BLOCKED**

## Truthfulness

Internal Production Integration program is complete for repository-owned work.
Repository is **not** declared Production Certified.
