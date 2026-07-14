# Local Runtime Profiles

Priority: **Environment variables → Profile defaults → Safe defaults**.

| Profile | Storage | Redis | Security | Demo routes | Use when |
| --- | --- | --- | --- | --- | --- |
| `local-dev` | JSON | optional | soft | allowed | Daily UI/API coding |
| `local-postgres` | PostgreSQL | optional | soft | allowed | Commercial data path |
| `local-full` | PostgreSQL | required | enforced | disabled | Pre-pilot local stack |
| `test` | JSON | optional | soft | CI-like | pytest |
| `ci` | JSON | optional | soft | off demos as CI sets | GitHub Actions |

## Validate

```bash
cd UI_API
python backend/scripts/validate_local_environment.py --list
python backend/scripts/validate_local_environment.py --profile local-dev
MEMBER_STORAGE_BACKEND=postgres DATABASE_URL=postgresql://... \
  python backend/scripts/validate_local_environment.py --profile local-postgres
```

Output is PASS/WARN/FAIL only — secret values are never printed.

## Apply with start

```bash
export APP_ENV=development
export MEMBER_STORAGE_BACKEND=json
bash scripts/local/start.sh

export MEMBER_STORAGE_BACKEND=postgres
export DATABASE_URL=postgresql://user@localhost/project2026
bash scripts/local/start.sh
```
