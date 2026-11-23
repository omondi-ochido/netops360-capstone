from datetime import datetime, timezone

from flask import Blueprint, g

from app.extensions import get_container
from app.utils.auth import require_auth
from app.utils.responses import ok
from app.utils.timeutil import now_iso

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.get("/me")
@require_auth
def me():
    c = get_container()
    profile = c.repo.update_profile(g.auth_identity["sub"], {"last_login_at": now_iso()})
    return ok({"user": c.users._safe_profile(profile),
               "roles": c.repo.get_user_roles(g.auth_identity["sub"]),
               "permissions": c.repo.get_user_permissions(g.auth_identity["sub"])})


@bp.post("/logout")
@require_auth
def logout():
    identity = g.auth_identity
    expires_at = datetime.fromtimestamp(identity["exp"], tz=timezone.utc).isoformat()
    get_container().repo.revoke_session(identity["session_id"], identity["sub"], expires_at)
    get_container().audit.record("session_revoked", "session", row={"id": identity["session_id"]})
    return ok({"revoked": True})
