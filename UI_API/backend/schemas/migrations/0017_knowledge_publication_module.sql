-- Independent Store Knowledge Base publication records (ADR-0006).
-- The superseded rag_studio_states blob is deliberately not migrated or dual-written.

CREATE TABLE IF NOT EXISTS knowledge_items (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    item_id TEXT NOT NULL,
    category TEXT NOT NULL,
    content_type TEXT NOT NULL,
    row_revision BIGINT NOT NULL DEFAULT 1 CHECK (row_revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, item_id)
);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    item_id TEXT NOT NULL,
    version BIGINT NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN (
        'draft', 'indexing', 'published', 'index_failed',
        'publication_failed', 'retired'
    )),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_checksum TEXT NOT NULL,
    chunks_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (tenant_id, store_id, item_id, version),
    FOREIGN KEY (tenant_id, store_id, item_id)
        REFERENCES knowledge_items (tenant_id, store_id, item_id)
);

CREATE TABLE IF NOT EXISTS publication_batches (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    batch_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, batch_id)
);

CREATE TABLE IF NOT EXISTS publication_attempts (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    attempt_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version BIGINT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('build', 'swap', 'cleanup', 'complete')),
    status TEXT NOT NULL CHECK (status IN (
        'in_progress', 'cleanup_pending', 'index_failed',
        'publication_failed', 'published'
    )),
    job_id TEXT,
    artifact_ref TEXT,
    cleanup_artifact_ref TEXT,
    artifact_manifest_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    safe_reason TEXT,
    retry_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    resume_count BIGINT NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, store_id, attempt_id),
    FOREIGN KEY (tenant_id, store_id, batch_id)
        REFERENCES publication_batches (tenant_id, store_id, batch_id),
    FOREIGN KEY (tenant_id, store_id, item_id, version)
        REFERENCES knowledge_versions (tenant_id, store_id, item_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS publication_attempts_one_active_item
    ON publication_attempts (tenant_id, store_id, item_id)
    WHERE status IN ('in_progress', 'cleanup_pending');

CREATE TABLE IF NOT EXISTS publication_batch_items (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    batch_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    attempt_id TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (tenant_id, store_id, batch_id, item_id),
    FOREIGN KEY (tenant_id, store_id, batch_id)
        REFERENCES publication_batches (tenant_id, store_id, batch_id)
);

CREATE TABLE IF NOT EXISTS published_knowledge_pointers (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    item_id TEXT NOT NULL,
    version BIGINT NOT NULL,
    attempt_id TEXT NOT NULL,
    artifact_ref TEXT NOT NULL,
    published_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, item_id),
    FOREIGN KEY (tenant_id, store_id, item_id, version)
        REFERENCES knowledge_versions (tenant_id, store_id, item_id, version)
);

CREATE TABLE IF NOT EXISTS knowledge_publication_audit (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    event_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version BIGINT NOT NULL,
    attempt_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    safe_reason TEXT,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, store_id, event_id)
);

CREATE TABLE IF NOT EXISTS knowledge_retirement_cleanups (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    cleanup_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    version BIGINT NOT NULL,
    artifact_ref TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
    safe_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, store_id, cleanup_id),
    FOREIGN KEY (tenant_id, store_id, item_id, version)
        REFERENCES knowledge_versions (tenant_id, store_id, item_id, version)
);

CREATE INDEX IF NOT EXISTS publication_attempts_store_updated_idx
    ON publication_attempts (tenant_id, store_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS knowledge_publication_audit_item_idx
    ON knowledge_publication_audit (tenant_id, store_id, item_id, occurred_at DESC);
