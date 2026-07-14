# Deploy notes (Local-first)

Primary runtime is **native local/LAN processes**, not Docker.

| Active path | Role |
| --- | --- |
| `UI_API/main.py` | API process |
| `UI_API/backend/scripts/run_worker.py` | Worker process |
| Host PostgreSQL / Redis | Data & ephemeral infra |
| `.env.example` | Environment template |

Archived Docker artifacts (reference only):

- `docs/archive/docker/Dockerfile.api`
- `docs/archive/docker/Dockerfile.worker`
- `docs/archive/docker/compose.staging.yml`
- `docs/archive/docker/env-templates/*`

Do not require Docker for local setup, CI developer loops, or Local-first gates.
