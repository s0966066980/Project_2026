-- Make the active checkout confirmation outbox durable across worker crashes.

ALTER TABLE checkout_outbox
    ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS locked_by TEXT,
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ;

ALTER TABLE checkout_outbox
    ADD CONSTRAINT checkout_outbox_max_attempts_positive CHECK (max_attempts > 0);

CREATE INDEX IF NOT EXISTS idx_checkout_outbox_claim
    ON checkout_outbox (available_at)
    WHERE published_at IS NULL AND dead_lettered_at IS NULL;
