from flask import Blueprint, g, request

from app.extensions import get_container
from app.utils.auth import require_permission
from app.utils.responses import ok, ok_list
from app.utils.validators import json_body, parse_pagination

bp = Blueprint("users", __name__, url_prefix="/api")


@bp.get("/users")
@require_permission("users.read")
def list_users():
    limit, offset = parse_pagination(request.args)
    rows, total = get_container().users.list_users(limit, offset,
        search=request.args.get("search"), status=request.args.get("status"))
    return ok_list(rows, limit, offset, total=total)


@bp.post("/users")
@require_permission("users.create")
def create_user():
    user = get_container().users.invite_user(json_body(request), g.auth_identity["sub"])
    return ok(user, 201)


@bp.get("/users/<user_id>")
@require_permission("users.read")
def get_user(user_id):
    return ok(get_container().users.get_user(user_id))


@bp.patch("/users/<user_id>")
@require_permission("users.update")
def update_user(user_id):
    return ok(get_container().users.update_user(user_id, json_body(request)))


@bp.patch("/users/<user_id>/status")
@require_permission("users.suspend")
def update_user_status(user_id):
    body = json_body(request)
    if set(body) != {"status"}:
        from app.utils.exceptions import ValidationError
        raise ValidationError("Request body must contain only status.")
    return ok(get_container().users.set_status(user_id, body["status"], g.auth_identity["sub"]))


@bp.post("/users/<user_id>/roles")
@require_permission("roles.assign")
def assign_user_role(user_id):
    body = json_body(request)
    if set(body) != {"role_id"}:
        from app.utils.exceptions import ValidationError
        raise ValidationError("Request body must contain only role_id.")
    return ok(get_container().users.assign_role(user_id, body["role_id"], g.auth_identity["sub"]))


@bp.delete("/users/<user_id>/roles/<role_id>")
@require_permission("roles.assign")
def remove_user_role(user_id, role_id):
    return ok(get_container().users.remove_role(user_id, role_id, g.auth_identity["sub"]))


@bp.get("/roles")
@require_permission("roles.read")
def list_roles():
    return ok(get_container().users.get_roles())


@bp.get("/permissions")
@require_permission("roles.read")
def list_permissions():
    return ok(get_container().users.get_permissions())


@bp.get("/users/<user_id>/audit-logs")
@require_permission("users.read", "audit.read")
def user_audit_logs(user_id):
    get_container().users.get_user(user_id)  # validates the subject exists and UUID is well-formed
    limit, offset = parse_pagination(request.args)
    return ok_list(get_container().repo.list_user_audit_logs(user_id, limit, offset), limit, offset)
