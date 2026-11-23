"""Supabase (PostgREST) implementation of the repository interface.

All access goes through the supabase-py query builder or RPC with bound
parameters - no SQL string is ever assembled from request data.
Raw database errors are logged (sanitised) and converted to safe AppErrors.
"""
import logging

from app.models.constants import ACTIVE_INCIDENT_STATUSES
from app.utils.exceptions import ConflictError, DatabaseError, ValidationError
from app.utils.timeutil import now_iso

try:  # postgrest ships with supabase-py
    from postgrest.exceptions import APIError
except ImportError:  # pragma: no cover
    class APIError(Exception):
        pass

logger = logging.getLogger(__name__)

BACKUP_META_COLUMNS = (
    "id,device_id,backup_type,status,checksum,created_at,completed_at,error_message,metadata"
)


def _execute(builder):
    try:
        return builder.execute()
    except APIError as exc:
        code = str(getattr(exc, "code", "") or "")
        message = str(getattr(exc, "message", "") or "")[:200]
        logger.error("Supabase API error code=%s message=%s", code, message)
        if code == "23505":
            raise ConflictError("A record with the same unique value already exists.") from None
        if code == "23503":
            raise ConflictError("The record is referenced by, or refers to, other records.") from None
        if code in ("23514", "23502", "22P02", "22023", "22007", "22003"):
            raise ValidationError("The data violates a database constraint.") from None
        raise DatabaseError() from None
    except Exception as exc:  # network errors, timeouts, bad credentials, ...
        logger.error("Supabase request failed: %s", type(exc).__name__)
        raise DatabaseError() from None


def _first(response):
    data = response.data
    return data[0] if data else None


def _rpc_row(response):
    data = response.data
    if isinstance(data, list):
        return data[0] if data else None
    return data


