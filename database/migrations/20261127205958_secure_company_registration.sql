-- Atomic company claim for newly authenticated Supabase users.
-- Existing profiles and operational rows are intentionally left unassigned for
-- an operator-reviewed ownership backfill.
BEGIN;

CREATE OR REPLACE FUNCTION normalize_company_name(p_name text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $$
    SELECT lower(btrim(regexp_replace(p_name, '[[:space:]]+', ' ', 'g')));
$$;

REVOKE ALL ON FUNCTION normalize_company_name(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION normalize_company_name(text) TO service_role;

CREATE TABLE companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name text NOT NULL,
    normalized_company_name text GENERATED ALWAYS AS
        (normalize_company_name(company_name)) STORED,
    registration_status text NOT NULL DEFAULT 'active',
    initial_admin_id uuid NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT companies_name_nonempty CHECK (length(normalized_company_name) > 0),
    CONSTRAINT companies_registration_status_valid
        CHECK (registration_status IN ('active', 'suspended')),
    CONSTRAINT companies_normalized_name_unique UNIQUE (normalized_company_name)
);

ALTER TABLE profiles
    ADD COLUMN company_id uuid REFERENCES companies(id) ON DELETE RESTRICT;
CREATE INDEX idx_profiles_company_id ON profiles(company_id) WHERE company_id IS NOT NULL;
CREATE INDEX idx_companies_registration_status ON companies(registration_status);

CREATE OR REPLACE FUNCTION set_company_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_companies_updated_at BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_company_updated_at();

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON companies FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON companies TO service_role;
REVOKE ALL ON FUNCTION set_company_updated_at() FROM PUBLIC, anon, authenticated;

-- Add a company-specific role without changing or reassigning existing roles.
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_name_valid;
ALTER TABLE roles ADD CONSTRAINT roles_name_valid
    CHECK (name IN ('super_admin', 'admin', 'company_admin', 'network_operator', 'viewer'));
INSERT INTO roles(name, description)
VALUES ('company_admin', 'Initial administrator for one registered company.')
ON CONFLICT (name) DO NOTHING;

-- The prior migration's global first-user provisioning function could assign
-- Super Admin/Admin based on signup order. Retain it for rollback inspection,
-- but prevent application credentials from invoking it.
REVOKE EXECUTE ON FUNCTION provision_auth_profile(uuid, text, text, text, text)
    FROM service_role;

-- Do not copy the legacy global-admin permissions. The new role remains
-- unprivileged until company-scoped APIs/RLS have been implemented and tested.

CREATE OR REPLACE FUNCTION register_company_with_initial_admin(
    p_user_id uuid,
    p_email text,
    p_full_name text,
    p_company_name text
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_email text := lower(btrim(p_email));
    v_full_name text := btrim(p_full_name);
    v_company_name text := btrim(regexp_replace(p_company_name, '[[:space:]]+', ' ', 'g'));
    v_normalized_name text := normalize_company_name(p_company_name);
    v_company companies%ROWTYPE;
    v_profile profiles%ROWTYPE;
    v_company_admin_role uuid;
BEGIN
    IF p_user_id IS NULL OR p_email IS NULL OR v_email IS NULL OR length(v_email) = 0
       OR v_full_name IS NULL OR length(v_full_name) = 0
       OR p_company_name IS NULL OR v_company_name IS NULL OR length(v_normalized_name) = 0 THEN
        RAISE EXCEPTION 'registration fields are required' USING ERRCODE = '22023';
    END IF;
    IF length(v_email) > 254 OR length(v_full_name) > 120 OR length(v_company_name) > 150 THEN
        RAISE EXCEPTION 'registration field exceeds maximum length' USING ERRCODE = '22023';
    END IF;

    -- Serialize same-name claims. The unique constraint remains the final guard.
    PERFORM pg_advisory_xact_lock(hashtextextended('netops360:company:' || v_normalized_name, 0));

    SELECT * INTO v_company FROM companies
    WHERE normalized_company_name = v_normalized_name
    LIMIT 1;
    IF FOUND THEN
        RETURN jsonb_build_object('status', 'company_exists');
    END IF;

    -- Never turn a legacy, invited, or previously onboarded profile into a
    -- registrant. Those identities need explicit operator/company review.
    IF EXISTS (SELECT 1 FROM profiles WHERE id = p_user_id)
       OR EXISTS (SELECT 1 FROM profiles WHERE lower(email) = v_email) THEN
        RETURN jsonb_build_object('status', 'existing_account');
    END IF;

    SELECT id INTO v_company_admin_role FROM roles WHERE name = 'company_admin';
    IF v_company_admin_role IS NULL THEN
        RAISE EXCEPTION 'company_admin role is not configured' USING ERRCODE = '22023';
    END IF;

    INSERT INTO profiles (id, email, full_name, account_status, company_name)
    VALUES (p_user_id, v_email, v_full_name, 'active', v_company_name)
    RETURNING * INTO v_profile;

    INSERT INTO companies (company_name, registration_status, initial_admin_id)
    VALUES (v_company_name, 'active', p_user_id)
    RETURNING * INTO v_company;

    UPDATE profiles SET company_id = v_company.id WHERE id = p_user_id
    RETURNING * INTO v_profile;

    INSERT INTO user_roles (user_id, role_id, assigned_by)
    VALUES (p_user_id, v_company_admin_role, p_user_id);

    INSERT INTO audit_logs (
        actor_user_id, action, resource_type, resource_id, description,
        before_metadata, after_metadata
    ) VALUES (
        p_user_id, 'company_registered', 'company', v_company.id::text,
        'Company registered and initial Company Admin assigned.', '{}'::jsonb,
        jsonb_build_object('company_id', v_company.id,
                           'company_name', v_company.company_name,
                           'initial_admin_id', p_user_id,
                           'role', 'company_admin')
    );

    RETURN jsonb_build_object(
        'status', 'registered',
        'company', to_jsonb(v_company),
        'profile', to_jsonb(v_profile),
        'roles', jsonb_build_array('company_admin')
    );
END;
$$;

REVOKE ALL ON FUNCTION register_company_with_initial_admin(uuid, text, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION register_company_with_initial_admin(uuid, text, text, text)
    TO service_role;

INSERT INTO schema_migrations(version)
VALUES ('20261127205958_secure_company_registration')
ON CONFLICT (version) DO NOTHING;

COMMIT;
