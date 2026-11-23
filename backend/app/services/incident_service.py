"""Incident lifecycle: open -> (acknowledged) -> resolved. Duplicates are prevented
atomically in the database (partial unique index + open_incident RPC)."""
import logging

from app.models.constants import INCIDENT_STATUSES, RULE_SEVERITIES
from app.services.rule_engine import OPERATOR_SYMBOLS
from app.utils.exceptions import ConflictError, NotFoundError
from app.utils.validators import validate_choice, validate_uuid

logger = logging.getLogger(__name__)


class IncidentService:
    def __init__(self, repo, automation=None):
        self.repo = repo
        self.automation = automation
        self.on_opened = []  # callables(incident, device, rule); failures are isolated

    # ---------------------------------------------------------------- lifecycle
    def open_incident(self, device, rule, actual):
        """Open (or touch) the active incident for device+rule. Returns (incident, created)."""
        symbol = OPERATOR_SYMBOLS.get(rule["operator"], rule["operator"])
        title = f"{rule['name']}: {device['hostname']}"
        description = (f"{rule['metric']} {symbol} {rule['threshold']} on {device['hostname']} "
                       f"({device['ip_address']}); observed {actual}.")
        incident, created = self.repo.open_incident(
            device["id"], rule["id"], title, description, rule["severity"],
            rule["metric"], actual,
        )
        if created:
            logger.info("Incident opened: %s", title)
            self._notify("incident.opened", incident, device, rule)
            for hook in self.on_opened:
                try:
                    hook(incident, device, rule)
                except Exception:
                    logger.exception("Post-open hook failed")
        return incident, created

    def resolve_for_rule(self, device, rule, actual, reason):
        """Resolve ONLY the active incident for this exact device+rule (if any)."""
        active = self.repo.find_active_incident(device["id"], rule["id"])
        if not active:
            return None
        incident, changed = self.repo.resolve_incident(active["id"], actual, reason)
        if changed:
            logger.info("Incident resolved: %s", incident.get("title"))
            self._notify("incident.resolved", incident, device, rule)
            return incident
        return None

    def acknowledge(self, incident_id):
        incident = self._get(incident_id)
        if incident["status"] == "resolved":
            raise ConflictError("A resolved incident cannot be acknowledged.")
        updated, changed = self.repo.acknowledge_incident(incident["id"])
        if changed:
            self._notify("incident.acknowledged", updated)
        return updated

    def resolve(self, incident_id, reason="manually resolved"):
        incident = self._get(incident_id)
        updated, changed = self.repo.resolve_incident(incident["id"], None, reason)
        if updated is None:
            raise NotFoundError("Incident not found.")
        if changed:
            self._notify("incident.resolved", updated)
        return updated

    # ---------------------------------------------------------------- queries
    def _get(self, incident_id):
        incident = self.repo.get_incident(validate_uuid(incident_id, "incident_id"))
        if incident is None:
            raise NotFoundError("Incident not found.")
        return incident

    def get(self, incident_id):
        return self._get(incident_id)

    def list(self, status=None, severity=None, device_id=None, rule_id=None,
             active_only=False, limit=50, offset=0):
        if status:
            validate_choice(status, INCIDENT_STATUSES, "status")
        if severity:
            validate_choice(severity, RULE_SEVERITIES, "severity")
        return self.repo.list_incidents(status=status, severity=severity, device_id=device_id,
                                        rule_id=rule_id, active_only=active_only,
                                        limit=limit, offset=offset)

    def active(self, limit=200):
        return self.repo.list_incidents(active_only=True, limit=limit)

    # ---------------------------------------------------------------- internals
    def _notify(self, event, incident, device=None, rule=None):
        """Never lets an automation problem affect incident handling."""
        if self.automation is None:
            return
        try:
            device = device or self.repo.get_device(incident["device_id"])
            rule = rule or self.repo.get_rule(incident["rule_id"])
            self.automation.notify(event, incident, device, rule)
        except Exception:
            logger.exception("Automation notification failed for incident %s", incident.get("id"))
