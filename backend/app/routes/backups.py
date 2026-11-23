from flask import Blueprint, request

from app.extensions import get_container
from app.services.backup_service import safe_backup_view
from app.utils.auth import require_api_key
from app.utils.responses import ok, ok_list
from app.utils.validators import parse_pagination

bp = Blueprint("backups", __name__, url_prefix="/api/backups")


@bp.get("", strict_slashes=False)
@require_api_key
def list_backups():
    limit, offset = parse_pagination(request.args)
    rows = get_container().backups.list(
        device_id=request.args.get("device_id"), status=request.args.get("status"),
        limit=limit, offset=offset,
    )
    return ok_list([safe_backup_view(r) for r in rows], limit, offset)


@bp.get("/<backup_id>")
@require_api_key
def get_backup(backup_id):
    """Returns the full configuration text - protected by the API key."""
    c = get_container()
    backup = c.backups.get(backup_id)
    c.audit.record("sensitive_contents_read", "backup", row=backup)
    return ok(backup)
