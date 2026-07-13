# Milestone 5B Inventory — Object Storage Truthfulness

## Current caller

| Caller | Path | Notes |
| --- | --- | --- |
| Unit / phase-4 tests | `tests/test_phase4_external_scale.py`, `tests/test_object_storage_production_path.py` | Primary consumers today |
| Future RAG / evidence / export | planned via ObjectStoragePort | Binary content; metadata durable |

## Current adapter

| Adapter | Role | Encryption metadata |
| --- | --- | --- |
| `InMemoryObjectStorage` | Test only | `none-test` (truthful; was falsely `aes-256-gcm-envelope`) |
| `LocalObjectStorage` | Development / pilot disk | `none-test` or `local-aes-gcm` when key injected |
| `S3ObjectStorage` | Cloud contract | `provider-managed` / `kms-envelope` only when cloud wired; otherwise EXTERNAL_BLOCKED |

## Current persistence

- Binary: local disk under `OBJECT_STORAGE_LOCAL_ROOT` or learning_data/object_storage; never PostgreSQL.
- Metadata: optional PostgreSQL table `object_storage_metadata` (migration `0009_object_storage_metadata.sql`).
- Local adapter also keeps sidecar JSON under `{root}/meta` for offline recovery.

## Current fallback

- Development without signing secret uses explicit non-production fallback only when not commercial runtime.
- Commercial runtime requires `OBJECT_STORAGE_SIGNING_SECRET` (fail fast).
- S3 without credentials raises EXTERNAL_BLOCKED (no fake store).

## Production path

1. Configure `OBJECT_STORAGE_BACKEND=local` (or `s3` when credentials exist).
2. Inject `OBJECT_STORAGE_SIGNING_SECRET`.
3. Optional `OBJECT_STORAGE_ENCRYPTION=local-aes-gcm` + key material.
4. `put` → encrypt (if configured) → atomic write → checksum → metadata persist.
5. `signed_url` → HMAC-SHA256(object_id, tenant_id, expires, method).
6. Consumer verifies signature + expiry + tenant + method.

## Compatibility path

- In-memory backend remains for unit tests (`OBJECT_STORAGE_BACKEND=memory`).
- Phase-4 tests continue to exercise isolation and signed URL shape.

## Test path

- Unit: truthful metadata, HMAC, local disk, AES-GCM, path traversal, retention, S3 blocked.
- Migration: `0009` expand-only metadata table.
- PostgreSQL metadata upsert when `MEMBER_STORAGE_BACKEND=postgres`.

## Known gaps

- Cloud S3 SDK put/get/stream wiring: EXTERNAL_BLOCKED until Milestone 10B credentials.
- KMS envelope production: EXTERNAL_BLOCKED until cloud KMS policy.
- Production callers for RAG evidence binary cutover expand in 5D/6A.
