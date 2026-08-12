-- P4 Optimization Lab: store-scoped de-identified evidence and reference-only
-- reports. These tables never receive raw media, identity, session, order,
-- payment or individual-emotion fields. JSON is text by contract so the same
-- repository adapter remains migration-testable without a fake Postgres path.

CREATE TABLE IF NOT EXISTS optimization_evidence (
    evidence_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    transcript_masked TEXT NOT NULL DEFAULT '',
    assistant_text_masked TEXT NOT NULL DEFAULT '',
    rag_hit TEXT NOT NULL DEFAULT '{}',
    voice_outcome TEXT NOT NULL CHECK (voice_outcome IN ('success', 'failed', 'unknown', 'not_observed')),
    failure_type TEXT NOT NULL DEFAULT '',
    retry_outcome TEXT NOT NULL DEFAULT '',
    synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX IF NOT EXISTS optimization_evidence_scope_time
    ON optimization_evidence (tenant_id, store_id, observed_at);

CREATE TABLE IF NOT EXISTS optimization_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    store_date DATE NOT NULL,
    timezone TEXT NOT NULL,
    cutoff_at TIMESTAMPTZ NOT NULL,
    partial BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_ids TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS optimization_reports (
    report_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES optimization_snapshots(snapshot_id),
    analyzer_id TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    model TEXT NOT NULL,
    effort TEXT NOT NULL,
    data_scope TEXT NOT NULL CHECK (data_scope IN ('synthetic_only', 'customer_evidence')),
    report_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('partial', 'complete')),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS optimization_egress_audits (
    audit_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    report_id TEXT NOT NULL REFERENCES optimization_reports(report_id),
    analyzer_id TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    model TEXT NOT NULL,
    effort TEXT NOT NULL,
    data_scope TEXT NOT NULL,
    evidence_count INTEGER NOT NULL CHECK (evidence_count >= 0),
    evidence_ids TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE IF NOT EXISTS optimization_access_audits (
    audit_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    report_id TEXT NOT NULL REFERENCES optimization_reports(report_id),
    evidence_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    step_up_expires_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);
