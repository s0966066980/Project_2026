-- Milestone 1C: tenant/store-scoped Admin identity, RBAC, and revocable sessions.
-- This is an expand-only migration. Rollback is an application compatibility
-- switch; schema corrections use a new forward migration.

CREATE TABLE admin_users (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    login_identity TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, login_identity),
    UNIQUE (id, tenant_id)
);

CREATE TABLE admin_roles (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, code),
    UNIQUE (id, tenant_id)
);

CREATE TABLE admin_permissions (
    id UUID PRIMARY KEY,
    machine_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE admin_role_permissions (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    role_id UUID NOT NULL,
    permission_id UUID NOT NULL REFERENCES admin_permissions(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id, tenant_id) REFERENCES admin_roles(id, tenant_id)
);

CREATE TABLE admin_user_role_assignments (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL,
    role_id UUID NOT NULL,
    store_id UUID,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, tenant_id) REFERENCES admin_users(id, tenant_id),
    FOREIGN KEY (role_id, tenant_id) REFERENCES admin_roles(id, tenant_id),
    FOREIGN KEY (store_id, tenant_id) REFERENCES stores(id, tenant_id)
);

CREATE TABLE admin_sessions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    rotated_from_session_id UUID REFERENCES admin_sessions(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, tenant_id) REFERENCES admin_users(id, tenant_id),
    UNIQUE (id, tenant_id)
);

CREATE UNIQUE INDEX idx_admin_user_role_tenant_assignment
    ON admin_user_role_assignments(user_id, role_id)
    WHERE store_id IS NULL;
CREATE UNIQUE INDEX idx_admin_user_role_store_assignment
    ON admin_user_role_assignments(user_id, role_id, store_id)
    WHERE store_id IS NOT NULL;
CREATE INDEX idx_admin_users_tenant_login ON admin_users(tenant_id, login_identity);
CREATE INDEX idx_admin_role_assignments_user ON admin_user_role_assignments(tenant_id, user_id, status);
CREATE INDEX idx_admin_sessions_user_expiry ON admin_sessions(tenant_id, user_id, expires_at);

