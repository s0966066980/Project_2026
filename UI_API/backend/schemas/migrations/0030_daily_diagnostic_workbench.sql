-- Daily Operations Diagnostic Workbench: store-scoped questions and one
-- reviewable RAG candidate. Candidates never become retrieval material until
-- an authenticated application workflow confirms them.

CREATE TABLE IF NOT EXISTS optimization_diagnostic_question_bootstrap (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    question_id TEXT NOT NULL,
    seeded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, store_id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS optimization_diagnostic_questions (
    question_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    display_name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX IF NOT EXISTS optimization_diagnostic_questions_scope
    ON optimization_diagnostic_questions (tenant_id, store_id, updated_at);

CREATE TABLE IF NOT EXISTS optimization_knowledge_candidates (
    candidate_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    report_id TEXT NOT NULL REFERENCES optimization_reports(report_id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'abandoned', 'confirmed', 'stale', 'expired')),
    candidate_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX IF NOT EXISTS optimization_knowledge_candidates_pending
    ON optimization_knowledge_candidates (tenant_id, store_id, status, created_at);
