from datetime import datetime, timezone

from flask import Blueprint, g, request

from app.extensions import get_container
from app.utils.auth import require_auth
from app.utils.responses import ok
from app.utils.timeutil import now_iso
from app.utils.validators import json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.get("/me")
@require_auth
def me():
    c = get_container()
    profile = c.repo.update_profile(g.auth_identity["sub"], {"last_login_at": now_iso()})
    roles = c.repo.get_user_roles(g.auth_identity["sub"])
    user = c.users._safe_profile(profile)
    if "admin" in roles and "super_admin" not in roles:
        user["assistant_invites_used"] = c.users.assistant_invite_count(g.auth_identity["sub"])
    return ok({"user": user,
               "roles": roles,
               "permissions": c.repo.get_user_permissions(g.auth_identity["sub"])})


@bp.post("/onboard-company")
@require_auth
def onboard_company():
    c = get_container()
    profile = c.auth.onboard_company(g.auth_identity, json_body(request))
    c.audit.record("onboarded", "user", row=profile)
    return ok({"user": c.users._safe_profile(profile),
               "roles": c.repo.get_user_roles(g.auth_identity["sub"])})


@bp.post("/logout")
@require_auth
def logout():
    identity = g.auth_identity
    expires_at = datetime.fromtimestamp(identity["exp"], tz=timezone.utc).isoformat()
    get_container().repo.revoke_session(identity["session_id"], identity["sub"], expires_at)
    get_container().audit.record("session_revoked", "session", row={"id": identity["session_id"]})
    return ok({"revoked": True})
