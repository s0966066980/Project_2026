-- Campaign versions, recommendation decisions, visible touch events and order attribution.
-- Expand-only: legacy promotion_records, recommendation_events and analytics_event_log remain available.

CREATE TABLE campaign_definitions (
    id UUID PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 0 CHECK (current_version >= 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'scheduled', 'active', 'paused', 'ended', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, store_id, campaign_id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE TABLE campaign_versions (
    id UUID PRIMARY KEY,
    campaign_definition_id UUID NOT NULL REFERENCES campaign_definitions(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'review', 'scheduled', 'active', 'paused', 'ended', 'archived')),
    payload JSONB NOT NULL,
    actor_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    UNIQUE (campaign_definition_id, version)
);

CREATE TABLE recommendation_decisions (
    decision_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID,
    session_ref TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT '',
    strategy_version TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL DEFAULT '',
    variant_id TEXT NOT NULL DEFAULT '',
    fallback_status TEXT NOT NULL DEFAULT '',
    candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id),
    FOREIGN KEY (tenant_id, store_id, device_id) REFERENCES devices(tenant_id, store_id, id)
);

CREATE TABLE commercial_touch_events (
    event_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID,
    decision_id TEXT REFERENCES recommendation_decisions(decision_id),
    impression_id TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'decision', 'impression', 'click', 'add_to_cart', 'remove_from_cart',
        'purchase', 'cancel', 'ignore'
    )),
    placement TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    campaign_version INTEGER,
    item_id TEXT NOT NULL DEFAULT '',
    session_ref TEXT NOT NULL DEFAULT '',
    data_quality TEXT NOT NULL DEFAULT 'complete',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id),
    FOREIGN KEY (tenant_id, store_id, device_id) REFERENCES devices(tenant_id, store_id, id)
);

CREATE UNIQUE INDEX uq_commercial_touch_impression
    ON commercial_touch_events (tenant_id, store_id, impression_id, event_type, item_id)
    WHERE impression_id IS NOT NULL AND impression_id <> '';
CREATE INDEX idx_commercial_touch_scope_time
    ON commercial_touch_events (tenant_id, store_id, occurred_at DESC);
CREATE INDEX idx_commercial_touch_decision
    ON commercial_touch_events (decision_id, occurred_at);

CREATE TABLE order_touch_attributions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    order_item_id BIGINT NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    decision_id TEXT REFERENCES recommendation_decisions(decision_id),
    impression_id TEXT,
    attribution_type TEXT NOT NULL CHECK (attribution_type IN ('direct', 'view_through')),
    attributed_revenue INTEGER NOT NULL CHECK (attributed_revenue >= 0),
    attributed_discount INTEGER NOT NULL CHECK (attributed_discount >= 0),
    status TEXT NOT NULL CHECK (status IN ('provisional', 'confirmed', 'reversed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (order_item_id, attribution_type),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_order_touch_attribution_scope
    ON order_touch_attributions (tenant_id, store_id, created_at DESC);
