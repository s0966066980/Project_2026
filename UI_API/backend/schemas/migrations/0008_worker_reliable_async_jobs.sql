-- Milestone 2E: durable background jobs and reliable order_outbox delivery controls.
-- Expand-only. Rollback is an application process switch; schema fixes use a new forward migration.

ALTER TABLE order_outbox
    ADD COLUMN available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN locked_by TEXT,
    ADD COLUMN locked_until TIMESTAMPTZ,
    ADD COLUMN last_error TEXT NOT NULL DEFAULT '',
    ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN dead_lettered_at TIMESTAMPTZ;

ALTER TABLE order_outbox
    ADD CONSTRAINT order_outbox_max_attempts_positive CHECK (max_attempts > 0);

CREATE INDEX idx_order_outbox_claim
    ON order_outbox (available_at)
    WHERE published_at IS NULL AND dead_lettered_at IS NULL;

CREATE TABLE background_jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    job_type TEXT NOT NULL,
    payload_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'running', 'succeeded', 'failed', 'dead_letter', 'cancelled'
    )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    idempotency_key TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    visibility_timeout_seconds INTEGER NOT NULL DEFAULT 60 CHECK (visibility_timeout_seconds > 0),
    locked_by TEXT,
    locked_until TIMESTAMPTZ,
    safe_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, job_type, idempotency_key),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_background_jobs_claim
    ON background_jobs (available_at)
    WHERE status IN ('pending', 'running');

CREATE INDEX idx_background_jobs_scope_status
    ON background_jobs (tenant_id, store_id, status, created_at DESC);
