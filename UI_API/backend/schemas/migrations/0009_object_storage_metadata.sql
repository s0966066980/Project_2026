-- Milestone 5B: durable object metadata. Binary bytes stay outside PostgreSQL.
-- Expand-only. Rollback is an application process switch; schema fixes use a new forward migration.

CREATE TABLE object_storage_metadata (
    object_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    owner TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    checksum TEXT NOT NULL,
    encryption TEXT NOT NULL,
    key_version TEXT NOT NULL DEFAULT '',
    retention_days INTEGER NOT NULL DEFAULT 30 CHECK (retention_days > 0),
    provider TEXT NOT NULL DEFAULT 'local',
    bucket TEXT NOT NULL DEFAULT '',
    provider_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_object_storage_metadata_tenant_created
    ON object_storage_metadata (tenant_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_object_storage_metadata_retention
    ON object_storage_metadata (created_at, retention_days)
    WHERE deleted_at IS NULL;
