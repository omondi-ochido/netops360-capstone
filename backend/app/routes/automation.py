from flask import Blueprint, request

from app.extensions import get_container
from app.models.constants import AUTOMATION_STATUSES
from app.utils.auth import require_api_key
from app.utils.responses import ok, ok_list
from app.utils.validators import parse_pagination, validate_choice, validate_uuid

bp = Blueprint("automation", __name__, url_prefix="/api/automation")


@bp.get("/logs")
@require_api_key
def logs():
    limit, offset = parse_pagination(request.args)
    status = request.args.get("status")
    if status:
        validate_choice(status, AUTOMATION_STATUSES, "status")
    incident_id = request.args.get("incident_id")
    device_id = request.args.get("device_id")
    rows = get_container().automation.list_logs(
        status=status,
        incident_id=validate_uuid(incident_id, "incident_id") if incident_id else None,
        device_id=validate_uuid(device_id, "device_id") if device_id else None,
        limit=limit, offset=offset,
    )
    return ok_list(rows, limit, offset)


@bp.post("/retry/<log_id>")
@require_api_key
def retry(log_id):
    return ok(get_container().automation.retry(log_id), 202)
