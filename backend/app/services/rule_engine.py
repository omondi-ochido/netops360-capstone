"""Rule validation and evaluation. Rules are data only - nothing is ever eval()'d."""
import logging
import operator as op

from app.models.constants import (
    DEVICE_STATUSES, RULE_METRICS, RULE_OPERATORS, RULE_SCOPES, RULE_SEVERITIES,
)
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.validators import is_uuid, validate_uuid

logger = logging.getLogger(__name__)

OPERATOR_FUNCS = {"eq": op.eq, "neq": op.ne, "gt": op.gt, "gte": op.ge, "lt": op.lt, "lte": op.le}
OPERATOR_SYMBOLS = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
RULE_WRITABLE = {"name", "description", "metric", "operator", "threshold", "severity",
                 "enabled", "scope", "device_id"}
SKIP_STATUSES = ("Unmonitored", "Unknown")  # no trustworthy measurement -> no evaluation


def _normalize_threshold(metric, operator_name, threshold):
    if metric == "device_status":
        if operator_name not in ("eq", "neq"):
            raise ValidationError("device_status rules only support the eq and neq operators.")
        if not isinstance(threshold, str):
            raise ValidationError("device_status threshold must be a status string.")
        canonical = {s.lower(): s for s in DEVICE_STATUSES}.get(threshold.strip().lower())
        if canonical is None:
            raise ValidationError(f"device_status threshold must be one of: {', '.join(DEVICE_STATUSES)}.")
        return canonical
    if isinstance(threshold, bool) or threshold is None:
        raise ValidationError(f"{metric} threshold must be a number.")
    try:
        number = float(threshold)
    except (TypeError, ValueError):
        raise ValidationError(f"{metric} threshold must be a number.") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValidationError(f"{metric} threshold must be a finite number.")
    if number < 0:
        raise ValidationError(f"{metric} threshold cannot be negative.")
    if metric == "packet_loss" and number > 100:
        raise ValidationError("packet_loss threshold must be between 0 and 100.")
    return int(number) if number.is_integer() else number


def validate_rule(data):
    """Validate a *complete* rule definition and return a clean, whitelisted dict."""
    if not isinstance(data, dict):
        raise ValidationError("Rule must be a JSON object.")
    unknown = sorted(set(data) - RULE_WRITABLE - {"id", "created_at", "updated_at"})
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(unknown)}.")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValidationError("name is required (1-120 characters).")
    description = data.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 500):
        raise ValidationError("description must be a string of at most 500 characters.")

    metric, operator_name = data.get("metric"), data.get("operator")
    if metric not in RULE_METRICS:
        raise ValidationError(f"metric must be one of: {', '.join(RULE_METRICS)}.")
    if operator_name not in RULE_OPERATORS:
        raise ValidationError(f"operator must be one of: {', '.join(RULE_OPERATORS)}.")
    severity = data.get("severity")
    if severity not in RULE_SEVERITIES:
        raise ValidationError(f"severity must be one of: {', '.join(RULE_SEVERITIES)}.")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValidationError("enabled must be a boolean.")
    scope = data.get("scope", "global")
    if scope not in RULE_SCOPES:
        raise ValidationError(f"scope must be one of: {', '.join(RULE_SCOPES)}.")
    device_id = data.get("device_id")
    if scope == "device":
        device_id = validate_uuid(device_id, "device_id")
    elif device_id is not None:
        raise ValidationError("device_id is only allowed when scope is 'device'.")

    return {
        "name": name.strip(), "description": description, "metric": metric,
        "operator": operator_name,
        "threshold": _normalize_threshold(metric, operator_name, data.get("threshold")),
        "severity": severity, "enabled": enabled, "scope": scope, "device_id": device_id,
    }


def compare(operator_name, actual, threshold):
    func = OPERATOR_FUNCS.get(operator_name)
    if func is None:
        raise ValidationError(f"Unsupported operator: {operator_name}")
    try:
        return bool(func(actual, threshold))
    except TypeError:
        raise ValidationError("Cannot compare values of different types.") from None


