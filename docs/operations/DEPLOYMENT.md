# Deployment Contract — NOT Production Certified

This document defines Development / Staging / Pilot / Production process boundaries for Project_2026. Completing the checklist does **not** mean the system is Production Certified.

## Process and image boundaries

| Process | Owns | Image / runtime | Must not own |
| --- | --- | --- | --- |
| API | HTTP/WebSocket, auth, checkout write path | `deploy/Dockerfile.api` | GPU model weights, long RAG rebuild |
| Worker | `background_jobs`, `order_outbox` delivery | `deploy/Dockerfile.worker` | Interactive HTTP, model weights |
| PostgreSQL | Commercial source of truth | Managed/service image | Ephemeral rate-limit counters |
| Redis | Ephemeral rate limit / cache / lock | Redis 8 service | Orders, members, identity truth |
| AI Gateways | Ollama / Emotion-LLaMA / R1-Omni | Separate GPU-capable runtimes | Core transaction writes |

GPU models stay outside API/Worker images. Checkout readiness must not require GPU availability.

## Environment separation

| APP_ENV | Demo routes | Storage | Fail-fast |
| --- | --- | --- | --- |
| development | allowed | JSON or postgres | soft |
| test | CI defaults | JSON | CI-controlled |
| staging | disabled | postgres required | commercial fail-fast |
| pilot | disabled | postgres required | commercial fail-fast |
| production | disabled | postgres required | commercial fail-fast |

Templates: `deploy/env-templates/staging.example`, `pilot.example`, `production.example`. Secrets are injected by the deployment platform; repository templates use `CHANGE_ME` markers only.

## Resource baseline (hints)

Orchestrators should map:

- API CPU/memory, worker CPU/memory
- PostgreSQL pool size
- HTTP and AI gateway timeouts
- Disk for logs/backups

Exact numbers live in env templates as `API_CPU_LIMIT`, `WORKER_MEMORY_LIMIT_MB`, `POSTGRES_POOL_SIZE`, `HTTP_TIMEOUT_SECONDS`, `AI_GATEWAY_TIMEOUT_SECONDS`.

## Release flow

### pre-deploy

```bash
export DATABASE_URL=...
export APP_ENV=staging   # or pilot/production
bash scripts/pre_deploy_check.sh
```

Includes: backup, migration status/validate --require-clean, commercial scope integrity, startup config fail-fast.

### deploy

1. Apply pending migrations (`manage_postgres_migrations.py apply`) when the release includes schema.
2. Roll out API image/process.
3. Roll out Worker image/process.
4. Keep AI gateways on independent lifecycle.

### post-deploy

```bash
export BASE_URL=http://127.0.0.1:8000
bash scripts/post_deploy_smoke.sh
```

Requires `/live` and `/ready`. Optionally inspect metrics. Reconcile outbox backlog and worker depth after cutover.

## Rollback

Application rollback redeploys the previous API/Worker image/SHA. Schema remains forward-only.

| Layer | Policy |
| --- | --- |
| Application | Redeploy previous API/Worker image/SHA |
| Schema | Forward-only; never edit applied migration checksums |
| Feature flags | Prefer compatibility windows (legacy tokens, identity read mode) |
| Data | Isolated restore + roll-forward; see [RESTORE_DRILL_TEMPLATE.md](RESTORE_DRILL_TEMPLATE.md) |

Do not force-push shared history. Do not drop commercial tables to "undo" a release.

## Staging-like composition

```bash
export POSTGRES_PASSWORD=...
docker compose -f deploy/compose.staging.yml up --build
```

This stack intentionally omits Emotion-LLaMA and R1-Omni.

## Security boundaries

- No production default secrets.
- Demo / test / debug routes off in staging/pilot/production.
- `ALLOW_POSTGRES_JSON_FALLBACK=false` for commercial runtimes.
- Secret injection only via environment/Secret Manager; never commit `.env` values.
