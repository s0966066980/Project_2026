CREATE TABLE IF NOT EXISTS ordering_carts (
 tenant_id UUID NOT NULL, store_id UUID NOT NULL, session_id TEXT NOT NULL,
 revision BIGINT NOT NULL DEFAULT 0 CHECK(revision >= 0), status TEXT NOT NULL CHECK(status IN ('open','closed','abandoned')),
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,store_id,session_id)
);
CREATE TABLE IF NOT EXISTS ordering_cart_lines (
 tenant_id UUID NOT NULL,store_id UUID NOT NULL,session_id TEXT NOT NULL,position INTEGER NOT NULL,
 item_id TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99),applied_offer_id TEXT NOT NULL DEFAULT '',options_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 PRIMARY KEY(tenant_id,store_id,session_id,position),
 FOREIGN KEY(tenant_id,store_id,session_id) REFERENCES ordering_carts(tenant_id,store_id,session_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS checkout_quotes (
 tenant_id UUID NOT NULL,store_id UUID NOT NULL,quote_id TEXT NOT NULL,session_id TEXT NOT NULL,cart_revision BIGINT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('active','superseded','stale','expired','consumed')),lines_json JSONB NOT NULL,pricing_json JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL,expires_at TIMESTAMPTZ NOT NULL,consumed_order_id TEXT NOT NULL DEFAULT '',PRIMARY KEY(tenant_id,store_id,quote_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS checkout_one_active_quote ON checkout_quotes(tenant_id,store_id,session_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS checkout_confirmation_attempts (
 tenant_id UUID NOT NULL,store_id UUID NOT NULL,idempotency_key TEXT NOT NULL,quote_id TEXT NOT NULL,outcome_type TEXT NOT NULL,outcome_json JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,store_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS confirmed_orders (
 tenant_id UUID NOT NULL,store_id UUID NOT NULL,order_id TEXT NOT NULL,quote_id TEXT NOT NULL,session_id TEXT NOT NULL,status TEXT NOT NULL,
 lines_json JSONB NOT NULL,pricing_json JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL,PRIMARY KEY(tenant_id,store_id,order_id),UNIQUE(tenant_id,store_id,quote_id)
);
CREATE TABLE IF NOT EXISTS checkout_outbox (
 tenant_id UUID NOT NULL,store_id UUID NOT NULL,event_id TEXT NOT NULL,event_type TEXT NOT NULL,aggregate_id TEXT NOT NULL,payload_json JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL,published_at TIMESTAMPTZ,
 PRIMARY KEY(tenant_id,store_id,event_id)
);
