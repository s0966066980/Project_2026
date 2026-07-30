-- One-way cutover to RAG Intelligence Studio.
--
-- Old RAG content and derived governance state are deliberately erased.  The
-- reset receipt records counts only; no content or raw query survives.
CREATE TABLE IF NOT EXISTS rag_reset_receipts (
    id UUID PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    reset_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deletion_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    contains_content BOOLEAN NOT NULL DEFAULT FALSE
);

DO $$
DECLARE
    documents_count BIGINT := 0;
    versions_count BIGINT := 0;
    traces_count BIGINT := 0;
    rebuilds_count BIGINT := 0;
BEGIN
    IF to_regclass('public.rag_documents') IS NOT NULL THEN
        SELECT COUNT(*) INTO documents_count FROM rag_documents;
    END IF;
    IF to_regclass('public.rag_document_versions') IS NOT NULL THEN
        SELECT COUNT(*) INTO versions_count FROM rag_document_versions;
    END IF;
    IF to_regclass('public.rag_retrieval_traces') IS NOT NULL THEN
        SELECT COUNT(*) INTO traces_count FROM rag_retrieval_traces;
    END IF;
    IF to_regclass('public.rag_rebuild_runs') IS NOT NULL THEN
        SELECT COUNT(*) INTO rebuilds_count FROM rag_rebuild_runs;
    END IF;

    INSERT INTO rag_reset_receipts (
        id, deployment_id, actor, deletion_counts, contains_content
    ) VALUES (
        gen_random_uuid(),
        current_setting('application_name', TRUE),
        'migration:0016',
        jsonb_build_object(
            'documents', documents_count,
            'versions', versions_count,
            'retrieval_traces', traces_count,
            'rebuild_runs', rebuilds_count
        ),
        FALSE
    );
END $$;

TRUNCATE TABLE rag_retrieval_traces, rag_rebuild_runs, rag_publications,
    rag_document_versions, rag_documents CASCADE;

CREATE TABLE IF NOT EXISTS rag_studio_states (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, store_id)
);

CREATE INDEX IF NOT EXISTS rag_studio_states_updated_at_idx
    ON rag_studio_states (updated_at DESC);
