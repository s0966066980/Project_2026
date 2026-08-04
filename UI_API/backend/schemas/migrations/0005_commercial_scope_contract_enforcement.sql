-- Milestone 1E: contract core scope and add formal scoped operational storage.

ALTER TABLE members ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE member_sessions ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE member_sessions ALTER COLUMN store_id SET NOT NULL;
ALTER TABLE member_sessions ALTER COLUMN origin_device_id SET NOT NULL;
ALTER TABLE member_orders ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE member_orders ALTER COLUMN store_id SET NOT NULL;
ALTER TABLE member_orders ALTER COLUMN origin_device_id SET NOT NULL;
ALTER TABLE recommendation_events ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE recommendation_events ALTER COLUMN store_id SET NOT NULL;
ALTER TABLE recommendation_events ALTER COLUMN device_id SET NOT NULL;
ALTER TABLE admin_audit_logs ALTER COLUMN tenant_id SET NOT NULL;

CREATE TABLE store_availability (
    store_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id),
    UNIQUE (store_id, tenant_id)
);

CREATE TABLE commercial_settings_versions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    version BIGINT NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id)
);

CREATE TABLE promotion_records (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    promotion_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id),
    UNIQUE (tenant_id, store_id, promotion_id)
);

CREATE TABLE interaction_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID NOT NULL,
    event_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id),
    UNIQUE (tenant_id, store_id, device_id, event_id)
);

CREATE TABLE intervention_outcomes (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID NOT NULL,
    intervention_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id),
    UNIQUE (tenant_id, store_id, device_id, intervention_id)
);

CREATE TABLE rag_asset_scopes (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    asset_id TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id)
);

CREATE INDEX idx_store_availability_tenant ON store_availability(tenant_id, store_id);
CREATE INDEX idx_settings_scope_version ON commercial_settings_versions(tenant_id, store_id, version DESC);
CREATE UNIQUE INDEX uq_settings_tenant_version
    ON commercial_settings_versions(tenant_id, version) WHERE store_id IS NULL;
CREATE UNIQUE INDEX uq_settings_store_version
    ON commercial_settings_versions(tenant_id, store_id, version) WHERE store_id IS NOT NULL;
CREATE INDEX idx_promotions_scope_status ON promotion_records(tenant_id, store_id, status);
CREATE INDEX idx_interaction_scope_session ON interaction_events(tenant_id, store_id, device_id, session_id);
CREATE INDEX idx_intervention_scope_session ON intervention_outcomes(tenant_id, store_id, device_id, session_id);
CREATE INDEX idx_rag_asset_scope ON rag_asset_scopes(tenant_id, store_id, asset_id);
CREATE UNIQUE INDEX uq_rag_asset_tenant
    ON rag_asset_scopes(tenant_id, asset_id) WHERE store_id IS NULL;
CREATE UNIQUE INDEX uq_rag_asset_store
    ON rag_asset_scopes(tenant_id, store_id, asset_id) WHERE store_id IS NOT NULL;