class SupabaseRepository:
    def __init__(self, client):
        self.client = client

    def _t(self, name):
        return self.client.table(name)

    def insert_audit_log(self, data):
        return _first(_execute(self._t("audit_logs").insert(data)))

    # ------------------------------------------------------------------ health
    def ping(self):
        _execute(self._t("rules").select("id").limit(1))
        return True

    # ----------------------------------------------------------------- devices
    def list_devices(self, include_inactive=False, monitoring_enabled=None, status=None,
                     limit=None, offset=0):
        q = self._t("devices").select("*")
        if not include_inactive:
            q = q.eq("is_active", True)
        if monitoring_enabled is not None:
            q = q.eq("monitoring_enabled", monitoring_enabled)
        if status is not None:
            q = q.eq("current_status", status)
        q = q.order("hostname")
        if limit is not None:
            q = q.range(offset, offset + limit - 1)
        return _execute(q).data

    def get_device(self, device_id):
        return _first(_execute(self._t("devices").select("*").eq("id", str(device_id)).limit(1)))

    def get_device_by_hostname(self, hostname):
        # ilike with an escaped literal gives case-insensitive equality
        escaped = str(hostname).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return _first(_execute(self._t("devices").select("*").ilike("hostname", escaped).limit(1)))

    def create_device(self, data):
        return _first(_execute(self._t("devices").insert(data)))

    def update_device(self, device_id, data):
        return _first(_execute(self._t("devices").update(data).eq("id", str(device_id))))

    # ------------------------------------------------------- monitoring logs
    def insert_monitoring_log(self, data):
        return _first(_execute(self._t("monitoring_logs").insert(data)))

    def list_monitoring_logs(self, device_id=None, status=None, since=None, until=None,
                             limit=50, offset=0):
        q = self._t("monitoring_logs").select("*")
        if device_id:
            q = q.eq("device_id", device_id)
        if status:
            q = q.eq("status", status)
        if since:
            q = q.gte("checked_at", since)
        if until:
            q = q.lte("checked_at", until)
        q = q.order("checked_at", desc=True).range(offset, offset + limit - 1)
        return _execute(q).data

    # ------------------------------------------------------------------ rules
    def list_rules(self, enabled_only=False, limit=None, offset=0):
        q = self._t("rules").select("*")
        if enabled_only:
            q = q.eq("enabled", True)
        q = q.order("name")
        if limit is not None:
            q = q.range(offset, offset + limit - 1)
        return _execute(q).data

    def get_rule(self, rule_id):
        return _first(_execute(self._t("rules").select("*").eq("id", str(rule_id)).limit(1)))

    def create_rule(self, data):
        return _first(_execute(self._t("rules").insert(data)))

    def update_rule(self, rule_id, data):
        return _first(_execute(self._t("rules").update(data).eq("id", str(rule_id))))

    def delete_rule(self, rule_id):
        return bool(_execute(self._t("rules").delete().eq("id", str(rule_id))).data)

    def rule_has_incidents(self, rule_id):
        res = _execute(self._t("incidents").select("id").eq("rule_id", str(rule_id)).limit(1))
        return bool(res.data)

    # -------------------------------------------------------------- incidents
    def open_incident(self, device_id, rule_id, title, description, severity,
                      trigger_metric, trigger_value):
        res = _execute(self.client.rpc("open_incident", {
            "p_device_id": device_id, "p_rule_id": rule_id, "p_title": title,
            "p_description": description, "p_severity": severity,
            "p_trigger_metric": trigger_metric, "p_trigger_value": trigger_value,
        }))
        row = _rpc_row(res)
        if not row or not row.get("incident"):
            raise DatabaseError()
        return row["incident"], bool(row["created"])

    def resolve_incident(self, incident_id, resolution_value, reason):
        res = _execute(self.client.rpc("resolve_incident", {
            "p_incident_id": str(incident_id), "p_resolution_value": resolution_value,
            "p_reason": reason,
        }))
        row = _rpc_row(res)
        if not row or not row.get("incident"):
            return None, False
        return row["incident"], bool(row["changed"])

    def acknowledge_incident(self, incident_id):
        now = now_iso()
        res = _execute(
            self._t("incidents")
            .update({"status": "acknowledged", "acknowledged_at": now})
            .eq("id", str(incident_id))
            .eq("status", "open")  # atomic: only an open incident can be acknowledged
        )
        row = _first(res)
        if row:
            return row, True
        return self.get_incident(incident_id), False

    def find_active_incident(self, device_id, rule_id):
        q = (self._t("incidents").select("*").eq("device_id", device_id).eq("rule_id", rule_id)
             .in_("status", list(ACTIVE_INCIDENT_STATUSES)).limit(1))
        return _first(_execute(q))

    def get_incident(self, incident_id):
        return _first(_execute(self._t("incidents").select("*").eq("id", str(incident_id)).limit(1)))

    def list_incidents(self, status=None, severity=None, device_id=None, rule_id=None,
                       active_only=False, limit=50, offset=0):
        q = self._t("incidents").select("*")
        if status:
            q = q.eq("status", status)
        if severity:
            q = q.eq("severity", severity)
        if device_id:
            q = q.eq("device_id", device_id)
        if rule_id:
            q = q.eq("rule_id", rule_id)
        if active_only:
            q = q.in_("status", list(ACTIVE_INCIDENT_STATUSES))
        q = q.order("triggered_at", desc=True).range(offset, offset + limit - 1)
        return _execute(q).data

    # ---------------------------------------------------------------- backups
    def insert_backup(self, data):
        if data.get("status") == "success" and not (data.get("configuration") or "").strip():
            raise ValidationError("A successful backup cannot have an empty configuration.")
        return _first(_execute(self._t("config_backups").insert(data)))

    def list_backups(self, device_id=None, status=None, limit=50, offset=0):
        q = self._t("config_backups").select(BACKUP_META_COLUMNS)
        if device_id:
            q = q.eq("device_id", device_id)
        if status:
            q = q.eq("status", status)
        q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
        return _execute(q).data

    def get_backup(self, backup_id):
        return _first(_execute(self._t("config_backups").select("*").eq("id", str(backup_id)).limit(1)))

    def latest_successful_backup(self, device_id):
        q = (self._t("config_backups").select(BACKUP_META_COLUMNS).eq("device_id", device_id)
             .eq("status", "success").order("created_at", desc=True).limit(1))
        return _first(_execute(q))

    # ------------------------------------------------------- automation logs
    def insert_automation_log(self, data):
        return _first(_execute(self._t("automation_logs").insert(data)))

    def update_automation_log(self, log_id, data):
        return _first(_execute(self._t("automation_logs").update(data).eq("id", str(log_id))))

    def get_automation_log(self, log_id):
        return _first(_execute(self._t("automation_logs").select("*").eq("id", str(log_id)).limit(1)))

    def list_automation_logs(self, status=None, incident_id=None, device_id=None,
                             limit=50, offset=0):
        q = self._t("automation_logs").select("*")
        if status:
            q = q.eq("status", status)
        if incident_id:
            q = q.eq("incident_id", incident_id)
        if device_id:
            q = q.eq("device_id", device_id)
        q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
        return _execute(q).data

    def find_automation_log(self, incident_id, trigger_type):
        q = (self._t("automation_logs").select("*").eq("incident_id", incident_id)
             .eq("trigger_type", trigger_type).limit(1))
        return _first(_execute(q))

    def list_retryable_automation_logs(self, max_retries):
        q = (self._t("automation_logs").select("*").in_("status", ["failed", "pending"])
             .lt("retry_count", max_retries).order("created_at").limit(100))
        return _execute(q).data