def extract_metric(result, metric):
    value = {"device_status": result.get("status"), "latency_ms": result.get("latency_ms"),
             "packet_loss": result.get("packet_loss")}.get(metric)
    if value is None:
        return None
    return value if metric == "device_status" else float(value)


class RuleEngine:
    def __init__(self, repo, incident_service=None):
        self.repo = repo
        self.incidents = incident_service

    # ------------------------------------------------------------ CRUD (logic)
    def list_rules(self, enabled_only=False, limit=None, offset=0):
        return self.repo.list_rules(enabled_only=enabled_only, limit=limit, offset=offset)

    def get_rule(self, rule_id):
        rule = self.repo.get_rule(validate_uuid(rule_id, "rule_id"))
        if rule is None:
            raise NotFoundError("Rule not found.")
        return rule

    def create_rule(self, payload):
        clean = validate_rule(payload)
        if clean["scope"] == "device" and self.repo.get_device(clean["device_id"]) is None:
            raise ValidationError("device_id does not refer to an existing device.")
        return self.repo.create_rule(clean)

    def update_rule(self, rule_id, payload):
        existing = self.get_rule(rule_id)
        if not isinstance(payload, dict) or not payload:
            raise ValidationError("No updatable fields supplied.")
        unknown = sorted(set(payload) - RULE_WRITABLE)
        if unknown:
            raise ValidationError(f"Unknown or read-only fields: {', '.join(unknown)}.")
        merged = {k: existing.get(k) for k in RULE_WRITABLE}
        merged.update(payload)
        if merged["scope"] == "global" and "device_id" not in payload:
            merged["device_id"] = None
        clean = validate_rule(merged)
        updated = self.repo.update_rule(existing["id"], clean)
        if updated is None:
            raise NotFoundError("Rule not found.")
        return updated

    def delete_rule(self, rule_id):
        rule = self.get_rule(rule_id)
        if self.repo.rule_has_incidents(rule["id"]):
            raise ConflictError("This rule has incident history and cannot be deleted. "
                                "Disable it instead (PATCH enabled=false).")
        self.repo.delete_rule(rule["id"])

    # -------------------------------------------------------------- evaluation
    def evaluate(self, result, rules, device_id=None):
        """Pure evaluation: returns one structured entry per rule, performs no I/O."""
        evaluations = []
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("scope") == "device" and device_id and rule.get("device_id") != device_id:
                continue
            try:
                clean = validate_rule(rule)
            except ValidationError as exc:
                logger.warning("Skipping invalid rule %s: %s", rule.get("id"), exc.message)
                evaluations.append({"rule": rule, "valid": False, "evaluable": False,
                                    "triggered": False, "actual": None, "error": exc.message})
                continue
            actual = extract_metric(result, clean["metric"])
            if actual is None:  # missing metric: neither triggers nor clears
                evaluations.append({"rule": rule, "valid": True, "evaluable": False,
                                    "triggered": False, "actual": None, "error": None})
                continue
            triggered = compare(clean["operator"], actual, clean["threshold"])
            evaluations.append({"rule": rule, "valid": True, "evaluable": True,
                                "triggered": triggered, "actual": actual, "error": None})
        return evaluations

    def evaluate_and_apply(self, device, result):
        """Evaluate enabled rules for a monitoring result and open/resolve incidents."""
        summary = {"opened": [], "resolved": [], "touched": [], "skipped": None}
        if result.get("status") in SKIP_STATUSES:
            summary["skipped"] = f"status {result.get('status')} is not evaluated"
            return summary
        rules = self.repo.list_rules(enabled_only=True)
        for ev in self.evaluate(result, rules, device_id=device["id"]):
            if not ev["valid"] or not ev["evaluable"]:
                continue
            rule = ev["rule"]
            if ev["triggered"]:
                incident, created = self.incidents.open_incident(device, rule, ev["actual"])
                (summary["opened"] if created else summary["touched"]).append(incident["id"])
            else:
                resolved = self.incidents.resolve_for_rule(
                    device, rule, ev["actual"],
                    reason=f"{rule['metric']} returned within threshold",
                )
                if resolved:
                    summary["resolved"].append(resolved["id"])
        return summary
