# Pilot Operations Runbook

Every incident starts with time, environment, release SHA, safe request/trace IDs, current `/live` and `/ready`, and an incident owner. Never paste credentials, full phone, DATABASE_URL, raw prompt or production data into tickets/chat.

## Database / Migration

1. Stop rollout and nonessential writes if `/ready` reports database or migration failure.
2. Run migration `status` and `validate --require-clean`; never edit applied checksum rows.
3. Run commercial scope and Member identity validators. Preserve count-only output.
4. Follow [backup/recovery](../POSTGRESQL_MIGRATIONS.md#backup-before-migration); prefer forward repair or isolated restore verification.

## Scope / Auth / Device

For scope failure, identify tenant/store/device only from verified principal and server logs. Revoke the affected Admin/device session or credential, preserve audit records, and validate hierarchy before re-enable. Never trust client scope headers.

## Checkout

Check `checkout_attempts_total`, idempotency replay/conflict, PostgreSQL error code, Order/outcome/items and outbox in one scope. Retry with the same key and identical request; a different fingerprint must remain conflict. Do not reconstruct total from client input.

## WebSocket

Check origin/auth denial and connection/disconnection metrics, then session cookie/credential state. Keep message payload out of logs. A realtime outage must not invalidate an already committed Order.

## Redis Shared Infrastructure

If `/ready` reports shared infrastructure failure, do not disable production security rate limiting to restore traffic. Check Redis service health, network/DNS, pool/timeout and secret injection without copying `REDIS_URL` into logs or tickets. Security rate limits and required correctness locks stay fail closed; noncritical cache may degrade to a miss. After recovery, verify ping, cross-instance counter, TTL and owner-token lock before restoring normal traffic.

## Worker / Outbox

Long-running or retriable work belongs in the worker process (`python backend/scripts/run_worker.py`), not the API request path. API callers only enqueue jobs or write transactional outbox rows.

1. Inspect `worker_jobs_depth`, `worker_jobs_oldest_age_seconds`, `order_outbox_pending`, `worker_jobs_retry_total` and `worker_jobs_dlq_total`.
2. Confirm worker process health and PostgreSQL connectivity; do not mark `published_at` manually to hide backlog.
3. Poison messages move to dead-letter after max attempts; preserve `safe_error`/`last_error` (already redacted) for replay after a fix.
4. Re-delivery of an already published outbox event must remain idempotent; do not re-run side effects.
5. Job `payload_ref` must stay reference-only — no passwords, tokens, full phone or card data.

## AI degraded

Disable or bypass the affected provider adapter, retain deterministic menu/pricing/checkout, and monitor fallback. AI, RAG and emotion availability do not block `/ready` for basic checkout.

## Backup / Restore

Verify backup checksum and `pg_restore --list`; restore first into an isolated database and reconcile migration versions/counts. Production replacement requires maintenance window and explicit operations approval.

## Incident

Assign commander, severity and communication cadence; contain, preserve evidence, recover, validate, then document timeline/root cause/actions. Rotate exposed credentials and notify privacy/security owners when PII exposure is suspected.
