# P2 Local Pilot Readiness

## Status

`BLOCKED` — not declared, and not currently pursuable.

Two independent inputs are missing, and neither can be substituted from this repository:

1. **Pilot Configuration Authority.** On 2026-08-11 the project owner directed that all pilot login credentials be removed and that no login authentication be created for now. Every file under `~/.config/project-2026/` was deleted at their instruction. Local Pilot Readiness is defined by one host-external, privately permissioned configuration and secret source; without it the gate cannot be entered, let alone passed.
2. **Target Kiosk device.** Microphone, camera, browser permissions, AudioWorklet, bundled Silero VAD v5 timing, physical ordering and Live AV Emotion evidence.

The project owner has decided to **pause Local Pilot Admission and proceed to the P3–P7 architecture convergence work instead**. This deliberately crosses the fixed stage order in [the execution plan](../../Project_2026_Execution_Plan.md), which places every later stage behind this gate. It is recorded here as an explicit decision, not as a passed gate. Local Pilot Readiness remains **NOT DECLARED**.

Issues: [#19](https://github.com/s0966066980/Project_2026/issues/19), [#20](https://github.com/s0966066980/Project_2026/issues/20), [#23](https://github.com/s0966066980/Project_2026/issues/23).

## The superseded record

The evidence previously recorded here, for commit `f5967a6`, is **`EVIDENCE_STALE`**. PR [#46](https://github.com/s0966066980/Project_2026/pull/46) changed the Pilot runtime contract and the images, which invalidates it by the rule that record itself stated.

Two facts about that superseded record are worth keeping, because both made it weaker than it read:

- **It authenticated with the compose default credential.** The database role password was the literal `project-2026-local` from `docker/compose.yaml`, not the value in the repository `.env`; the stack had been started without `--env-file .env`. Any invocation that did pass `--env-file .env` failed authentication. `.env` has since been aligned to the database (backup: `.env.bak.20260811230306`).
- **Its Playwright evidence ran without device admission.** Those five tests passed against `SECURITY_ENFORCED=false`. Under the Pilot profile the same suite cannot reach the menu at all — see below.

## Candidate artifact verified on 2026-08-11

A hardened Pilot candidate was built and exercised before the credentials were removed. This is a **repository-and-host** record for that candidate. It is not a readiness declaration and no target-device claim is made anywhere in it.

| Item | Evidence |
| --- | --- |
| commit | `2d9ff9899799bce765f0a1db368eb6b4ad10598d` |
| source integrity | `config.py`, `main.py` and `tests/test_pilot_container_security.py` md5-identical between image and working tree |
| app and worker image | `project-2026:ai`, `sha256:8d9d7b625c01714905f416bda212847fca14abdf313a121ba0fdd84c7637cdb0` |
| core runtime image | `project-2026:local`, `sha256:728adc6ec564c66f780b4a2e219ac5e19188f33bdbcdec1b009025ed48410e33` |
| R1-Omni image | `project-2026-r1-omni:gpu`, `sha256:e80c34e712b4965ce6ff8930ef050d7cfa22f31887ef37f062932ebc05fa380d` |
| PostgreSQL image | `postgres@sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296` |
| Ollama image | `ollama/ollama@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131` |
| merged compose fingerprint | `b66bd2e3aa6fa8922eba4463803ff0ca01571519f2da57b638ac96b68192f17b` |
| external config fingerprint | `6a8918d38ffcb2a37c0513e7fecebdeb6fdc6cd00bd7efd7c12369715a3bca4c` (source since deleted) |
| migration head | `0027_remove_pre_pilot_rag_history`, 27 applied, 0 pending |
| runtime | single local host, Docker Compose with the AI and GPU overlays plus `compose.pilot.yaml` |

### Container security — 22 of 22 passed

`docker/scripts/verify-pilot-security.sh` against the running candidate, for both app and worker:

- `ReadonlyRootfs=true`, `CapDrop=[ALL]`, `CapAdd=[]`, `no-new-privileges:true`, `User=10001:10001`.
- Kernel-level: `CapPrm`, `CapEff` and `CapBnd` all `0000000000000000`; `NoNewPrivs: 1`.
- Every root filesystem write rejected with `EROFS(30)`: `/app/UI_API`, `/`, `/usr/local`, `/etc`, `/home/project2026`, `/var/lib`.
- Allowlisted paths writable: `/tmp`, `/var/lib/project-2026`, `/tmp/project-2026-media`, `/home/project2026/.cache`.
- Secrets mode `0600`, uid `10001`, readable; database password absent from the environment and from container logs.
- `/api/v1/diagnostics/ollama-models`, `/api/demo`, `/api/debug` → 404. `/ready` → 200.
  （記錄當時該診斷路徑為 `/api/ollama/models`；未版本化的相容面已於 2026-08-12 全面撤除，見 [ADR-0062](../adr/0062-serve-one-versioned-http-prefix.md)，該路徑在任何 profile 下都已是 404。）

The structural half is a required check: `UI_API/tests/test_pilot_container_security.py`, 27 tests, mutation-verified.

### Fail-fast configuration

- Omitting any of `PILOT_ENV_FILE`, `PILOT_DATABASE_URL_FILE`, `PILOT_MIGRATION_DATABASE_URL_FILE` fails at `docker compose config`, before anything starts.
- A configuration or secret file looser than `0600`, or not owned by uid 10001, fails closed.

### Backup, restore and migration reconciliation

- PostgreSQL custom-format dump (1,523,010 bytes) restored into an explicitly named temporary database.
- Reconciled: 27 migration rows and 74 public tables in both; `md5(string_agg(version||':'||checksum))` identical at `cce1174aa91d4abbb4af0a36523ebeb6`.
- The temporary database and the exact dump path were removed afterwards; `pg_database` count for the temporary name returned 0.
- Migration reapply is idempotent: still 27 rows, head unchanged, no errors.

### Restart, warm-up and degradation

- App stopped: `/ready` unreachable (`HTTP 000`) — the measurement has a real zero point.
- App started: Core `/ready` returned 200 **2611 ms** after container start, while `stt` and `rag` were still `pending` and listed in `warming_capabilities`. Optional warm-up does not gate Core HTTP, as [ADR-0060](../adr/0060-warm-capabilities-beside-the-service-not-in-front-of-it.md) requires.
- Security attributes still enforced after restart; worker returned to `healthy`.
- Shared infrastructure absent reports `skipped` with reason `shared_infrastructure_not_configured` without making the service unready.
- After warm-up: `stt`, `rag` and `voice_llm` all `ready`, no degraded optional dependency, adapter coverage 19/19 complete.
- Edge TTS synthesised 15,840 bytes for a Traditional Chinese probe.

### Test suites

| Suite | Result |
| --- | --- |
| `docker/scripts/test.sh` | 158 passed; Docker smoke test passed; RC=0 |
| Frontend typecheck / syntax / build | passed |
| Frontend coverage | statements 92.97%, branches 80.36%, functions 94.73%, lines 93.1% |
| Playwright against the Pilot profile | **1 passed, 4 failed** — see below |
| Playwright against the development profile | 5 passed |

`docker/scripts/test.sh` needs `APP_PORT` overridden while a stack already holds `127.0.0.1:8000`; the smoke project has its own compose project name and volumes, only the published host port collides.

### Playwright under the Pilot profile

Four of five tests fail at `#startSystemBtn`, blocked by the `kioskDeviceAuthBackdrop` modal. **This is correct fail-closed behaviour, not a defect**: `SECURITY_ENFORCED=true` requires the Kiosk to present a device credential, and the suite has none.

The consequence is that browser evidence under the Pilot profile depends on device credential provisioning, which belongs to target-device admission ([#20](https://github.com/s0966066980/Project_2026/issues/20), [#23](https://github.com/s0966066980/Project_2026/issues/23)). It was not substituted with development-profile evidence, and the development-profile run above is recorded as what it is.

## Still not admissible

Unchanged from the superseded record, and now joined by the missing configuration authority:

1. Target Kiosk device admission: microphone, camera, browser permissions, AudioWorklet, bundled Silero VAD v5, 250 ms minimum speech, 1.2 s ending silence, 30 s cap, echo cooldown, noisy-store acceptance.
2. Physical touch ordering, voice ordering, checkout outcome-unknown recovery and Payment Pending handoff on the target Kiosk.
3. Live Admin AV Test and voice-aligned audiovisual Emotion evidence on the target camera and microphone. Host `/dev/video*`, `/dev/snd` and an available NVIDIA GPU are not evidence for the target device.
4. Kiosk device credential provisioning, revocation and store scope.
5. Pilot Recovery Objective observed against a backup copy separated from the primary runtime.

## Open observations

- [#47](https://github.com/s0966066980/Project_2026/issues/47): the interactive OpenAPI explorer at `/docs` answers 200 under the Pilot profile. Loopback-bound, but it is an unauthenticated enumeration of every operation and needs a decision rather than a default.
- [#48](https://github.com/s0966066980/Project_2026/issues/48): `docker/Dockerfile` copies the application into `base` before the AI stage installs its dependencies, so any source change forces a full AI dependency reinstall. The candidate rebuild recorded here cost over an hour for that reason.
- The application still connects as the owning database role. `project_runtime` is provisioned and granted but unused; moving the runtime connection onto it belongs to Operations & Configuration (P5.1).
- The database role password is the compose default. A pilot-grade credential is a human decision and was not rotated here.

## Safety notes

- No PostgreSQL volume, backup, customer record or authoritative business data was deleted at any point.
- The temporary restore database and dump had exact names and were removed after verification.
- Credential removal was limited to eleven explicitly enumerated files and one directory under `~/.config/project-2026/`, at the project owner's direction, with the enumeration printed before deletion.
