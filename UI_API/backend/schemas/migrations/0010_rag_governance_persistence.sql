-- Milestone 6A: durable RAG governance metadata. Document binary content stays in object storage.
-- Expand-only. Rollback is application compatibility switch; schema fixes use a new forward migration.

CREATE TABLE rag_documents (
    document_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    owner TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE rag_document_versions (
    id UUID PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES rag_documents(document_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'published', 'retired', 'failed')),
    checksum TEXT NOT NULL,
    content_ref TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    extractor_version TEXT NOT NULL DEFAULT '',
    chunking_version TEXT NOT NULL DEFAULT '',
    embedding_provider TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_version TEXT NOT NULL DEFAULT '',
    retrieval_config_version TEXT NOT NULL DEFAULT '',
    index_version TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT '',
    published_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    last_rebuild_at TIMESTAMPTZ,
    history JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (document_id, version),
    UNIQUE (document_id, checksum)
);

CREATE INDEX idx_rag_document_versions_status
    ON rag_document_versions (document_id, status, version DESC);

CREATE TABLE rag_publications (
    document_id TEXT PRIMARY KEY REFERENCES rag_documents(document_id) ON DELETE CASCADE,
    published_version INTEGER NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_by TEXT NOT NULL DEFAULT '',
    index_namespace TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (document_id, published_version)
        REFERENCES rag_document_versions (document_id, version)
);

CREATE TABLE rag_retrieval_traces (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    query_ref TEXT NOT NULL,
    document_versions JSONB NOT NULL DEFAULT '[]'::jsonb,
    chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    scores JSONB NOT NULL DEFAULT '[]'::jsonb,
    provider TEXT NOT NULL DEFAULT '',
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL DEFAULT 'retrieval-trace-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_rag_retrieval_traces_scope_created
    ON rag_retrieval_traces (tenant_id, store_id, created_at DESC);

CREATE TABLE rag_rebuild_runs (
    id UUID PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES rag_documents(document_id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    side_effect_id TEXT NOT NULL DEFAULT '',
    safe_error TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    FOREIGN KEY (document_id, version) REFERENCES rag_document_versions (document_id, version),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_rag_rebuild_runs_document
    ON rag_rebuild_runs (document_id, started_at DESC);
