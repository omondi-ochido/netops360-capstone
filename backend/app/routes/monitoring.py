from flask import Blueprint, request

from app.extensions import get_container
from app.utils.auth import require_api_key
from app.utils.responses import ok, ok_list
from app.utils.validators import (
    parse_pagination, parse_timestamp_arg, validate_status,
)

bp = Blueprint("monitoring", __name__, url_prefix="/api/monitoring")


@bp.get("/history")
def history():
    c = get_container()
    limit, offset = parse_pagination(request.args)
    status = request.args.get("status")
    if status:
        validate_status(status)
    since = parse_timestamp_arg(request.args.get("since"), "since")
    until = parse_timestamp_arg(request.args.get("until"), "until")
    device_ref = request.args.get("device_id")
    if device_ref:
        rows = c.devices.history(device_ref, status=status, since=since, until=until,
                                 limit=limit, offset=offset)
    else:
        rows = c.repo.list_monitoring_logs(status=status, since=since, until=until,
                                           limit=limit, offset=offset)
    return ok_list(rows, limit, offset)


@bp.get("/latest")
def latest():
    devices = get_container().devices.list()
    fields = ("id", "hostname", "ip_address", "current_status", "last_latency_ms",
              "last_packet_loss", "last_checked_at", "last_seen_at", "monitoring_enabled")
    return ok([{k: d.get(k) for k in fields} for d in devices])


@bp.get("/summary")
def summary():
    return ok(get_container().monitoring.summary())


@bp.post("/run")
@require_api_key
def run_now():
    """Trigger an immediate check of all monitored devices."""
    results = get_container().monitoring.run_cycle(only_due=False)
    return ok({"checked": len(results), "results": results})
