-- Milestone 1F: move Member domain identity to UUID while retaining phone compatibility.

ALTER TABLE members ADD COLUMN id UUID;
ALTER TABLE members ADD COLUMN phone_lookup_hash TEXT;
ALTER TABLE members ADD COLUMN phone_encrypted TEXT;
ALTER TABLE members ADD COLUMN key_version TEXT;
ALTER TABLE members ADD COLUMN pii_updated_at TIMESTAMPTZ;
ALTER TABLE members ADD COLUMN anonymized_at TIMESTAMPTZ;

UPDATE members
SET id = (
    SUBSTR(seed, 1, 8) || '-' || SUBSTR(seed, 9, 4) || '-4' || SUBSTR(seed, 14, 3) ||
    '-a' || SUBSTR(seed, 18, 3) || '-' || SUBSTR(seed, 21, 12)
)::uuid
FROM (
    SELECT phone AS legacy_phone,
           MD5(RANDOM()::text || CLOCK_TIMESTAMP()::text || tenant_id::text || phone) AS seed
    FROM members
    WHERE id IS NULL
) generated
WHERE members.phone = generated.legacy_phone AND members.id IS NULL;

ALTER TABLE member_preferences ADD COLUMN member_id UUID;
ALTER TABLE member_preferences ADD COLUMN tenant_id UUID;
ALTER TABLE member_sessions ADD COLUMN member_id UUID;
ALTER TABLE member_orders ADD COLUMN member_id UUID;

UPDATE member_preferences preferences
SET member_id = members.id,
    tenant_id = members.tenant_id
FROM members
WHERE preferences.phone = members.phone;

UPDATE member_sessions sessions
SET member_id = members.id
FROM members
WHERE sessions.phone = members.phone AND sessions.tenant_id = members.tenant_id;

UPDATE member_orders orders
SET member_id = members.id
FROM members
WHERE orders.phone = members.phone AND orders.tenant_id = members.tenant_id;

ALTER TABLE member_preferences DROP CONSTRAINT member_preferences_phone_fkey;
ALTER TABLE member_preferences DROP CONSTRAINT member_preferences_pkey;
ALTER TABLE member_sessions DROP CONSTRAINT member_sessions_phone_fkey;
ALTER TABLE member_sessions DROP CONSTRAINT member_sessions_member_scope_fk;
ALTER TABLE member_orders DROP CONSTRAINT member_orders_phone_fkey;
ALTER TABLE member_orders DROP CONSTRAINT member_orders_member_scope_fk;
ALTER TABLE members DROP CONSTRAINT members_pkey;

ALTER TABLE members ALTER COLUMN id SET NOT NULL;
ALTER TABLE members ADD CONSTRAINT members_pkey PRIMARY KEY (id);
ALTER TABLE members ADD CONSTRAINT members_id_tenant_unique UNIQUE (id, tenant_id);
ALTER TABLE members ADD CONSTRAINT members_tenant_lookup_unique UNIQUE (tenant_id, phone_lookup_hash);

ALTER TABLE member_preferences ALTER COLUMN member_id SET NOT NULL;
ALTER TABLE member_preferences ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE member_preferences ADD CONSTRAINT member_preferences_pkey PRIMARY KEY (member_id);
ALTER TABLE member_preferences ADD CONSTRAINT member_preferences_member_fk
    FOREIGN KEY (member_id, tenant_id) REFERENCES members(id, tenant_id) ON DELETE CASCADE;

ALTER TABLE member_sessions ALTER COLUMN member_id SET NOT NULL;
ALTER TABLE member_sessions ADD CONSTRAINT member_sessions_member_id_fk
    FOREIGN KEY (member_id, tenant_id) REFERENCES members(id, tenant_id) ON DELETE CASCADE;

ALTER TABLE member_orders ALTER COLUMN member_id SET NOT NULL;
ALTER TABLE member_orders ADD CONSTRAINT member_orders_member_id_fk
    FOREIGN KEY (member_id, tenant_id) REFERENCES members(id, tenant_id) ON DELETE CASCADE;

CREATE INDEX idx_member_preferences_tenant_member ON member_preferences(tenant_id, member_id);
CREATE INDEX idx_member_sessions_scope_member ON member_sessions(tenant_id, store_id, member_id);
CREATE INDEX idx_member_orders_scope_member ON member_orders(tenant_id, store_id, member_id);
