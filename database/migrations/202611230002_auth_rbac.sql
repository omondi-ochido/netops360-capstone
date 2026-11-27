-- Additive Supabase Auth profile and database-backed RBAC model.
-- Requires the core schema and 202611230001_audit_logs.sql.
BEGIN;

CREATE TABLE IF NOT EXISTS profiles (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name text NOT NULL,
    email text NOT NULL,
    phone_number INTEGER,
    account_status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    CONSTRAINT profiles_status_valid CHECK (account_status IN ('pending','active','suspended')),
    CONSTRAINT profiles_name_nonempty CHECK (length(btrim(full_name)) > 0),
    CONSTRAINT profiles_email_nonempty CHECK (length(btrim(email)) > 3)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_profiles_email_lower ON profiles (lower(email));

CREATE TABLE IF NOT EXISTS roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT roles_name_valid CHECK (name IN ('super_admin','admin','network_operator','viewer'))
);

CREATE TABLE IF NOT EXISTS permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_key text NOT NULL UNIQUE,
    description text NOT NULL,
    resource text NOT NULL,
    action text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT permissions_key_format CHECK (permission_key ~ '^[a-z_]+\.[a-z_]+$')
);

CREATE TABLE IF NOT EXISTS user_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    assigned_by uuid REFERENCES profiles(id) ON DELETE SET NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_roles_user_role_key UNIQUE (user_id, role_id)
);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_user ON user_roles (role_id, user_id);

CREATE TABLE IF NOT EXISTS role_permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    CONSTRAINT role_permissions_role_permission_key UNIQUE (role_id, permission_id)
);
CREATE INDEX IF NOT EXISTS idx_role_permissions_permission ON role_permissions (permission_id, role_id);

CREATE TABLE IF NOT EXISTS revoked_sessions (
    session_id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    revoked_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CONSTRAINT revoked_session_expiry_valid CHECK (expires_at > revoked_at)
);
CREATE INDEX IF NOT EXISTS idx_revoked_sessions_expiry ON revoked_sessions (expires_at);

ALTER TABLE audit_logs
    ADD COLUMN IF NOT EXISTS actor_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS description text,
    ADD COLUMN IF NOT EXISTS ip_address inet;
CREATE INDEX IF NOT EXISTS idx_audit_actor_user_time ON audit_logs (actor_user_id, occurred_at DESC)
    WHERE actor_user_id IS NOT NULL;

CREATE OR REPLACE FUNCTION set_profile_updated_at()
RETURNS trigger LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;
CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION set_profile_updated_at();

-- Serialize changes that could remove the final active Super Admin. Both the
-- route layer and these triggers check this; the database trigger closes races.
CREATE OR REPLACE FUNCTION guard_last_active_super_admin()
RETURNS trigger LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE
    target_user uuid;
    active_admin_count integer;
    was_active_admin boolean := false;
    remains_active_admin boolean := false;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('netops360:last-active-super-admin', 0));

    IF TG_TABLE_NAME = 'user_roles' THEN
        target_user := OLD.user_id;
        SELECT EXISTS (
            SELECT 1 FROM roles WHERE id = OLD.role_id AND name = 'super_admin'
        ) INTO was_active_admin;
        IF TG_OP = 'UPDATE' THEN
            SELECT EXISTS (
                SELECT 1 FROM roles WHERE id = NEW.role_id AND name = 'super_admin'
            ) INTO remains_active_admin;
        END IF;
    ELSE
        target_user := OLD.id;
        was_active_admin := OLD.account_status = 'active' AND EXISTS (
            SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = OLD.id AND r.name = 'super_admin'
        );
        remains_active_admin := TG_OP = 'UPDATE' AND NEW.account_status = 'active';
    END IF;

    IF was_active_admin AND NOT remains_active_admin THEN
        SELECT count(*) INTO active_admin_count
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        JOIN profiles p ON p.id = ur.user_id
        WHERE r.name = 'super_admin' AND p.account_status = 'active';
        IF active_admin_count <= 1 THEN
            RAISE EXCEPTION 'cannot remove the last active Super Admin' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_user_roles_guard_last_admin ON user_roles;
CREATE TRIGGER trg_user_roles_guard_last_admin BEFORE DELETE OR UPDATE ON user_roles
    FOR EACH ROW EXECUTE FUNCTION guard_last_active_super_admin();
