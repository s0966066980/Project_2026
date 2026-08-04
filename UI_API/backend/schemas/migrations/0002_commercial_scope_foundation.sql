-- Milestone 1B reserved legacy scope identifiers:
-- tenant 00000000-0000-4000-8000-000000000001
-- store  00000000-0000-4000-8000-000000000002
-- device 00000000-0000-4000-8000-000000000003

CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE stores (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, code),
    UNIQUE (id, tenant_id)
);

CREATE TABLE devices (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    store_id UUID NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    app_version TEXT,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id),
    UNIQUE (store_id, code),
    UNIQUE (id, store_id, tenant_id)
);

INSERT INTO tenants (id, code, name, status)
VALUES ('00000000-0000-4000-8000-000000000001', 'legacy-default', 'Default Tenant', 'active')
ON CONFLICT DO NOTHING;

INSERT INTO stores (id, tenant_id, code, name, timezone, status)
VALUES (
    '00000000-0000-4000-8000-000000000002',
    '00000000-0000-4000-8000-000000000001',
    'legacy-default',
    'Default Store',
    'Asia/Taipei',
    'active'
)
ON CONFLICT DO NOTHING;

INSERT INTO devices (id, tenant_id, store_id, code, name, status)
VALUES (
    '00000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000002',
    'legacy-kiosk',
    'Legacy Kiosk',
    'active'
)
ON CONFLICT DO NOTHING;

ALTER TABLE members ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE member_sessions ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE member_sessions ADD COLUMN IF NOT EXISTS store_id UUID;
ALTER TABLE member_sessions ADD COLUMN IF NOT EXISTS origin_device_id UUID;
ALTER TABLE member_orders ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE member_orders ADD COLUMN IF NOT EXISTS store_id UUID;
ALTER TABLE member_orders ADD COLUMN IF NOT EXISTS origin_device_id UUID;
ALTER TABLE recommendation_events ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE recommendation_events ADD COLUMN IF NOT EXISTS store_id UUID;
ALTER TABLE recommendation_events ADD COLUMN IF NOT EXISTS device_id UUID;
ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE admin_audit_logs ADD COLUMN IF NOT EXISTS store_id UUID;

UPDATE members
SET tenant_id = '00000000-0000-4000-8000-000000000001'
WHERE tenant_id IS NULL;

UPDATE member_sessions
SET tenant_id = '00000000-0000-4000-8000-000000000001',
    store_id = '00000000-0000-4000-8000-000000000002',
    origin_device_id = '00000000-0000-4000-8000-000000000003'
WHERE tenant_id IS NULL OR store_id IS NULL OR origin_device_id IS NULL;

UPDATE member_orders
SET tenant_id = '00000000-0000-4000-8000-000000000001',
    store_id = '00000000-0000-4000-8000-000000000002',
    origin_device_id = '00000000-0000-4000-8000-000000000003'
WHERE tenant_id IS NULL OR store_id IS NULL OR origin_device_id IS NULL;

UPDATE recommendation_events
SET tenant_id = '00000000-0000-4000-8000-000000000001',
    store_id = '00000000-0000-4000-8000-000000000002',
    device_id = '00000000-0000-4000-8000-000000000003'
WHERE tenant_id IS NULL OR store_id IS NULL OR device_id IS NULL;

UPDATE admin_audit_logs
SET tenant_id = '00000000-0000-4000-8000-000000000001',
    store_id = '00000000-0000-4000-8000-000000000002'
WHERE tenant_id IS NULL OR store_id IS NULL;

ALTER TABLE members
    ADD CONSTRAINT members_tenant_fk FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE members
    ADD CONSTRAINT members_phone_tenant_unique UNIQUE (phone, tenant_id);
ALTER TABLE member_sessions
    ADD CONSTRAINT member_sessions_scope_fk
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id);
ALTER TABLE member_sessions
    ADD CONSTRAINT member_sessions_member_scope_fk
    FOREIGN KEY (phone, tenant_id) REFERENCES members(phone, tenant_id);
ALTER TABLE member_sessions
    ADD CONSTRAINT member_sessions_origin_device_fk
    FOREIGN KEY (origin_device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id);
ALTER TABLE member_orders
    ADD CONSTRAINT member_orders_scope_fk
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id);
ALTER TABLE member_orders
    ADD CONSTRAINT member_orders_member_scope_fk
    FOREIGN KEY (phone, tenant_id) REFERENCES members(phone, tenant_id);
ALTER TABLE member_orders
    ADD CONSTRAINT member_orders_origin_device_fk
    FOREIGN KEY (origin_device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id);
ALTER TABLE recommendation_events
    ADD CONSTRAINT recommendation_events_scope_fk
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id);
ALTER TABLE recommendation_events
    ADD CONSTRAINT recommendation_events_device_fk
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id);
ALTER TABLE admin_audit_logs
    ADD CONSTRAINT admin_audit_logs_tenant_fk FOREIGN KEY (tenant_id) REFERENCES tenants(id);
ALTER TABLE admin_audit_logs
    ADD CONSTRAINT admin_audit_logs_store_fk
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id);

CREATE INDEX idx_members_tenant_phone ON members(tenant_id, phone);
CREATE INDEX idx_member_sessions_scope_session ON member_sessions(tenant_id, store_id, session_id);
CREATE INDEX idx_member_orders_scope_phone ON member_orders(tenant_id, store_id, phone);
CREATE INDEX idx_recommendation_events_scope_session
    ON recommendation_events(tenant_id, store_id, device_id, session_id);
CREATE INDEX idx_admin_audit_logs_scope_created
    ON admin_audit_logs(tenant_id, store_id, created_at);
