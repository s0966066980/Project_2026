# Staging Stack Contract

Topology source: `deploy/compose.staging.yml`.

Required processes:

1. PostgreSQL 16 (commercial SoT)
2. Redis 8 (ephemeral shared infra)
3. API container (`deploy/Dockerfile.api`)
4. Worker container (`deploy/Dockerfile.worker`)
5. Optional AI gateways on separate hosts/images (not in API image)

Pre-boot:

```bash
export DATABASE_URL=...
export REDIS_URL=...
export OBJECT_STORAGE_SIGNING_SECRET=...
export ADMIN_MEMBER_REF_SECRET=...
# commercial fail-fast fields from deploy/env-templates/staging.example
python UI_API/backend/scripts/manage_postgres_migrations.py apply
python UI_API/backend/scripts/manage_postgres_migrations.py validate --require-clean
```

Post-boot:

```bash
bash scripts/post_deploy_smoke.sh
```

This environment does not run Docker; staging image build remains an operator exercise.
