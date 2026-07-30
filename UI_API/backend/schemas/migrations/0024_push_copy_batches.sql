-- Progress for one-click push copy generation.
--
-- Generating copy for a full menu takes minutes because each item costs an LLM call, so the work
-- runs as a background job. background_jobs itself only carries pending/running/succeeded, which
-- cannot answer "how far along is it"; keeping the per-item tally here means progress survives a
-- server restart instead of living in the browser tab that started it.

CREATE TABLE IF NOT EXISTS push_copy_batches (
    batch_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    -- fill_missing 只補尚未撰寫的品項；regenerate 會覆寫既有文案，因此兩者必須可分辨。
    mode TEXT NOT NULL CHECK (mode IN ('fill_missing', 'regenerate')),
    item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    total INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0),
    succeeded INTEGER NOT NULL DEFAULT 0 CHECK (succeeded >= 0),
    failed INTEGER NOT NULL DEFAULT 0 CHECK (failed >= 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
    last_error TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX IF NOT EXISTS push_copy_batches_scope_idx
    ON push_copy_batches (tenant_id, store_id, created_at DESC);

COMMENT ON COLUMN push_copy_batches.item_ids IS
    'Items this batch was created for, snapshotted at enqueue time so menu edits cannot change its scope.';
