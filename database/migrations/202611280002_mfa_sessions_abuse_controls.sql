-- MFA/session cutoff support and durable auth-operation rate limits.
BEGIN;

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sessions_revoked_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_profiles_session_cutoff
    ON profiles (sessions_revoked_at) WHERE sessions_revoked_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    bucket_key text PRIMARY KEY,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE auth_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON auth_rate_limits FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_rate_limits TO service_role;

CREATE OR REPLACE FUNCTION consume_auth_rate_limit(
    p_bucket_key text,
    p_limit integer,
    p_window_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count integer;
BEGIN
    IF p_bucket_key IS NULL OR p_bucket_key !~ '^[0-9a-f]{64}$'
       OR p_limit < 1 OR p_limit > 1000
       OR p_window_seconds < 1 OR p_window_seconds > 86400 THEN
        RAISE EXCEPTION 'invalid auth rate limit parameters' USING ERRCODE = '22023';
    END IF;

    INSERT INTO auth_rate_limits(bucket_key, window_started_at, request_count, updated_at)
    VALUES (p_bucket_key, now(), 1, now())
    ON CONFLICT (bucket_key) DO UPDATE SET
        request_count = CASE
            WHEN auth_rate_limits.window_started_at + make_interval(secs => p_window_seconds) <= now()
                THEN 1
            ELSE auth_rate_limits.request_count + 1
        END,
        window_started_at = CASE
            WHEN auth_rate_limits.window_started_at + make_interval(secs => p_window_seconds) <= now()
                THEN now()
            ELSE auth_rate_limits.window_started_at
        END,
        updated_at = now()
    RETURNING request_count INTO v_count;
    RETURN v_count <= p_limit;
END;
$$;
REVOKE ALL ON FUNCTION consume_auth_rate_limit(text, integer, integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION consume_auth_rate_limit(text, integer, integer) TO service_role;

CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_login_once_per_session
    ON audit_logs (actor_user_id, resource_id)
    WHERE action = 'login_succeeded' AND actor_user_id IS NOT NULL;

INSERT INTO schema_migrations(version)
VALUES ('202611280002_mfa_sessions_abuse_controls')
ON CONFLICT (version) DO NOTHING;
COMMIT;
