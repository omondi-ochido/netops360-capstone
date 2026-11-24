from flask import Blueprint, jsonify, request

from app.extensions import get_container
from app.services.backup_service import safe_backup_view
from app.services.device_service import legacy_view
from app.utils.auth import require_permission
from app.utils.responses import ok, ok_list
from app.utils.timeutil import now_iso
from app.utils.validators import (
    json_body, parse_bool_arg, parse_pagination, validate_status,
)

bp = Blueprint("devices", __name__, url_prefix="/api/devices")


@bp.get("", strict_slashes=False)
@require_permission("devices.read")
def list_devices():
    """Backward compatible: {"devices": [...], "timestamp": "..."}."""
    c = get_container()
    limit, offset = parse_pagination(request.args, default=200, maximum=200)
    status = request.args.get("status")
    if status:
        validate_status(status)
    if (parse_bool_arg(request.args.get("refresh"), "refresh")
            and not c.config.testing and not c.config.auth_test_bypass):
        c.monitoring.refresh()  # rate-limited on-demand check, like the old live ping
    devices = c.devices.list(status=status, limit=limit, offset=offset)
    rows = [legacy_view(d) for d in devices]
    return jsonify({"data": rows, "devices": rows,
                    "count": len(devices), "pagination": {"limit": limit, "offset": offset,
                    "count": len(devices)}, "timestamp": now_iso()})


@bp.get("/<device_id>")
@require_permission("devices.read")
def get_device(device_id):
    return ok(legacy_view(get_container().devices.get(device_id)))


@bp.post("", strict_slashes=False)
@require_permission("devices.create")
def create_device():
    c = get_container()
    device = c.devices.create(json_body(request))
    c.audit.record("created", "device", row=device)
    return ok(legacy_view(device), 201)


@bp.patch("/<device_id>")
@require_permission("devices.update")
def update_device(device_id):
    c = get_container()
    before = c.devices.get(device_id)
    device = c.devices.update(device_id, json_body(request))
    c.audit.record("updated", "device", row=device, before=before)
    return ok(legacy_view(device))


@bp.delete("/<device_id>")
@require_permission("devices.delete")
def delete_device(device_id):
    """Soft delete: preserves monitoring, incident and backup history."""
    c = get_container()
    before = c.devices.get(device_id)
    device = c.devices.deactivate(device_id)
    c.audit.record("deactivated", "device", row=device, before=before)
    return ok({"deactivated": True})


@bp.post("/<device_id>/backup")
@require_permission("backups.create")
def backup_device(device_id):
    c = get_container()
    result = c.backups.run_backup(device_id, "manual")
    return ok(result, 201)


@bp.get("/<device_id>/backups")
@require_permission("backups.read")
def device_backups(device_id):
    limit, offset = parse_pagination(request.args)
    rows = get_container().backups.history(device_id, request.args.get("status"), limit, offset)
    return ok_list([safe_backup_view(r) for r in rows], limit, offset)
