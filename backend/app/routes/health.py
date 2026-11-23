from flask import Blueprint, jsonify

from app.extensions import get_container
from app.utils.exceptions import AppError
from app.utils.timeutil import now_iso

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    c = get_container()
    try:
        c.repo.ping()
        database = {"status": "ok"}
    except AppError:
        database = {"status": "unavailable"}
    return jsonify({
        "status": "ok" if database["status"] == "ok" else "degraded",
        "service": "netops360-backend",
        "database": database,
        "monitoring": {"running": c.monitor_runner.running},
        "timestamp": now_iso(),
    })
