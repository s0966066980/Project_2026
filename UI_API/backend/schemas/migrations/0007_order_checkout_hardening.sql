-- Milestone 1G: transactional Order aggregate, snapshots, idempotency, and outbox.

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    origin_device_id UUID NOT NULL,
    member_id UUID,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'draft', 'pricing', 'pending_confirmation', 'confirmed', 'payment_pending',
        'paid', 'preparing', 'completed', 'cancel_pending', 'cancelled', 'failed'
    )),
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    currency TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
    option_total INTEGER NOT NULL CHECK (option_total >= 0),
    discount_total INTEGER NOT NULL CHECK (discount_total >= 0),
    tax_total INTEGER NOT NULL CHECK (tax_total >= 0),
    total INTEGER NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    UNIQUE (tenant_id, store_id, idempotency_key),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id),
    FOREIGN KEY (tenant_id, store_id, origin_device_id)
        REFERENCES devices(tenant_id, store_id, id),
    FOREIGN KEY (member_id, tenant_id) REFERENCES members(id, tenant_id)
);

CREATE TABLE order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    base_unit_price INTEGER NOT NULL CHECK (base_unit_price >= 0),
    option_unit_total INTEGER NOT NULL CHECK (option_unit_total >= 0),
    discount_unit_total INTEGER NOT NULL CHECK (discount_unit_total >= 0),
    final_unit_price INTEGER NOT NULL CHECK (final_unit_price >= 0),
    options_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE order_promotion_usages (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    order_item_id BIGINT NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    promotion_ref TEXT NOT NULL,
    promotion_title TEXT NOT NULL,
    discount_amount INTEGER NOT NULL CHECK (discount_amount >= 0),
    promotion_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (order_item_id, promotion_ref)
);

CREATE TABLE order_outcomes (
    order_id UUID PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
    checkout_success BOOLEAN NOT NULL,
    failure_code TEXT NOT NULL DEFAULT '',
    recommendation_success BOOLEAN,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE order_outbox (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    aggregate_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('order_confirmed', 'order_completed', 'order_cancelled')),
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    UNIQUE (aggregate_id, event_type),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX idx_orders_scope_created ON orders(tenant_id, store_id, created_at DESC);
CREATE INDEX idx_orders_member_created ON orders(tenant_id, member_id, created_at DESC);
CREATE INDEX idx_order_outbox_pending ON order_outbox(occurred_at) WHERE published_at IS NULL;
