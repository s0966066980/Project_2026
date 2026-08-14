CREATE TABLE IF NOT EXISTS voice_evidence (
    evidence_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    voice_turn_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    terminal_status TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    retry_outcome TEXT NOT NULL,
    rag_outcome TEXT NOT NULL CHECK (rag_outcome IN ('hit', 'miss', 'not_run')),
    rag_refs_json TEXT NOT NULL DEFAULT '{}',
    transcript_masked TEXT NOT NULL DEFAULT '',
    assistant_text_masked TEXT NOT NULL DEFAULT '',
    has_transcript BOOLEAN NOT NULL DEFAULT FALSE,
    has_assistant_text BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL,
    projection_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, store_id, voice_turn_id)
);
CREATE INDEX IF NOT EXISTS voice_evidence_scope_time
    ON voice_evidence (tenant_id, store_id, observed_at DESC, evidence_id DESC);

CREATE TABLE IF NOT EXISTS voice_evidence_outbox (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    voice_turn_id TEXT NOT NULL,
    terminal_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    projected_at TIMESTAMPTZ,
    UNIQUE (tenant_id, store_id, voice_turn_id)
);
CREATE INDEX IF NOT EXISTS voice_evidence_outbox_pending
    ON voice_evidence_outbox (status, available_at, created_at);

CREATE TABLE IF NOT EXISTS voice_evidence_backfill_runs (
    run_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    enqueued INTEGER NOT NULL DEFAULT 0
);
