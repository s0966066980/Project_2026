# Local Native Deployment (Primary)

Project_2026 的**主要執行方式**是本機或區域網路的原生 Process，**不需要 Docker**。

## Processes

| Process | How to run | Notes |
| --- | --- | --- |
| API | `cd UI_API && python main.py` | Serves Kiosk/Admin + HTTP/WebSocket |
| Worker | `cd UI_API && python backend/scripts/run_worker.py` | Jobs + outbox (PostgreSQL mode) |
| PostgreSQL | Host service (apt/brew/system) | Required for commercial local profiles |
| Redis | Host service optional | Shared rate limit / presence |
| Ollama | Host install optional | LLM; does not block checkout |
| Emotion-LLaMA | `bash scripts/start_emotion_llama.sh` | Optional |
| R1-Omni | `bash scripts/start_r1_omni.sh` | Optional |

Orchestration scripts under `scripts/local/` are added in Milestone L2.

## Config

1. `cp .env.example .env`
2. Never commit real secrets.
3. Commercial local: `MEMBER_STORAGE_BACKEND=postgres` + `DATABASE_URL`.
4. JSON dev: `MEMBER_STORAGE_BACKEND=json`.

See also: [LOCAL_RUNTIME_INVENTORY.md](LOCAL_RUNTIME_INVENTORY.md), [operations/DEPLOYMENT.md](operations/DEPLOYMENT.md).

## Docker

Docker files (if retained) live under **`docs/archive/docker/`** as historical reference only. They are **not** the active local runtime and are not required for development.
