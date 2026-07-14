# Local Runtime Inventory (Milestone L0)

- Status: Active inventory
- Base HEAD: `55fce0b`
- Docker required for local run: **No**

## Current process map

| Process | Entry | Required for core checkout |
| --- | --- | --- |
| API | `UI_API/main.py` | Yes |
| Worker | `UI_API/backend/scripts/run_worker.py` | Yes for outbox/async jobs |
| PostgreSQL | host install / local service | Yes for commercial profiles |
| Redis | host install (optional) | No (degrade/optional) |
| Ollama / local LLM | external process | No |
| Emotion-LLaMA | `scripts/start_emotion_llama.sh` | No |
| R1-Omni | `scripts/start_r1_omni.sh` | No |
| Kiosk / Admin | FastAPI static + Vite toolchain | Yes (served by API) |
| Local object storage | directory under learning_data / future `runtime/object_storage` | Yes for content refs |

## Existing ops scripts

| Script | Role |
| --- | --- |
| `scripts/pre_deploy_check.sh` | Pre-deploy validation |
| `scripts/post_deploy_smoke.sh` | Smoke after deploy |
| `scripts/backup_postgres.sh` / `restore_postgres.sh` | DB backup/restore |
| `scripts/record_restore_drill.sh` | Restore drill record (dry-run capable) |
| `scripts/start_emotion_llama.sh` / `start_r1_omni.sh` | Optional model servers |

## Missing local orchestration (L2)

- `scripts/local/setup.sh|ps1`
- `scripts/local/start.sh|ps1`
- `scripts/local/stop.sh|ps1`
- `scripts/local/status.sh|ps1`
- `scripts/local/doctor.sh|ps1`
- `scripts/local/test_fast.sh|ps1`
- `scripts/local/test_full.sh|ps1`
- Managed `runtime/{pids,logs,object_storage,tmp,state}`

## Docker / container artifacts (L1 candidates)

| Path | Current role | Local-first action |
| --- | --- | --- |
| `deploy/Dockerfile.api` | Image build contract | Archive or delete in L1 (not primary) |
| `deploy/Dockerfile.worker` | Image build contract | Archive or delete in L1 |
| `deploy/compose.staging.yml` | Staging-like composition | Archive or delete in L1 |
| `deploy/env-templates/*` | Env templates | Keep non-Docker values; reframe as local profiles in L3 |
| `docs/operations/STAGING_STACK.md` | Staging compose docs | Reframe to native local in L1 |
| GitHub Actions service containers | Remote CI Postgres/Redis | Keep remote-only; never require local Docker |

## Local profiles (planned L3)

| Profile | Storage | Worker | Redis | AI |
| --- | --- | --- | --- | --- |
| `local-dev` | JSON | in-process / light | optional | optional |
| `local-postgres` | PostgreSQL | real worker | optional | optional |
| `local-full` | PostgreSQL | real worker | required | optional services expected |

## Baseline measurement (L0)

| Metric | Value |
| --- | --- |
| Backend tests collected | 351 |
| Inventory backend functions | 352 |
| Backend test files | 72 |
| Frontend unit test files | 4 |
| Collect-only duration | ~0.75s |
| Smoke subset (27 tests) | ~2.55s PASS |

## Decision

Native local/LAN processes are the primary runtime. Docker is not part of the local developer loop.
