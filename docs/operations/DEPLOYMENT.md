# Deployment Contract — NOT Production Certified

Primary runtime for this repository is **native local / LAN processes**. Completing the checklist does **not** mean the system is Production Certified.

## Process boundaries (native)

| Process | Owns | Runtime | Must not own |
| --- | --- | --- | --- |
| API | HTTP/WebSocket, auth, checkout write path | `python UI_API/main.py` | GPU model weights, long RAG rebuild |
| Worker | `background_jobs`, `order_outbox` delivery | `python UI_API/backend/scripts/run_worker.py` | Interactive HTTP, model weights |
| PostgreSQL | Commercial source of truth | Host / managed service | Ephemeral rate-limit counters |
| Redis | Ephemeral rate limit / cache / lock | Host Redis (optional locally) | Orders, members, identity truth |
| AI Gateways | Ollama / Emotion-LLaMA / R1-Omni | Separate optional processes | Core transaction writes |

GPU models stay outside API/Worker processes. Checkout readiness must not require GPU availability.

## Environment separation

| APP_ENV | Demo routes | Storage | Fail-fast |
| --- | --- | --- | --- |
| development | allowed | JSON or postgres | soft |
| test | CI defaults | JSON | CI-controlled |
| staging | disabled | postgres required | commercial fail-fast |
| pilot | disabled | postgres required | commercial fail-fast |
| production | disabled | postgres required | commercial fail-fast |

Local developer profiles (Milestone L3): `local-dev`, `local-postgres`, `local-full`.

Historical env examples (archived, not active runtime): `docs/archive/docker/env-templates/*`.

## Resource baseline (hints)

- API CPU/memory, worker CPU/memory
- PostgreSQL pool size
- HTTP and AI gateway timeouts
- Disk for logs/backups

## Release flow (native)

### pre-deploy

```bash
export DATABASE_URL=...
export APP_ENV=staging   # or pilot/production
bash scripts/pre_deploy_check.sh
```

Includes: backup, migration status/validate --require-clean, commercial scope integrity, startup config fail-fast.

### deploy

1. Apply pending migrations (`manage_postgres_migrations.py apply`) when the release includes schema.
2. Restart API process.
3. Restart Worker process.
4. Keep AI gateways on independent lifecycle.

### post-deploy

```bash
export BASE_URL=http://127.0.0.1:8000
bash scripts/post_deploy_smoke.sh
```

Requires `/live` and `/ready`. Optionally inspect metrics. Reconcile outbox backlog and worker depth after cutover.

## Rollback

Application rollback restarts previous API/Worker SHA. Schema remains forward-only.

| Layer | Policy |
| --- | --- |
| Application | Redeploy previous API/Worker SHA |
| Schema | Forward-only; never edit applied migration checksums |
| Feature flags | Prefer compatibility windows (legacy tokens, identity read mode) |
| Data | Isolated restore + roll-forward; see [RESTORE_DRILL_TEMPLATE.md](RESTORE_DRILL_TEMPLATE.md) |

Do not force-push shared history. Do not drop commercial tables to "undo" a release.

## Local stack (no Docker required)

```bash
# PostgreSQL + Redis as host services (optional Redis)
cp .env.example .env
cd UI_API
python -m pip install -r requirements.txt
python backend/scripts/manage_postgres_migrations.py apply   # when using postgres
python main.py &
python backend/scripts/run_worker.py &
```

See [LOCAL_DEPLOYMENT.md](../LOCAL_DEPLOYMENT.md) and L2 `scripts/local/*` orchestration.

Docker artifacts are archived under `docs/archive/docker/` for historical reference only.

## Security boundaries

- No production default secrets.
- Demo / test / debug routes off in staging/pilot/production.
- `ALLOW_POSTGRES_JSON_FALLBACK=false` for commercial runtimes.
- Secret injection only via environment/Secret Manager; never commit `.env` values.
