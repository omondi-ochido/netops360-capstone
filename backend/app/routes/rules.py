from flask import Blueprint, request

from app.extensions import get_container
from app.utils.auth import require_permission
from app.utils.responses import ok, ok_list
from app.utils.validators import json_body, parse_bool_arg, parse_pagination

bp = Blueprint("rules", __name__, url_prefix="/api/rules")


@bp.get("", strict_slashes=False)
@require_permission("rules.read")
def list_rules():
    limit, offset = parse_pagination(request.args)
    enabled = parse_bool_arg(request.args.get("enabled"), "enabled")
    rules = get_container().rules.list_rules(enabled_only=bool(enabled), limit=limit, offset=offset)
    return ok_list(rules, limit, offset)


@bp.post("", strict_slashes=False)
@require_permission("rules.create")
def create_rule():
    c = get_container()
    rule = c.rules.create_rule(json_body(request))
    c.audit.record("created", "rule", row=rule)
    return ok(rule, 201)


@bp.get("/<rule_id>")
@require_permission("rules.read")
def get_rule(rule_id):
    return ok(get_container().rules.get_rule(rule_id))


@bp.patch("/<rule_id>")
@require_permission("rules.update")
def update_rule(rule_id):
    c = get_container()
    before = c.rules.get_rule(rule_id)
    rule = c.rules.update_rule(rule_id, json_body(request))
    c.audit.record("updated", "rule", row=rule, before=before)
    return ok(rule)


@bp.delete("/<rule_id>")
@require_permission("rules.delete")
def delete_rule(rule_id):
    c = get_container()
    before = c.rules.get_rule(rule_id)
    c.rules.delete_rule(rule_id)
    c.audit.record("deleted", "rule", row=before, before=before, after={})
    return ok({"deleted": True})
