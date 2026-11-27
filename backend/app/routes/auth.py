from datetime import datetime, timezone

from flask import Blueprint, g, request

from app.extensions import get_container
from app.utils.auth import require_auth, require_recent_mfa
from app.utils.rate_limit import auth_rate_limit
from app.utils.responses import ok
from app.utils.timeutil import now_iso
from app.utils.validators import json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.get("/me")
@require_auth
def me():
    c = get_container()
    profile = g.auth_profile
    if profile is None:
        # Names in JWT metadata are display-only hints. They confer no role or
        # company membership; the user must submit company details to the RPC.
        metadata = g.auth_identity.get("user_metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        email = g.auth_identity.get("email")
        suggested_name = metadata.get("full_name") or metadata.get("name")
        return ok({
            "user": {"id": g.auth_identity["sub"], "email": email,
                     "full_name": suggested_name if isinstance(suggested_name, str) else "",
                     "company_name": None, "company_id": None},
            "roles": [], "permissions": [], "onboarding_required": True,
        })
    profile = c.repo.update_profile(g.auth_identity["sub"], {"last_login_at": now_iso()})
    roles = c.repo.get_user_roles(g.auth_identity["sub"])
    user = c.users._safe_profile(profile)
    return ok({"user": user, "onboarding_required": False,
               "invitation_required": profile.get("account_status") == "pending",
               "mfa_required": bool(set(roles).intersection({"super_admin", "company_admin", "admin"})
                                    and g.auth_identity.get("aal", "aal1") != "aal2"),
               "roles": roles,
               "permissions": c.repo.get_user_permissions(g.auth_identity["sub"])})


@require_auth
@auth_rate_limit("registration")
def register_company():
    c = get_container()
    result = c.auth.register_company(g.auth_identity, json_body(request))
    return ok({"company": result["company"],
               "user": c.users._safe_profile(result["profile"]),
               "roles": result["roles"],
               "permissions": c.repo.get_user_permissions(g.auth_identity["sub"]),
               "onboarding_required": False}, 201)


bp.add_url_rule("/onboard-company", endpoint="onboard_company", view_func=register_company, methods=["POST"])
bp.add_url_rule("/register-company", endpoint="register_company", view_func=register_company, methods=["POST"])


@bp.post("/logout")
@require_auth
def logout():
    identity = g.auth_identity
    if g.auth_profile is None:
        # There is no application profile to revoke against yet. Supabase signout
        # still clears/revokes the provider session in the browser.
        return ok({"revoked": False, "application_profile": False})
    expires_at = datetime.fromtimestamp(identity["exp"], tz=timezone.utc).isoformat()
    get_container().repo.revoke_session(identity["session_id"], identity["sub"], expires_at)
    auth_admin = get_container().users.auth_admin
    if auth_admin and hasattr(auth_admin, "sign_out"):
        try:
            auth_admin.sign_out(g.auth_token, scope="local")
        except Exception:
            # Flask immediately denies this session via revoked_sessions. The
            # client clears its local session even if Auth's revocation call fails.
            pass
    get_container().audit.record("session_revoked", "session", row={"id": identity["session_id"]})
    return ok({"revoked": True})


@bp.get("/session")
@require_auth
def current_session():
    identity = g.auth_identity
    return ok({
        "session_id": identity["session_id"],
        "issued_at": datetime.fromtimestamp(identity["iat"], tz=timezone.utc).isoformat()
                     if isinstance(identity.get("iat"), (int, float)) else None,
        "expires_at": datetime.fromtimestamp(identity["exp"], tz=timezone.utc).isoformat(),
        "assurance_level": identity.get("aal", "aal1"),
        "current_session": True,
    })


@bp.post("/sessions/revoke-all")
@require_auth
@require_recent_mfa
def revoke_all_sessions():
    c = get_container()
    auth_admin = c.users.auth_admin
    if auth_admin is None or not hasattr(auth_admin, "sign_out"):
        from app.utils.exceptions import ServiceUnavailableError
        raise ServiceUnavailableError("Supabase session revocation is unavailable.")
    try:
        auth_admin.sign_out(g.auth_token, scope="global")
    except Exception:
        from app.utils.exceptions import ServiceUnavailableError
        raise ServiceUnavailableError("Supabase could not revoke all sessions.") from None
    cutoff = now_iso()
    c.repo.update_profile(g.auth_identity["sub"], {"sessions_revoked_at": cutoff})
    c.audit.record("all_sessions_revoked", "session", row={"id": g.auth_identity["sub"]})
    return ok({"revoked": True, "sessions_revoked_at": cutoff})


@bp.post("/security-events")
@require_auth
def security_event():
    body = json_body(request)
    event = body.get("event") if isinstance(body, dict) else None
    allowed = {"login_succeeded", "password_changed", "mfa_enrolled", "mfa_removed"}
    if set(body) != {"event"} or event not in allowed:
        from app.utils.exceptions import ValidationError
        raise ValidationError("Unsupported authentication security event.")
    identity = g.auth_identity
    if event in {"mfa_enrolled", "mfa_removed"} and identity.get("aal", "aal1") != "aal2":
        from app.utils.exceptions import ForbiddenError
        raise ForbiddenError("Authenticator changes must be verified with MFA.", code="mfa_required")
    if event == "login_succeeded":
        # A duplicate event for one session is harmless and is constrained by
        # a unique database index in the MFA/session migration.
        get_container().audit.record(event, "session", row={"id": identity["session_id"]})
    else:
        get_container().audit.record(event, "user", row={"id": identity["sub"]})
    return ok({"recorded": True})
