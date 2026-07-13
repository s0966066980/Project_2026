-- Milestone 6B/6C/6D: durable recommendation governance, fleet state, and analytics sink.
-- Expand-only. Binary content and Redis presence remain outside these tables.

-- 6B Recommendation / Promotion governance
CREATE TABLE recommendation_strategies (
    strategy_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE recommendation_strategy_versions (
    id UUID PRIMARY KEY,
    strategy_id TEXT NOT NULL REFERENCES recommendation_strategies(strategy_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'published', 'paused', 'retired')),
    eligibility JSONB NOT NULL DEFAULT '{}'::jsonb,
    ranking_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    history JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (strategy_id, version)
);

CREATE INDEX idx_recommendation_strategy_versions_status
    ON recommendation_strategy_versions (strategy_id, status, version DESC);

CREATE TABLE recommendation_assignments (
    id UUID PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    session_ref TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    strategy_version INTEGER,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (experiment_id, session_ref),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE recommendation_governance_events (
    event_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    strategy_id TEXT NOT NULL DEFAULT '',
    strategy_version INTEGER,
    experiment_id TEXT NOT NULL DEFAULT '',
    variant_id TEXT NOT NULL DEFAULT '',
    session_ref TEXT NOT NULL DEFAULT '',
    member_opaque_ref TEXT NOT NULL DEFAULT '',
    surface TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL DEFAULT '',
    rank INTEGER,
    score DOUBLE PRECISION,
    reason_code TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_recommendation_governance_events_scope
    ON recommendation_governance_events (tenant_id, store_id, occurred_at DESC);

CREATE TABLE promotion_rule_versions (
    id UUID PRIMARY KEY,
    promotion_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'published', 'paused', 'retired')),
    rule_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (promotion_id, version),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

-- 6C Fleet durable state
CREATE TABLE fleet_device_state (
    device_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    app_version TEXT NOT NULL DEFAULT '',
    config_version TEXT NOT NULL DEFAULT '',
    health TEXT NOT NULL DEFAULT 'ok',
    last_error TEXT NOT NULL DEFAULT '',
    deployment_ring TEXT NOT NULL DEFAULT 'pilot',
    last_seen_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id)
);

CREATE TABLE fleet_config_versions (
    id UUID PRIMARY KEY,
    config_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    checksum TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (config_id, version),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE fleet_commands (
    id UUID PRIMARY KEY,
    device_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    actor TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    expires_at TIMESTAMPTZ,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acked_at TIMESTAMPTZ,
    UNIQUE (tenant_id, device_id, idempotency_key),
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id)
);

CREATE INDEX idx_fleet_commands_device_status
    ON fleet_commands (device_id, status, created_at DESC);

CREATE TABLE fleet_rollouts (
    id UUID PRIMARY KEY,
    rollout_id TEXT NOT NULL UNIQUE,
    ring TEXT NOT NULL CHECK (ring IN ('internal', 'pilot', 'percentage', 'general')),
    percentage INTEGER NOT NULL DEFAULT 0 CHECK (percentage >= 0 AND percentage <= 100),
    config_id TEXT NOT NULL DEFAULT '',
    config_version INTEGER,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6D Analytics durable sink
CREATE TABLE analytics_event_log (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT 'analytics-v1',
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID,
    device_id UUID,
    session_ref TEXT NOT NULL DEFAULT '',
    order_ref TEXT NOT NULL DEFAULT '',
    member_opaque_ref TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_analytics_event_log_scope_time
    ON analytics_event_log (tenant_id, store_id, occurred_at DESC);

CREATE TABLE analytics_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    event_type TEXT NOT NULL DEFAULT '',
    last_event_id TEXT NOT NULL DEFAULT '',
    last_occurred_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
