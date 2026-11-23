-- Additive migration: audit log and migration version tracking.
-- Apply after the six core tables exist. Existing application rows are untouched.
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    request_id text,
    before_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT audit_action_nonempty CHECK (length(btrim(action)) > 0),
    CONSTRAINT audit_resource_nonempty CHECK (length(btrim(resource_type)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_audit_resource_time
    ON audit_logs (resource_type, resource_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_request_id
    ON audit_logs (request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_actor_time
    ON audit_logs (actor_id, occurred_at DESC) WHERE actor_id IS NOT NULL;

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
-- No anon/authenticated policies. Only the backend service role accesses audit data.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT SELECT, INSERT ON TABLE audit_logs TO service_role;
    END IF;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('202611230001_audit_logs')
ON CONFLICT (version) DO NOTHING;
COMMIT;

-- Rollback: DROP TABLE audit_logs; DELETE FROM schema_migrations
-- WHERE version = '202611230001_audit_logs';
-- Preserve schema_migrations while any other migration versions are recorded.
