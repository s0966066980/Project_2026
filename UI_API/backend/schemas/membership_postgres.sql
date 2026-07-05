CREATE TABLE IF NOT EXISTS members (
    phone TEXT PRIMARY KEY,
    phone_masked TEXT NOT NULL DEFAULT '',
    nickname TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    visit_count INTEGER NOT NULL DEFAULT 0,
    total_spend INTEGER NOT NULL DEFAULT 0,
    last_visit_at TEXT NOT NULL DEFAULT '',
    last_login_at TEXT NOT NULL DEFAULT '',
    login_count INTEGER NOT NULL DEFAULT 0,
    login_failed_count INTEGER NOT NULL DEFAULT 0,
    consent_version TEXT NOT NULL DEFAULT '',
    privacy_version TEXT NOT NULL DEFAULT '',
    consent_accepted_at TEXT NOT NULL DEFAULT '',
    consent_source TEXT NOT NULL DEFAULT '',
    order_history_consent BOOLEAN NOT NULL DEFAULT FALSE,
    personalization_consent BOOLEAN NOT NULL DEFAULT FALSE,
    data_retention_until TEXT NOT NULL DEFAULT '',
    deleted_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS member_preferences (
    phone TEXT PRIMARY KEY REFERENCES members(phone) ON DELETE CASCADE,
    item_freq JSONB NOT NULL DEFAULT '{}'::jsonb,
    category_freq JSONB NOT NULL DEFAULT '{}'::jsonb,
    pair_freq JSONB NOT NULL DEFAULT '{}'::jsonb,
    recent_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    preference_updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS member_sessions (
    session_id TEXT PRIMARY KEY,
    phone TEXT NOT NULL REFERENCES members(phone) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    cleared_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS member_orders (
    id BIGSERIAL PRIMARY KEY,
    phone TEXT NOT NULL REFERENCES members(phone) ON DELETE CASCADE,
    order_index INTEGER NOT NULL DEFAULT 0,
    session_id TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL DEFAULT '',
    total INTEGER NOT NULL DEFAULT 0,
    order_status TEXT NOT NULL DEFAULT 'completed',
    is_completed BOOLEAN NOT NULL DEFAULT TRUE,
    cancel_reason TEXT NOT NULL DEFAULT '',
    recommendation_success BOOLEAN NOT NULL DEFAULT FALSE,
    is_success BOOLEAN NOT NULL DEFAULT FALSE,
    cart_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    cart_items JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS member_order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES member_orders(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recommendation_events (
    event_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    member_phone_masked TEXT NOT NULL DEFAULT '',
    is_member BOOLEAN NOT NULL DEFAULT FALSE,
    event_type TEXT NOT NULL DEFAULT '',
    surface TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    item_id TEXT NOT NULL DEFAULT '',
    item_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    rank INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    quantity INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    timestamp TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    audit_id TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TEXT NOT NULL DEFAULT ''
);

ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS audit_id TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS last_login_at TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS login_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE members ADD COLUMN IF NOT EXISTS login_failed_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE members ADD COLUMN IF NOT EXISTS consent_version TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS privacy_version TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS consent_accepted_at TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS consent_source TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS order_history_consent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE members ADD COLUMN IF NOT EXISTS personalization_consent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE members ADD COLUMN IF NOT EXISTS data_retention_until TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN IF NOT EXISTS deleted_at TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_member_orders_phone ON member_orders(phone);
CREATE INDEX IF NOT EXISTS idx_member_order_items_item_id ON member_order_items(item_id);
CREATE INDEX IF NOT EXISTS idx_member_sessions_phone ON member_sessions(phone);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_session_id ON recommendation_events(session_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_item_id ON recommendation_events(item_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_events_timestamp ON recommendation_events(timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_audit_logs_audit_id ON admin_audit_logs(audit_id) WHERE audit_id <> '';
