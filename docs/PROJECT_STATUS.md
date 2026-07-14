# Project Status — Single-Store Local Kiosk Pilot

## 1. Current Version

- Git branch: `main`
- Deployment mode: **方案 A — 單店本地端 Kiosk Pilot**
- Classification target: `LOCAL_PILOT_READY` / `LOCAL_PILOT_READY_WITH_LIMITATIONS` / `NOT_READY`

## 2. Deployment Mode

```text
Local Machine / LAN
├── PostgreSQL          (required commercial SoT)
├── FastAPI API
├── Worker
├── Kiosk / Admin Frontend
├── Local Object Storage
├── Ollama              (optional)
├── Emotion-LLaMA / R1-Omni (optional)
└── Redis               (optional; not required for single-process pilot)
```

**Not in scope:** Docker runtime, Kubernetes, microservices, cloud-first, Kafka/RabbitMQ, multi-region.

## 3. Module Status

| Module | Path | Status |
| --- | --- | --- |
| identity | `modules/identity` | In progress |
| device | `modules/device` | In progress |
| catalog | `modules/catalog` | In progress |
| member | `modules/member` | In progress |
| ordering | `modules/ordering` | In progress |
| promotion | `modules/promotion` | In progress |
| recommendation | `modules/recommendation` | In progress |
| rag | `modules/rag` | In progress |
| intervention | `modules/intervention` | In progress |
| worker | `modules/worker` | In progress |
| fleet | `modules/fleet` | In progress |
| analytics | `modules/analytics` | In progress |
| integrations/* | llm, multimodal, object_storage, payment, pos | In progress |

## 4. Database Status

- Migrations `0001`–`0011` immutable.
- PostgreSQL is the only commercial Source of Truth for `local-pilot`.
- Object **metadata** in PostgreSQL; binaries on local disk.
- See [DATABASE.md](DATABASE.md).

## 5. Local Pilot Status

- Profile: `APP_PROFILE=local-pilot`
- Bootstrap: `backend/scripts/bootstrap_local_pilot.py`
- Validation: `validate_local_environment.py`, `validate_local_pilot_data_paths.py`

## 6. Test Status

- Architecture boundary tests under `tests/architecture/`
- Fast local: `scripts/local/test_fast.sh`
- Full JSON/unit regression + host Postgres integration when available

## 7. Known Limitations

- Payment / POS: **manual** adapters only (no fake capture success).
- Cloud S3 / merchant payment certification: out of scope.
- Not Production Certified.

## 8. Next Work

1. Finish module cutovers and delete legacy service/route files.
2. Frontend direct `/api/*` callers → 0 via v1Client.
3. Host Postgres integration + isolated restore evidence.

## 9. Last Verification

Recorded after each phase commit in `.codex/project_2026_current_state.json`.
