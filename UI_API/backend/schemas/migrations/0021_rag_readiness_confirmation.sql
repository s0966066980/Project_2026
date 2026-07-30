CREATE TABLE IF NOT EXISTS rag_retrieval_checks (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL REFERENCES stores(id),
    check_id TEXT NOT NULL,
    index_identity TEXT NOT NULL,
    configuration_version BIGINT,
    method TEXT NOT NULL,
    top_k INTEGER NOT NULL,
    relevance_policy TEXT NOT NULL,
    effective_method TEXT NOT NULL,
    fallback_used TEXT NOT NULL DEFAULT '',
    result_fingerprint TEXT NOT NULL,
    result_count INTEGER NOT NULL CHECK (result_count >= 0),
    eligible BOOLEAN NOT NULL,
    eligibility_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    confirmed_by TEXT,
    PRIMARY KEY (tenant_id, store_id, check_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_retrieval_confirmation
    ON rag_retrieval_checks (
        tenant_id,
        store_id,
        index_identity,
        configuration_version,
        confirmed_at DESC
    );
