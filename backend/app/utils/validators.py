"""Input validation helpers. Nothing here builds SQL or executes input."""
import ipaddress
import re
import uuid

from app.models.constants import DEVICE_STATUSES, DEVICE_TYPES, MONITORING_METHODS
from app.utils.exceptions import ValidationError
from app.utils.timeutil import parse_ts

HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

DEVICE_WRITABLE = {
    "hostname",
    "ip_address",
    "device_type",
    "operating_system",
    "site",
    "description",
    "ssh_enabled",
    "monitoring_enabled",
    "monitoring_method",
    "monitor_interval_seconds",
}


def json_body(request):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    return data


def is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def validate_uuid(value, field="id") -> str:
    if not is_uuid(value):
        raise ValidationError(f"{field} must be a valid UUID.")
    return str(uuid.UUID(str(value)))


def validate_ip(value, field="ip_address") -> str:
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        raise ValidationError(f"{field} must be a valid IPv4 or IPv6 address.") from None


def validate_choice(value, choices, field):
    if value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(choices)}.")
    return value


def validate_status(value, field="status"):
    return validate_choice(value, DEVICE_STATUSES, field)


def parse_pagination(args, default=50, maximum=200):
    try:
        limit = int(args.get("limit", default))
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        raise ValidationError("limit and offset must be integers.") from None
    if limit < 1 or limit > maximum:
        raise ValidationError(f"limit must be between 1 and {maximum}.")
    if offset < 0:
        raise ValidationError("offset must be 0 or greater.")
    return limit, offset


def parse_timestamp_arg(value, field):
    if value in (None, ""):
        return None
    try:
        return parse_ts(value).isoformat()
    except ValueError:
        raise ValidationError(f"{field} must be an ISO-8601 timestamp.") from None


def parse_bool_arg(value, field):
    if value in (None, ""):
        return None
    lowered = str(value).strip().lower()
    if lowered in ("1", "true", "yes"):
        return True
    if lowered in ("0", "false", "no"):
        return False
    raise ValidationError(f"{field} must be true or false.")


def _clean_str(payload, key, *, max_len=255, required=False, nullable=True):
    if key not in payload:
        if required:
            raise ValidationError(f"{key} is required.")
        return None
    value = payload[key]
    if value is None:
        if required or not nullable:
            raise ValidationError(f"{key} cannot be null.")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{key} must be a string.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{key} cannot be empty.")
    if len(value) > max_len:
        raise ValidationError(f"{key} must be at most {max_len} characters.")
    return value or None


def validate_device_payload(payload, *, partial=False):
    """Validate/whitelist a device create (partial=False) or patch (partial=True) body."""
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")
    unknown = sorted(set(payload) - DEVICE_WRITABLE)
    if unknown:
        raise ValidationError(f"Unknown or read-only fields: {', '.join(unknown)}.")

    clean = {}
    required = not partial

    if "hostname" in payload or required:
        hostname = _clean_str(payload, "hostname", max_len=63, required=True, nullable=False)
        if not HOSTNAME_RE.match(hostname):
            raise ValidationError(
                "hostname must start with a letter or digit and contain only letters, "
                "digits, '.', '_' or '-' (max 63 characters)."
            )
        clean["hostname"] = hostname

    if "ip_address" in payload or required:
        clean["ip_address"] = validate_ip(payload.get("ip_address"))

    if "device_type" in payload or required:
        clean["device_type"] = validate_choice(payload.get("device_type"), DEVICE_TYPES, "device_type")

    for key in ("operating_system", "site", "description"):
        if key in payload:
            clean[key] = _clean_str(
                payload,
                key,
                max_len=500 if key == "description" else 120,
                nullable=(key != "site"),
                required=(key == "site"),
            )

    for key in ("ssh_enabled", "monitoring_enabled"):
        if key in payload:
            if not isinstance(payload[key], bool):
                raise ValidationError(f"{key} must be a boolean.")
            clean[key] = payload[key]

    if "monitoring_method" in payload:
        clean["monitoring_method"] = validate_choice(
            payload["monitoring_method"], MONITORING_METHODS, "monitoring_method"
        )

    if "monitor_interval_seconds" in payload:
        value = payload["monitor_interval_seconds"]
        if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 3600:
            raise ValidationError("monitor_interval_seconds must be an integer between 5 and 3600.")
        clean["monitor_interval_seconds"] = value

    return clean
