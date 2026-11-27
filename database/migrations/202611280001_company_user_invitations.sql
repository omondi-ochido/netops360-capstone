-- Tenant-scoped Company Admin user management and expiring invite acceptance.
BEGIN;

CREATE TABLE IF NOT EXISTS company_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    email text NOT NULL,
    full_name text NOT NULL,
    company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    invited_by uuid NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    CONSTRAINT company_invitations_status_valid
        CHECK (status IN ('pending', 'accepted', 'expired', 'revoked'))
);
CREATE UNIQUE INDEX IF NOT EXISTS company_invitations_one_pending_user
    ON company_invitations (user_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS company_invitations_company_created
    ON company_invitations (company_id, created_at DESC);
CREATE INDEX IF NOT EXISTS company_invitations_email_pending
    ON company_invitations (lower(email)) WHERE status = 'pending';

ALTER TABLE company_invitations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON company_invitations FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON company_invitations TO service_role;

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_audit_company_time
    ON audit_logs (company_id, occurred_at DESC) WHERE company_id IS NOT NULL;
UPDATE audit_logs SET company_id = (after_metadata->>'company_id')::uuid
WHERE company_id IS NULL AND after_metadata ? 'company_id'
  AND after_metadata->>'company_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
UPDATE audit_logs a SET company_id = p.company_id
FROM profiles p
WHERE a.company_id IS NULL AND a.actor_user_id = p.id AND p.company_id IS NOT NULL;

-- Operational ownership is nullable for legacy rows so production owners can
-- review and backfill data without guessing tenant ownership.
ALTER TABLE devices ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;
ALTER TABLE monitoring_logs ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;
ALTER TABLE rules ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;
ALTER TABLE config_backups ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;
ALTER TABLE automation_logs ADD COLUMN IF NOT EXISTS company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;

ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_hostname_key;
ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_ip_address_key;
ALTER TABLE rules DROP CONSTRAINT IF EXISTS rules_name_key;

CREATE INDEX IF NOT EXISTS idx_devices_company ON devices(company_id, hostname);
CREATE INDEX IF NOT EXISTS idx_monitoring_logs_company_time ON monitoring_logs(company_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_rules_company ON rules(company_id, name);
CREATE INDEX IF NOT EXISTS idx_incidents_company_time ON incidents(company_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_backups_company_time ON config_backups(company_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_logs_company_time ON automation_logs(company_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_company_hostname
    ON devices(company_id, hostname) WHERE company_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_company_ip
    ON devices(company_id, ip_address) WHERE company_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_rules_company_name
    ON rules(company_id, name) WHERE company_id IS NOT NULL;

CREATE OR REPLACE FUNCTION inherit_device_company_id()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_device_company uuid;
BEGIN
    IF NEW.device_id IS NOT NULL THEN
        SELECT company_id INTO v_device_company FROM devices WHERE id = NEW.device_id;
        IF v_device_company IS NOT NULL AND NEW.company_id IS NOT NULL
           AND v_device_company <> NEW.company_id THEN
            RAISE EXCEPTION 'device and resource belong to different companies' USING ERRCODE = '23514';
        END IF;
        IF NEW.company_id IS NULL THEN
            NEW.company_id := v_device_company;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_monitoring_logs_company ON monitoring_logs;
CREATE TRIGGER trg_monitoring_logs_company BEFORE INSERT OR UPDATE ON monitoring_logs
FOR EACH ROW EXECUTE FUNCTION inherit_device_company_id();
DROP TRIGGER IF EXISTS trg_rules_company ON rules;
CREATE TRIGGER trg_rules_company BEFORE INSERT OR UPDATE ON rules
FOR EACH ROW EXECUTE FUNCTION inherit_device_company_id();
DROP TRIGGER IF EXISTS trg_incidents_company ON incidents;
CREATE TRIGGER trg_incidents_company BEFORE INSERT OR UPDATE ON incidents
FOR EACH ROW EXECUTE FUNCTION inherit_device_company_id();
DROP TRIGGER IF EXISTS trg_backups_company ON config_backups;
CREATE TRIGGER trg_backups_company BEFORE INSERT OR UPDATE ON config_backups
FOR EACH ROW EXECUTE FUNCTION inherit_device_company_id();
DROP TRIGGER IF EXISTS trg_automation_logs_company ON automation_logs;
CREATE TRIGGER trg_automation_logs_company BEFORE INSERT OR UPDATE ON automation_logs
FOR EACH ROW EXECUTE FUNCTION inherit_device_company_id();
REVOKE ALL ON FUNCTION inherit_device_company_id() FROM PUBLIC, anon, authenticated;

ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE config_backups ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_logs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON devices, monitoring_logs, rules, incidents, config_backups, automation_logs
    FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON devices, monitoring_logs, rules, incidents,
    config_backups, automation_logs TO service_role;

-- Company Admins get read access to their own operational data plus scoped
-- user administration. Only network_operator receives operational write rights.
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON p.permission_key = ANY(ARRAY[
    'users.read', 'users.create', 'users.update', 'users.suspend',
    'roles.read', 'roles.assign', 'audit.read', 'devices.read', 'monitoring.read',
    'rules.read', 'incidents.read', 'automation.read', 'backups.read'
])
WHERE r.name = 'company_admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;

CREATE OR REPLACE FUNCTION accept_company_invitation(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_invitation company_invitations%ROWTYPE;
    v_profile profiles%ROWTYPE;
BEGIN
    SELECT * INTO v_invitation
    FROM company_invitations
    WHERE user_id = p_user_id AND status = 'pending'
    FOR UPDATE;
    IF NOT FOUND OR v_invitation.expires_at <= now() THEN
        IF FOUND THEN
            UPDATE company_invitations SET status = 'expired' WHERE id = v_invitation.id;
        END IF;
        RETURN jsonb_build_object('status', 'not_found');
    END IF;

    UPDATE profiles
    SET account_status = 'active'
    WHERE id = p_user_id
      AND company_id = v_invitation.company_id
      AND lower(email) = lower(v_invitation.email)
      AND account_status = 'pending'
      AND EXISTS (
          SELECT 1 FROM user_roles
          WHERE user_id = p_user_id AND role_id = v_invitation.role_id
      )
    RETURNING * INTO v_profile;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'invalid');
    END IF;

    UPDATE company_invitations
    SET status = 'accepted', accepted_at = now()
    WHERE id = v_invitation.id;
    RETURN jsonb_build_object('status', 'accepted', 'profile', to_jsonb(v_profile));
END;
$$;
REVOKE ALL ON FUNCTION accept_company_invitation(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION accept_company_invitation(uuid) TO service_role;

CREATE OR REPLACE FUNCTION provision_company_invitation(
    p_user_id uuid,
    p_email text,
    p_full_name text,
    p_phone_number text,
    p_invited_by uuid,
    p_role_id uuid,
    p_expires_at timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_company_id uuid;
    v_company_name text;
    v_role_name text;
    v_profile profiles%ROWTYPE;
    v_invitation company_invitations%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('netops360:invite-email:' || lower(btrim(p_email)), 0));
    SELECT p.company_id, p.company_name INTO v_company_id, v_company_name
    FROM profiles p
    WHERE p.id = p_invited_by
      AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                  WHERE ur.user_id = p_invited_by AND r.name = 'company_admin');
    IF v_company_id IS NULL THEN
        RAISE EXCEPTION 'company administrator is not authorized' USING ERRCODE = '42501';
    END IF;
    SELECT name INTO v_role_name FROM roles WHERE id = p_role_id;
    IF v_role_name NOT IN ('network_operator', 'viewer') THEN
        RAISE EXCEPTION 'role is not assignable by a company administrator' USING ERRCODE = '42501';
    END IF;
    IF p_user_id IS NULL OR p_email IS NULL OR length(btrim(p_email)) = 0
       OR p_full_name IS NULL OR length(btrim(p_full_name)) = 0
       OR p_expires_at <= now() OR p_expires_at > now() + interval '24 hours' THEN
        RAISE EXCEPTION 'invitation fields are invalid' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT 1 FROM profiles WHERE lower(email) = lower(btrim(p_email))) THEN
        RAISE EXCEPTION 'email already has a NetOps360 account' USING ERRCODE = '23505';
    END IF;

    INSERT INTO profiles (id, email, full_name, phone_number, account_status,
                          company_name, company_id, invited_by)
    VALUES (p_user_id, lower(btrim(p_email)), btrim(p_full_name), p_phone_number,
            'pending', v_company_name, v_company_id, p_invited_by)
    RETURNING * INTO v_profile;
    INSERT INTO user_roles (user_id, role_id, assigned_by)
    VALUES (p_user_id, p_role_id, p_invited_by);
    INSERT INTO company_invitations (user_id, email, full_name, company_id, role_id, invited_by, expires_at)
    VALUES (p_user_id, lower(btrim(p_email)), btrim(p_full_name), v_company_id, p_role_id, p_invited_by, p_expires_at)
    RETURNING * INTO v_invitation;
    RETURN jsonb_build_object('profile', to_jsonb(v_profile), 'invitation', to_jsonb(v_invitation));
END;
$$;
REVOKE ALL ON FUNCTION provision_company_invitation(uuid, text, text, text, uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION provision_company_invitation(uuid, text, text, text, uuid, uuid, timestamptz)
    TO service_role;

CREATE OR REPLACE FUNCTION set_audit_company_id()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NEW.company_id IS NULL THEN
        IF NEW.after_metadata ? 'company_id'
           AND NEW.after_metadata->>'company_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            NEW.company_id := (NEW.after_metadata->>'company_id')::uuid;
        ELSIF NEW.before_metadata ? 'company_id'
           AND NEW.before_metadata->>'company_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            NEW.company_id := (NEW.before_metadata->>'company_id')::uuid;
        ELSIF NEW.actor_user_id IS NOT NULL THEN
            SELECT company_id INTO NEW.company_id FROM profiles WHERE id = NEW.actor_user_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_audit_set_company_id ON audit_logs;
CREATE TRIGGER trg_audit_set_company_id BEFORE INSERT ON audit_logs
FOR EACH ROW EXECUTE FUNCTION set_audit_company_id();
REVOKE ALL ON FUNCTION set_audit_company_id() FROM PUBLIC, anon, authenticated;

INSERT INTO schema_migrations(version)
VALUES ('202611280001_company_user_invitations')
ON CONFLICT (version) DO NOTHING;
COMMIT;
