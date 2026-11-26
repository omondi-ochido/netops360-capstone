-- =====================================================================
-- NetOps360 database schema (Supabase / PostgreSQL 14+)
-- Repeatable: safe to run more than once (CREATE ... IF NOT EXISTS).
-- NOTE: IF NOT EXISTS will not alter a table that already exists with a
-- different shape. For schema changes after first deploy, add migrations.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Shared trigger function: keep updated_at current
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------
-- 1. devices
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname                 text NOT NULL,
    ip_address               inet NOT NULL,
    device_type              text NOT NULL,
    operating_system         text,
    site                     text NOT NULL DEFAULT 'main-site',
    description              text,
    ssh_enabled              boolean NOT NULL DEFAULT false,
    monitoring_enabled       boolean NOT NULL DEFAULT true,
    monitoring_method        text NOT NULL DEFAULT 'icmp',
    monitor_interval_seconds integer NOT NULL DEFAULT 5,
    current_status           text NOT NULL DEFAULT 'Unknown',
    last_latency_ms          numeric(10,3),
    last_packet_loss         numeric(5,2),
    last_checked_at          timestamptz,
    last_seen_at             timestamptz,
    is_active                boolean NOT NULL DEFAULT true,   -- soft delete flag
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT devices_hostname_key UNIQUE (hostname),
    CONSTRAINT devices_ip_address_key UNIQUE (ip_address),
    CONSTRAINT devices_hostname_format CHECK (hostname ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'),
    -- inet also accepts CIDR ranges; require a single host address
    CONSTRAINT devices_ip_is_host CHECK (
        masklen(ip_address) = CASE family(ip_address) WHEN 4 THEN 32 ELSE 128 END
    ),
    CONSTRAINT devices_type_valid CHECK (
        device_type IN ('router','switch','server','host','firewall','access_point','other')
    ),
    CONSTRAINT devices_method_valid CHECK (monitoring_method IN ('icmp','tcp','snmp','none')),
    CONSTRAINT devices_interval_valid CHECK (monitor_interval_seconds BETWEEN 5 AND 3600),
    CONSTRAINT devices_status_valid CHECK (
        current_status IN ('Online','Offline','Warning','Unknown','Unmonitored')
    ),
    CONSTRAINT devices_latency_valid CHECK (last_latency_ms IS NULL OR last_latency_ms >= 0),
    CONSTRAINT devices_loss_valid CHECK (
        last_packet_loss IS NULL OR last_packet_loss BETWEEN 0 AND 100
    ),
    -- a device with no monitoring method cannot have monitoring enabled
    CONSTRAINT devices_monitoring_consistent CHECK (
        NOT (monitoring_method = 'none' AND monitoring_enabled)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_hostname_lower ON devices (lower(hostname));
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices (current_status);
CREATE INDEX IF NOT EXISTS idx_devices_monitoring ON devices (monitoring_enabled) WHERE is_active;

DROP TRIGGER IF EXISTS trg_devices_updated_at ON devices;
CREATE TRIGGER trg_devices_updated_at BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- 2. monitoring_logs  (append-only history; never deleted with a device)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_logs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id        uuid NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
    status           text NOT NULL,
    latency_ms       numeric(10,3),
    packet_loss      numeric(5,2),
    checked_at       timestamptz NOT NULL DEFAULT now(),
    check_type       text NOT NULL DEFAULT 'icmp',
    packets_sent     integer,
    packets_received integer,
    error_message    text,
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT monlogs_status_valid CHECK (
        status IN ('Online','Offline','Warning','Unknown','Unmonitored')
    ),
    CONSTRAINT monlogs_check_type_valid CHECK (check_type IN ('icmp','tcp','snmp','manual')),
    CONSTRAINT monlogs_latency_valid CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CONSTRAINT monlogs_loss_valid CHECK (packet_loss IS NULL OR packet_loss BETWEEN 0 AND 100),
    CONSTRAINT monlogs_packets_valid CHECK (
        (packets_sent IS NULL OR packets_sent >= 0)
        AND (packets_received IS NULL OR packets_received >= 0)
        AND (packets_sent IS NULL OR packets_received IS NULL OR packets_received <= packets_sent)
    )
);

CREATE INDEX IF NOT EXISTS idx_monlogs_device_time ON monitoring_logs (device_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_monlogs_time ON monitoring_logs (checked_at DESC);

-- ---------------------------------------------------------------------
-- 3. rules  (declarative only; no expressions are ever executed)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    description text,
    metric      text NOT NULL,
    operator    text NOT NULL,
    threshold   jsonb NOT NULL,        -- string for device_status, number otherwise
    severity    text NOT NULL,
    enabled     boolean NOT NULL DEFAULT true,
    scope       text NOT NULL DEFAULT 'global',
    device_id   uuid REFERENCES devices(id) ON DELETE CASCADE,  -- for scope = 'device'
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT rules_name_key UNIQUE (name),
    CONSTRAINT rules_metric_valid CHECK (metric IN ('device_status','latency_ms','packet_loss')),
    CONSTRAINT rules_operator_valid CHECK (operator IN ('eq','neq','gt','gte','lt','lte')),
    CONSTRAINT rules_severity_valid CHECK (severity IN ('info','warning','critical')),
    CONSTRAINT rules_scope_valid CHECK (
        (scope = 'global' AND device_id IS NULL) OR (scope = 'device' AND device_id IS NOT NULL)
    ),
    -- CASE guarantees evaluation order, so casts are only attempted on numbers
    CONSTRAINT rules_threshold_valid CHECK (
        CASE metric
            WHEN 'device_status' THEN
                CASE WHEN jsonb_typeof(threshold) = 'string'
                     THEN operator IN ('eq','neq')
                          AND (threshold #>> '{}') IN ('Online','Offline','Warning','Unknown','Unmonitored')
                     ELSE false END
            WHEN 'latency_ms' THEN
                CASE WHEN jsonb_typeof(threshold) = 'number'
                     THEN (threshold #>> '{}')::numeric >= 0
                     ELSE false END
            WHEN 'packet_loss' THEN
                CASE WHEN jsonb_typeof(threshold) = 'number'
                     THEN (threshold #>> '{}')::numeric BETWEEN 0 AND 100
                     ELSE false END
            ELSE false
        END
    )
);

CREATE INDEX IF NOT EXISTS idx_rules_enabled ON rules (enabled);

DROP TRIGGER IF EXISTS trg_rules_updated_at ON rules;
CREATE TRIGGER trg_rules_updated_at BEFORE UPDATE ON rules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- 4. incidents
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id        uuid NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
    rule_id          uuid NOT NULL REFERENCES rules(id) ON DELETE RESTRICT,
    title            text NOT NULL,
    description      text,
    severity         text NOT NULL,
    status           text NOT NULL DEFAULT 'open',
    triggered_at     timestamptz NOT NULL DEFAULT now(),
    resolved_at      timestamptz,
    acknowledged_at  timestamptz,
    last_observed_at timestamptz NOT NULL DEFAULT now(),
    trigger_metric   text,
    trigger_value    jsonb,
    resolution_value jsonb,
    duration_seconds integer,
    resolution_reason text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT incidents_severity_valid CHECK (severity IN ('info','warning','critical')),
    CONSTRAINT incidents_status_valid CHECK (status IN ('open','acknowledged','resolved')),
    CONSTRAINT incidents_resolved_consistent CHECK ((status = 'resolved') = (resolved_at IS NOT NULL)),
    CONSTRAINT incidents_duration_valid CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

-- Database-level duplicate prevention: one active incident per device + rule
CREATE UNIQUE INDEX IF NOT EXISTS uq_incidents_active_device_rule
    ON incidents (device_id, rule_id)
    WHERE status IN ('open','acknowledged');

CREATE INDEX IF NOT EXISTS idx_incidents_status_time ON incidents (status, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_device_time ON incidents (device_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents (severity);

DROP TRIGGER IF EXISTS trg_incidents_updated_at ON incidents;
CREATE TRIGGER trg_incidents_updated_at BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- 5. config_backups
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config_backups (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id           uuid NOT NULL REFERENCES devices(id) ON DELETE RESTRICT,
    configuration       text,
    interfaces_snapshot text,
    backup_type         text NOT NULL DEFAULT 'manual',
    status              text NOT NULL,
    checksum            text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    error_message       text,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT backups_type_valid CHECK (backup_type IN ('manual','scheduled','incident_triggered')),
    CONSTRAINT backups_status_valid CHECK (status IN ('success','failed')),
    CONSTRAINT backups_checksum_format CHECK (checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'),
    -- a successful backup can never carry an empty configuration
    CONSTRAINT backups_success_has_config CHECK (
        status <> 'success'
        OR (configuration IS NOT NULL AND length(btrim(configuration)) > 0 AND checksum IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_backups_device_time ON config_backups (device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backups_device_checksum ON config_backups (device_id, checksum);

-- ---------------------------------------------------------------------
-- 6. automation_logs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS automation_logs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_name    text NOT NULL,
    trigger_type     text NOT NULL,          -- e.g. incident.opened
    incident_id      uuid REFERENCES incidents(id) ON DELETE SET NULL,
    device_id        uuid REFERENCES devices(id) ON DELETE RESTRICT,
    rule_id          uuid REFERENCES rules(id) ON DELETE SET NULL,
    execution_id     text,
    status           text NOT NULL DEFAULT 'pending',
    request_payload  jsonb,
    response_payload jsonb,
    started_at       timestamptz,
    completed_at     timestamptz,
    error_message    text,
    retry_count      integer NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT autologs_status_valid CHECK (status IN ('pending','running','success','failed')),
    CONSTRAINT autologs_retry_valid CHECK (retry_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_autologs_status_time ON automation_logs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_autologs_incident ON automation_logs (incident_id, trigger_type);
CREATE INDEX IF NOT EXISTS idx_autologs_device ON automation_logs (device_id);

-- ---------------------------------------------------------------------
-- Atomic incident functions (called by the backend through supabase.rpc)
-- ---------------------------------------------------------------------

-- Opens an incident, or touches last_observed_at on the existing active one.
-- Returns (incident, created). created = true only for a brand-new incident,
-- so callers fire "incident.opened" exactly once.
CREATE OR REPLACE FUNCTION open_incident(
    p_device_id      uuid,
    p_rule_id        uuid,
    p_title          text,
    p_description    text,
    p_severity       text,
    p_trigger_metric text,
    p_trigger_value  jsonb
)
RETURNS TABLE (incident jsonb, created boolean)
LANGUAGE plpgsql
AS $$
DECLARE
    v_row incidents%ROWTYPE;
BEGIN
    INSERT INTO incidents (device_id, rule_id, title, description, severity,
                           trigger_metric, trigger_value)
    VALUES (p_device_id, p_rule_id, p_title, p_description, p_severity,
            p_trigger_metric, p_trigger_value)
    ON CONFLICT (device_id, rule_id) WHERE status IN ('open','acknowledged') DO NOTHING
    RETURNING * INTO v_row;

    IF FOUND THEN
        RETURN QUERY SELECT to_jsonb(v_row), true;
        RETURN;
    END IF;

    UPDATE incidents
       SET last_observed_at = now()
     WHERE device_id = p_device_id
       AND rule_id = p_rule_id
       AND status IN ('open','acknowledged')
    RETURNING * INTO v_row;

    RETURN QUERY SELECT to_jsonb(v_row), false;
END;
$$;

-- Resolves an active incident atomically. No-op on already-resolved incidents.
-- Returns (incident, changed).
CREATE OR REPLACE FUNCTION resolve_incident(
    p_incident_id      uuid,
    p_resolution_value jsonb,
    p_reason           text
)
RETURNS TABLE (incident jsonb, changed boolean)
LANGUAGE plpgsql
AS $$
DECLARE
    v_row incidents%ROWTYPE;
BEGIN
    UPDATE incidents
       SET status = 'resolved',
           resolved_at = now(),
           resolution_value = p_resolution_value,
           resolution_reason = p_reason,
           last_observed_at = now(),
           duration_seconds = GREATEST(0, EXTRACT(EPOCH FROM (now() - triggered_at))::integer)
     WHERE id = p_incident_id
       AND status IN ('open','acknowledged')
    RETURNING * INTO v_row;

    IF FOUND THEN
        RETURN QUERY SELECT to_jsonb(v_row), true;
        RETURN;
    END IF;

    SELECT * INTO v_row FROM incidents WHERE id = p_incident_id;
    IF FOUND THEN
        RETURN QUERY SELECT to_jsonb(v_row), false;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- Row Level Security
-- RLS is enabled with NO policies for anon/authenticated roles, so the
-- public (anon) key can read or write nothing. Only the backend, using the
-- server-side service-role key (which bypasses RLS), can access the data.
-- Config backups contain sensitive device configuration.
-- ---------------------------------------------------------------------
ALTER TABLE devices         ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules           ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents       ENABLE ROW LEVEL SECURITY;
ALTER TABLE config_backups  ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_logs ENABLE ROW LEVEL SECURITY;

-- Lock the RPC functions down to the service role (Supabase roles only).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        REVOKE ALL ON FUNCTION open_incident(uuid, uuid, text, text, text, text, jsonb)
            FROM PUBLIC, anon, authenticated;
        REVOKE ALL ON FUNCTION resolve_incident(uuid, jsonb, text)
            FROM PUBLIC, anon, authenticated;
        GRANT EXECUTE ON FUNCTION open_incident(uuid, uuid, text, text, text, text, jsonb)
            TO service_role;
        GRANT EXECUTE ON FUNCTION resolve_incident(uuid, jsonb, text) TO service_role;
    END IF;
END;
$$;
