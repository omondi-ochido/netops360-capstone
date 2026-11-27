from flask import Blueprint, g, jsonify, request

from app.extensions import get_container
from app.services.backup_service import safe_backup_view
from app.services.device_service import legacy_view, resolve_device
from app.utils.auth import require_backup_automation, require_permission
from app.utils.exceptions import AppError, ConflictError, ValidationError
from app.utils.responses import error_response, ok, ok_list
from app.utils.timeutil import now_iso
from app.utils.validators import (
    json_body, parse_bool_arg, parse_pagination, validate_choice, validate_status, validate_uuid,
)

bp = Blueprint("devices", __name__, url_prefix="/api/devices")


@bp.get("", strict_slashes=False)
@require_backup_automation("devices.read")
def list_devices():
    """Backward compatible: {"devices": [...], "timestamp": "..."}."""
    c = get_container()
    limit, offset = parse_pagination(request.args, default=200, maximum=200)
    status = request.args.get("status")
    if status:
        validate_status(status)
    refresh_requested = (
        parse_bool_arg(request.args.get("refresh"), "refresh")
        and not c.config.testing and not c.config.auth_test_bypass
    )
    snapshot = None
    if not c.config.testing:
        snapshot = c.monitoring.latest_snapshot(max_age_seconds=3)
    if refresh_requested and snapshot is None:
        c.monitoring.refresh(
            min_age_seconds=2, persist_async=True, use_snapshot=True,
        )
        snapshot = c.monitoring.latest_snapshot(max_age_seconds=3)
        if snapshot is None:
            snapshot = c.monitoring.latest_snapshot()

    if snapshot is not None:
        devices = snapshot["devices"]
        if status:
            devices = [device for device in devices if device["current_status"] == status]
        devices = devices[offset:offset + limit]
    else:
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
@require_backup_automation("backups.create")
def backup_device(device_id):
    c = get_container()
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict) or set(data) - {"backup_type", "incident_id"}:
        raise ValidationError("Backup request contains unsupported fields.")
    machine = bool(getattr(g, "backup_automation_token", False))
    backup_type = data.get("backup_type", "manual")
    if not machine and backup_type != "manual":
        raise ValidationError("Only the backup automation token may request scheduled or incident backups.")
    validate_choice(backup_type, ("manual", "scheduled", "incident_triggered"), "backup_type")
    device = resolve_device(c.repo, device_id)
    execution_id = request.headers.get("X-N8N-Execution-Id", "")[:200] or None
    incident_id = data.get("incident_id")
    if backup_type == "incident_triggered":
        incident_id = validate_uuid(incident_id, "incident_id")
        incident = c.repo.get_incident(incident_id)
        if not incident or incident.get("device_id") != device["id"]:
            raise ValidationError("incident_id must reference an incident for this device.")
    elif incident_id is not None:
        raise ValidationError("incident_id is only valid for incident_triggered backups.")

    log = None
    if machine:
        trigger_type = f"backup.{backup_type}"
        if execution_id:
            log = c.repo.find_automation_log_for_execution(execution_id, device["id"], trigger_type)
        if log and log["status"] == "success":
            backup_id = (log.get("response_payload") or {}).get("backup_id")
            backup = c.repo.get_backup(backup_id) if backup_id else None
            return ok({"success": True, "duplicate": True, "changed": (log.get("response_payload") or {}).get("changed", False),
                       "backup": safe_backup_view(backup) if backup else None,
                       "automation_log_id": log["id"]}, 200)
        if log and log["status"] == "running":
            raise ConflictError("This n8n execution already has a backup in progress.")
        if log and log["status"] == "failed":
            if log.get("retry_count", 0) >= 2:
                raise ConflictError("The retry limit for this workflow execution has been reached.")
            log = c.repo.update_automation_log(log["id"], {
                "status": "running", "started_at": now_iso(), "completed_at": None,
                "retry_count": log.get("retry_count", 0) + 1, "error_message": None,
            })
        if backup_type == "incident_triggered" and not log:
            previous = c.repo.find_automation_log(incident_id, trigger_type)
            if previous:
                backup_id = (previous.get("response_payload") or {}).get("backup_id")
                backup = c.repo.get_backup(backup_id) if backup_id else None
                summary = {"success": previous["status"] == "success", "duplicate": True,
                           "automation_log_id": previous["id"], "backup": safe_backup_view(backup) if backup else None}
                return ok(summary, 200)
        if not log:
            log = c.repo.insert_automation_log({
                "workflow_name": "n8n-config-backup", "trigger_type": trigger_type,
                "incident_id": incident_id, "device_id": device["id"], "rule_id": None,
                "execution_id": execution_id, "status": "running", "started_at": now_iso(),
                "request_payload": {"backup_type": backup_type, "incident_id": incident_id,
                                    "device_id": device["id"], "device_hostname": device["hostname"]},
            })
    try:
        result = c.backups.run_backup(device["id"], backup_type)
    except AppError as exc:
        if log:
            c.repo.update_automation_log(log["id"], {
                "status": "failed", "completed_at": now_iso(), "error_message": exc.code,
                "response_payload": {"error_code": exc.code,
                                     "reason": (exc.details or {}).get("reason"),
                                     "backup_id": (exc.details or {}).get("backup_id")},
            })
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    if log:
        c.repo.update_automation_log(log["id"], {
            "status": "success", "completed_at": now_iso(),
            "response_payload": {"backup_id": result["backup"]["id"], "status": "success",
                                 "checksum": result["backup"]["checksum"],
                                 "changed": result["changed"]},
        })
        return ok({"success": True, "changed": result["changed"],
                   "backup": result["backup"], "automation_log_id": log["id"]}, 201)
    return ok(result, 201)


@bp.get("/<device_id>/backups")
@require_permission("backups.read")
def device_backups(device_id):
    limit, offset = parse_pagination(request.args)
    rows = get_container().backups.history(device_id, request.args.get("status"), limit, offset)
    return ok_list([safe_backup_view(r) for r in rows], limit, offset)
