from flask import Blueprint, request

from app.extensions import get_container
from app.utils.auth import require_permission
from app.utils.responses import ok, ok_list
from app.utils.validators import parse_bool_arg, parse_pagination, validate_uuid

bp = Blueprint("incidents", __name__, url_prefix="/api/incidents")


@bp.get("", strict_slashes=False)
@require_permission("incidents.read")
def list_incidents():
    c = get_container()
    limit, offset = parse_pagination(request.args)
    device_ref = request.args.get("device_id")
    device_id = c.devices.get(device_ref)["id"] if device_ref else None
    rule_id = request.args.get("rule_id")
    if rule_id:
        rule_id = validate_uuid(rule_id, "rule_id")
    rows = c.incidents.list(
        status=request.args.get("status"), severity=request.args.get("severity"),
        device_id=device_id, rule_id=rule_id,
        active_only=bool(parse_bool_arg(request.args.get("active"), "active")),
        limit=limit, offset=offset,
    )
    return ok_list(rows, limit, offset)


@bp.get("/<incident_id>")
@require_permission("incidents.read")
def get_incident(incident_id):
    return ok(get_container().incidents.get(incident_id))


@bp.post("/<incident_id>/acknowledge")
@require_permission("incidents.acknowledge")
def acknowledge(incident_id):
    c = get_container()
    before = c.incidents.get(incident_id)
    incident = c.incidents.acknowledge(incident_id)
    if before.get("status") == "open" and incident.get("status") == "acknowledged":
        c.audit.record("acknowledged", "incident", row=incident, before=before)
    return ok(incident)


@bp.post("/<incident_id>/resolve")
@require_permission("incidents.resolve")
def resolve(incident_id):
    c = get_container()
    before = c.incidents.get(incident_id)
    incident = c.incidents.resolve(incident_id)
    if before.get("status") in ("open", "acknowledged") and incident.get("status") == "resolved":
        c.audit.record("resolved", "incident", row=incident, before=before)
    return ok(incident)
