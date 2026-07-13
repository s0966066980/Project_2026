# TDD — Milestone 5B Object Storage Truthfulness

## RED contracts

1. In-memory adapter must not claim `aes-256-gcm-envelope` when bytes are stored plaintext.
2. Signed URL must use HMAC-SHA256 over object_id + tenant_id + expires + method with injected secret.
3. Tampered signature, wrong method, and expired timestamp must fail verification.
4. Local disk adapter must block path traversal and enforce tenant isolation.
5. Production/commercial runtime without signing secret must fail fast.
6. S3 adapter without credentials must report EXTERNAL_BLOCKED (not silent success).
7. Local AES-GCM must report `local-aes-gcm` and store ciphertext on disk.

## GREEN evidence

- `UI_API/tests/test_object_storage_production_path.py`
- `UI_API/backend/services/object_storage_service.py`
- `UI_API/backend/models/object_storage.py`
- `UI_API/backend/repositories/object_storage_repository.py`
- `UI_API/backend/schemas/migrations/0009_object_storage_metadata.sql`

## Classification

- Local / HMAC / metadata truthfulness: PRODUCTION_PATH_PASS (internal)
- Cloud S3/KMS wiring: EXTERNAL_BLOCKED
