-- Company onboarding metadata and atomic first-user role provisioning.
BEGIN;

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS company_name text,
    ADD COLUMN IF NOT EXISTS invited_by uuid REFERENCES profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_profiles_company_name ON profiles (company_name);
CREATE INDEX IF NOT EXISTS idx_profiles_invited_by ON profiles (invited_by);

CREATE TABLE IF NOT EXISTS company_assistant_invite_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    invited_by uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    invitee_email text NOT NULL,
    company_name text,
    status text NOT NULL DEFAULT 'reserved',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT company_assistant_invite_reservation_status
        CHECK (status IN ('reserved', 'cancelled')),
    CONSTRAINT company_assistant_invite_reservation_key
        UNIQUE (invited_by, invitee_email)
);

ALTER TABLE company_assistant_invite_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON company_assistant_invite_reservations FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON company_assistant_invite_reservations TO service_role;

CREATE OR REPLACE FUNCTION provision_auth_profile(
    p_user_id uuid,
    p_email text,
    p_full_name text,
    p_company_name text,
    p_default_role text
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_profile profiles%ROWTYPE;
    v_role_name text;
    v_role_id uuid;
BEGIN
    IF p_default_role IS NULL OR p_default_role NOT IN ('admin', 'viewer') THEN
        RAISE EXCEPTION 'invalid default role' USING ERRCODE = '22023';
    END IF;
    IF p_email IS NULL OR length(btrim(p_email)) = 0
       OR p_full_name IS NULL OR length(btrim(p_full_name)) = 0 THEN
        RAISE EXCEPTION 'email and full name are required' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('netops360:auth-role-provisioning', 0));

    INSERT INTO profiles (id, email, full_name, company_name)
    VALUES (p_user_id, lower(btrim(p_email)), btrim(p_full_name), nullif(btrim(p_company_name), ''))
    ON CONFLICT (id) DO UPDATE SET
        email = lower(btrim(EXCLUDED.email)),
        full_name = btrim(EXCLUDED.full_name),
        company_name = coalesce(nullif(btrim(EXCLUDED.company_name), ''), profiles.company_name)
    RETURNING * INTO v_profile;

    SELECT r.name, r.id INTO v_role_name, v_role_id
    FROM user_roles ur
    JOIN roles r ON r.id = ur.role_id
    WHERE ur.user_id = p_user_id
    ORDER BY r.name
    LIMIT 1;

    IF v_role_id IS NULL AND v_profile.account_status = 'active' THEN
        IF EXISTS (
            SELECT 1
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name = 'super_admin'
        ) THEN
            v_role_name := p_default_role;
        ELSE
            v_role_name := 'super_admin';
        END IF;

        SELECT id INTO v_role_id FROM roles WHERE name = v_role_name;
        IF v_role_id IS NULL THEN
            RAISE EXCEPTION 'required role is not configured' USING ERRCODE = '22023';
        END IF;
        INSERT INTO user_roles (user_id, role_id, assigned_by)
        VALUES (p_user_id, v_role_id, NULL)
        ON CONFLICT (user_id, role_id) DO NOTHING;
    END IF;

    RETURN jsonb_build_object('profile', to_jsonb(v_profile), 'role', v_role_name);
END;
$$;

REVOKE ALL ON FUNCTION provision_auth_profile(uuid, text, text, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION provision_auth_profile(uuid, text, text, text, text) TO service_role;

CREATE OR REPLACE FUNCTION count_company_assistant_users(
    p_actor_id uuid,
    p_company_name text
)
RETURNS integer
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT count(*)::integer
    FROM (
        SELECT lower(p.email) AS invitee_email
        FROM profiles p
        WHERE p.id <> p_actor_id
          AND (
              p.invited_by = p_actor_id
              OR (
                  p_company_name IS NOT NULL
                  AND lower(p.company_name) = lower(p_company_name)
                  AND EXISTS (
                      SELECT 1
                      FROM user_roles ur
                      JOIN roles r ON r.id = ur.role_id
                      WHERE ur.user_id = p.id
                        AND r.name IN ('network_operator', 'viewer')
                  )
              )
          )
        UNION
        SELECT lower(reservation.invitee_email)
        FROM company_assistant_invite_reservations reservation
        WHERE reservation.status = 'reserved'
          AND (
              reservation.invited_by = p_actor_id
              OR (
                  p_company_name IS NOT NULL
                  AND lower(reservation.company_name) = lower(p_company_name)
              )
          )
    ) used_invites;
$$;

REVOKE ALL ON FUNCTION count_company_assistant_users(uuid, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION count_company_assistant_users(uuid, text) TO service_role;

CREATE OR REPLACE FUNCTION reserve_company_assistant_invite(
    p_actor_id uuid,
    p_invitee_email text,
    p_company_name text
)
RETURNS boolean
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_used_count integer;
    v_lock_key text;
BEGIN
    v_lock_key := coalesce(
        'company:' || lower(p_company_name),
        'inviter:' || p_actor_id::text
    );
    PERFORM pg_advisory_xact_lock(hashtextextended('netops360:assistant-invite:' || v_lock_key, 0));

    SELECT count(*) INTO v_used_count
    FROM (
        SELECT lower(p.email) AS invitee_email
        FROM profiles p
        WHERE p.id <> p_actor_id
          AND (
              p.invited_by = p_actor_id
              OR (
                  p_company_name IS NOT NULL
                  AND lower(p.company_name) = lower(p_company_name)
                  AND EXISTS (
                      SELECT 1
                      FROM user_roles ur
                      JOIN roles r ON r.id = ur.role_id
                      WHERE ur.user_id = p.id
                        AND r.name IN ('network_operator', 'viewer')
                  )
              )
          )
        UNION
        SELECT lower(reservation.invitee_email)
        FROM company_assistant_invite_reservations reservation
        WHERE reservation.status = 'reserved'
          AND (
              reservation.invited_by = p_actor_id
              OR (
                  p_company_name IS NOT NULL
                  AND lower(reservation.company_name) = lower(p_company_name)
              )
          )
    ) used_invites;

    IF v_used_count >= 1 THEN
        RETURN false;
    END IF;

    INSERT INTO company_assistant_invite_reservations (
        invited_by, invitee_email, company_name, status
    )
    VALUES (p_actor_id, lower(btrim(p_invitee_email)), p_company_name, 'reserved')
    ON CONFLICT (invited_by, invitee_email) DO UPDATE SET
        company_name = EXCLUDED.company_name,
        status = 'reserved',
        created_at = now();
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION cancel_company_assistant_invite(
    p_actor_id uuid,
    p_invitee_email text
)
RETURNS void
LANGUAGE sql
SET search_path = public, pg_temp
AS $$
    UPDATE company_assistant_invite_reservations
    SET status = 'cancelled'
    WHERE invited_by = p_actor_id
      AND invitee_email = lower(btrim(p_invitee_email))
      AND status = 'reserved';
$$;

REVOKE ALL ON FUNCTION reserve_company_assistant_invite(uuid, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION reserve_company_assistant_invite(uuid, text, text) TO service_role;
REVOKE ALL ON FUNCTION cancel_company_assistant_invite(uuid, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION cancel_company_assistant_invite(uuid, text) TO service_role;

INSERT INTO schema_migrations(version)
VALUES ('202611270001_company_auth_onboarding')
ON CONFLICT (version) DO NOTHING;

COMMIT;
