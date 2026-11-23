"""Safe, best-effort audit recording for security-relevant mutations."""
import logging

from flask import g, has_request_context, request

logger = logging.getLogger(__name__)

SAFE_FIELDS = {
    "device": ("id", "hostname", "ip_address", "device_type", "site", "monitoring_enabled",
               "monitoring_method", "monitor_interval_seconds", "is_active", "current_status"),
    "rule": ("id", "name", "metric", "operator", "threshold", "severity", "enabled",
             "scope", "device_id"),
    "incident": ("id", "device_id", "rule_id", "status", "severity", "acknowledged_at",
                 "resolved_at", "resolution_reason"),
    "backup": ("id", "device_id", "backup_type", "status", "checksum"),
    "automation": ("id", "incident_id", "device_id", "rule_id", "trigger_type", "status",
                   "execution_id", "retry_count"),
    "user": ("id", "email", "full_name", "phone_number", "account_status"),
    "user_role": ("id", "user_id", "role_id", "assigned_by"),
}


class AuditService:
    def __init__(self, repo):
        self.repo = repo

    def record(self, action, resource_type, row=None, before=None, after=None):
        fields = SAFE_FIELDS.get(resource_type, ())
        clean = lambda value: {key: value.get(key) for key in fields if key in value} if value else {}
        data = {
            "actor_id": None,  # Retained for compatibility with the original audit schema.
            "actor_user_id": (getattr(g, "auth_identity", {}) or {}).get("sub") if has_request_context() else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str((row or {}).get("id")) if (row or {}).get("id") else None,
            "description": f"{action} {resource_type}",
            "ip_address": request.remote_addr if has_request_context() else None,
            "request_id": getattr(g, "request_id", None),
            "before_metadata": clean(before),
            "after_metadata": clean(after or row),
        }
        try:
            self.repo.insert_audit_log(data)
        except Exception:
            # Keep the primary operation's outcome accurate; failures remain visible in server logs.
            logger.exception("Audit write failed for %s %s", action, resource_type)
