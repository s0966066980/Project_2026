-- Store-scoped menu catalog master (ADR-0018).
-- menu.json is seed-only; runtime reads/writes this table per tenant+store.

CREATE TABLE IF NOT EXISTS store_menu_items (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    item_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image TEXT NOT NULL DEFAULT '',
    retired_at TIMESTAMPTZ,
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, store_id, item_id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id),
    CONSTRAINT store_menu_items_price_positive CHECK (price > 0 AND price <= 100000)
);

CREATE INDEX IF NOT EXISTS store_menu_items_scope_active_idx
    ON store_menu_items (tenant_id, store_id)
    WHERE retired_at IS NULL;

CREATE INDEX IF NOT EXISTS store_menu_items_scope_category_idx
    ON store_menu_items (tenant_id, store_id, category)
    WHERE retired_at IS NULL;

COMMENT ON TABLE store_menu_items IS
    'Per-store sellable product master. Retirement is soft (retired_at); hard delete is not the admin path.';
COMMENT ON COLUMN store_menu_items.extra IS
    'Seed-preserved fields (aliases, nutrition, etc.) not exposed in v1 authoring form.';
COMMENT ON COLUMN store_menu_items.image IS
    'http(s) URL, /static/ path, or object:<object_id> reference after upload.';
