from flask import Blueprint, jsonify, request

from app.extensions import get_container
from app.services.backup_service import safe_backup_view
from app.services.device_service import legacy_view
from app.utils.auth import require_api_key
from app.utils.responses import ok, ok_list
from app.utils.timeutil import now_iso
from app.utils.validators import (
    json_body, parse_bool_arg, parse_pagination, validate_status,
)

bp = Blueprint("devices", __name__, url_prefix="/api/devices")


@bp.get("", strict_slashes=False)
def list_devices():
    """Backward compatible: {"devices": [...], "timestamp": "..."}."""
    c = get_container()
    limit, offset = parse_pagination(request.args, default=200, maximum=200)
    status = request.args.get("status")
    if status:
        validate_status(status)
    if parse_bool_arg(request.args.get("refresh"), "refresh"):
        c.monitoring.refresh()  # rate-limited on-demand check, like the old live ping
    devices = c.devices.list(status=status, limit=limit, offset=offset)
    return jsonify({"devices": [legacy_view(d) for d in devices],
                    "count": len(devices), "timestamp": now_iso()})


@bp.get("/<device_id>")
def get_device(device_id):
    return ok(legacy_view(get_container().devices.get(device_id)))


@bp.post("", strict_slashes=False)
@require_api_key
def create_device():
    device = get_container().devices.create(json_body(request))
    return ok(legacy_view(device), 201)


@bp.patch("/<device_id>")
@require_api_key
def update_device(device_id):
    return ok(legacy_view(get_container().devices.update(device_id, json_body(request))))


@bp.delete("/<device_id>")
@require_api_key
def delete_device(device_id):
    """Soft delete: preserves monitoring, incident and backup history."""
    get_container().devices.deactivate(device_id)
    return ok({"deactivated": True})


@bp.post("/<device_id>/backup")
@require_api_key
def backup_device(device_id):
    c = get_container()
    result = c.backups.run_backup(device_id, "manual")
    return ok(result, 201)


@bp.get("/<device_id>/backups")
@require_api_key
def device_backups(device_id):
    limit, offset = parse_pagination(request.args)
    rows = get_container().backups.history(device_id, request.args.get("status"), limit, offset)
    return ok_list([safe_backup_view(r) for r in rows], limit, offset)
