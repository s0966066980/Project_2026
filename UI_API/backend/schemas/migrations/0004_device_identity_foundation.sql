-- Milestone 1D: per-device credentials, short-lived sessions, and safe events.

CREATE TABLE device_credentials (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID NOT NULL,
    key_id TEXT NOT NULL UNIQUE,
    credential_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    rotation_valid_until TIMESTAMPTZ,
    rotated_from_credential_id UUID REFERENCES device_credentials(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id),
    UNIQUE (id, device_id, store_id, tenant_id)
);

CREATE TABLE device_sessions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID NOT NULL,
    credential_id UUID NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (credential_id, device_id, store_id, tenant_id)
        REFERENCES device_credentials(id, device_id, store_id, tenant_id),
    UNIQUE (id, device_id, store_id, tenant_id)
);

CREATE TABLE device_credential_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL,
    device_id UUID NOT NULL,
    credential_id UUID,
    event_type TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (device_id, store_id, tenant_id) REFERENCES devices(id, store_id, tenant_id),
    FOREIGN KEY (credential_id, device_id, store_id, tenant_id)
        REFERENCES device_credentials(id, device_id, store_id, tenant_id)
);

CREATE INDEX idx_device_credentials_scope_status
    ON device_credentials(tenant_id, store_id, device_id, status);
CREATE INDEX idx_device_sessions_scope_expiry
    ON device_sessions(tenant_id, store_id, device_id, expires_at);
CREATE INDEX idx_device_credential_events_scope_created
    ON device_credential_events(tenant_id, store_id, device_id, created_at);
