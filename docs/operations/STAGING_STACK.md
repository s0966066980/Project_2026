# Staging / Local-full Stack Contract (Native)

Primary topology is **host processes**, not containers.

Required for commercial-like local:

1. PostgreSQL 16+ (host service)
2. Redis (optional for local-postgres; recommended for local-full)
3. API process (`python UI_API/main.py`)
4. Worker process (`python UI_API/backend/scripts/run_worker.py`)
5. Optional AI gateways (Ollama / Emotion-LLaMA / R1-Omni) on separate processes

Pre-boot:

```bash
export DATABASE_URL=...
export REDIS_URL=...   # optional
export OBJECT_STORAGE_SIGNING_SECRET=...
export ADMIN_MEMBER_REF_SECRET=...
cd UI_API
python backend/scripts/manage_postgres_migrations.py apply
python backend/scripts/manage_postgres_migrations.py validate --require-clean
```

Post-boot:

```bash
bash scripts/post_deploy_smoke.sh
```

Docker is **not** required. Archived compose/Dockerfiles: `docs/archive/docker/`.
