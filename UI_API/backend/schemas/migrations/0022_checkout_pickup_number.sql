CREATE TABLE IF NOT EXISTS checkout_pickup_sequences (
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    last_number BIGINT NOT NULL CHECK (last_number > 0),
    PRIMARY KEY (tenant_id, store_id)
);

ALTER TABLE confirmed_orders
    ADD COLUMN IF NOT EXISTS pickup_number BIGINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN confirmed_orders.pickup_number IS
    'Store-scoped, human-facing pickup sequence allocated atomically during checkout confirmation.';
