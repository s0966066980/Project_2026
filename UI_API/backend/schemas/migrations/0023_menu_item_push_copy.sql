-- Pre-authored AI push copy per menu item, replacing runtime LLM copy generation.
-- Two slots per item: base copy is evergreen and must never assert a promotion; campaign copy
-- is optional, names the offer it depends on, and stops being served the moment that offer is
-- no longer active. See docs/adr/0016-author-push-copy-ahead-of-time.md.

CREATE TABLE IF NOT EXISTS menu_item_push_copy (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    item_id TEXT NOT NULL,
    base_copy TEXT NOT NULL DEFAULT '',
    campaign_copy TEXT NOT NULL DEFAULT '',
    -- Offer this campaign copy depends on. Runtime serves campaign_copy only while this id is
    -- among the currently active offers, so ended campaigns fall back to base_copy on their own.
    campaign_offer_id TEXT NOT NULL DEFAULT '',
    is_new_item BOOLEAN NOT NULL DEFAULT FALSE,
    -- New-item status expires by date rather than relying on someone remembering to untick it.
    new_until DATE,
    actor_id TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, store_id, item_id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores(tenant_id, id)
);

CREATE INDEX IF NOT EXISTS menu_item_push_copy_scope_idx
    ON menu_item_push_copy (tenant_id, store_id);

COMMENT ON COLUMN menu_item_push_copy.base_copy IS
    'Evergreen push sentence. Rejected at save time if it asserts an unverified promotion.';
COMMENT ON COLUMN menu_item_push_copy.campaign_copy IS
    'Optional promotional sentence, served only while campaign_offer_id is an active offer.';