DROP TRIGGER IF EXISTS trg_profiles_guard_last_admin ON profiles;
CREATE TRIGGER trg_profiles_guard_last_admin BEFORE DELETE OR UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION guard_last_active_super_admin();

INSERT INTO roles(name, description) VALUES
    ('super_admin','Full application administration.'),
    ('admin','Manage operations and ordinary user accounts.'),
    ('network_operator','Operate network monitoring and incident response.'),
    ('viewer','Read-only network visibility.')
ON CONFLICT (name) DO NOTHING;

INSERT INTO permissions(permission_key, description, resource, action) VALUES
    ('devices.read','View managed devices.','devices','read'),
    ('devices.create','Create managed devices.','devices','create'),
    ('devices.update','Update managed devices and settings.','devices','update'),
    ('devices.delete','Deactivate managed devices.','devices','delete'),
    ('monitoring.read','View monitoring data.','monitoring','read'),
    ('monitoring.manage','Run and configure monitoring.','monitoring','manage'),
    ('rules.read','View monitoring rules.','rules','read'),
    ('rules.create','Create monitoring rules.','rules','create'),
    ('rules.update','Update monitoring rules.','rules','update'),
    ('rules.delete','Delete monitoring rules.','rules','delete'),
    ('incidents.read','View incidents.','incidents','read'),
    ('incidents.acknowledge','Acknowledge incidents.','incidents','acknowledge'),
    ('incidents.resolve','Resolve incidents.','incidents','resolve'),
    ('automation.read','View automation executions.','automation','read'),
    ('automation.execute','Execute approved automation actions.','automation','execute'),
    ('backups.read','View backup metadata and protected backup content.','backups','read'),
    ('backups.create','Create configuration backups.','backups','create'),
    ('backups.restore','Restore a configuration backup.','backups','restore'),
    ('users.read','View user accounts.','users','read'),
    ('users.create','Invite user accounts.','users','create'),
    ('users.update','Update user profile information.','users','update'),
    ('users.suspend','Suspend or reactivate user accounts.','users','suspend'),
    ('roles.read','View roles and permissions.','roles','read'),
    ('roles.assign','Assign roles within own authority.','roles','assign'),
    ('audit.read','View audit history.','audit','read'),
    ('system.manage','Manage system-level configuration and authority.','system','manage')
ON CONFLICT (permission_key) DO NOTHING;

INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.name = 'super_admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.permission_key = ANY(ARRAY[
    'devices.read','devices.create','devices.update','devices.delete',
    'monitoring.read','monitoring.manage',
    'rules.read','rules.create','rules.update','rules.delete',
    'incidents.read','incidents.acknowledge','incidents.resolve',
    'automation.read','automation.execute','backups.read','backups.create',
    'users.read','users.create','users.update','users.suspend','roles.read','roles.assign','audit.read'
]) WHERE r.name = 'admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.permission_key = ANY(ARRAY[
    'devices.read','monitoring.read','monitoring.manage','rules.read','incidents.read',
    'incidents.acknowledge','incidents.resolve','automation.read','automation.execute','backups.read'
]) WHERE r.name = 'network_operator'
ON CONFLICT (role_id, permission_id) DO NOTHING;
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.permission_key = ANY(ARRAY[
    'devices.read','monitoring.read','rules.read','incidents.read'
]) WHERE r.name = 'viewer'
ON CONFLICT (role_id, permission_id) DO NOTHING;

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE revoked_sessions ENABLE ROW LEVEL SECURITY;
-- All auth/profile/role access goes through Flask's verified identity and RBAC.
REVOKE ALL ON profiles, roles, permissions, user_roles, role_permissions, revoked_sessions, audit_logs FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON profiles, roles, permissions, user_roles, role_permissions, revoked_sessions TO service_role;
GRANT SELECT, INSERT ON audit_logs TO service_role;

REVOKE ALL ON FUNCTION guard_last_active_super_admin() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION set_profile_updated_at() FROM PUBLIC, anon, authenticated;

INSERT INTO schema_migrations(version)
VALUES ('202611230002_auth_rbac')
ON CONFLICT (version) DO NOTHING;
COMMIT;

-- Rollback is deliberately manual: remove only these additive objects after
-- exporting user_roles/audit identity metadata and coordinating Auth users.
