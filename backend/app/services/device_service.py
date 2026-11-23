"""Device inventory backed by the repository (Supabase in production)."""
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.validators import is_uuid, validate_device_payload


def resolve_device(repo, identifier):
    """Look a device up by UUID or by hostname (keeps old hostname-style ids working)."""
    device = repo.get_device(identifier) if is_uuid(identifier) else repo.get_device_by_hostname(identifier)
    if device is None or not device.get("is_active", True):
        raise NotFoundError("Device not found.")
    return device


def legacy_view(device):
    """Shape a device row for the existing React dashboard.

    The original hardcoded inventory field names are not visible to the backend
    refactor, so both the canonical DB names and the common legacy aliases are
    returned. ADJUST HERE if the frontend reads other keys.
    """
    return {
        **device,
        "name": device["hostname"],
        "ip": device["ip_address"],
        "type": device["device_type"],
        "status": device["current_status"],
        "latency": device["last_latency_ms"],
        "latency_ms": device["last_latency_ms"],
        "packet_loss": device["last_packet_loss"],
        "packetLoss": device["last_packet_loss"],
        "last_checked": device["last_checked_at"],
    }


class DeviceService:
    def __init__(self, repo):
        self.repo = repo

    def list(self, include_inactive=False, status=None, limit=None, offset=0):
        return self.repo.list_devices(include_inactive=include_inactive, status=status,
                                      limit=limit, offset=offset)

    def get(self, identifier):
        return resolve_device(self.repo, identifier)

    def create(self, payload):
        data = validate_device_payload(payload, partial=False)
        if data.get("monitoring_method") == "none":
            data["monitoring_enabled"] = False
        enabled = data.get("monitoring_enabled", True)
        method = data.get("monitoring_method", "icmp")
        data["current_status"] = "Unknown" if enabled and method != "none" else "Unmonitored"
        return self.repo.create_device(data)

    def update(self, identifier, payload):
        device = resolve_device(self.repo, identifier)
        data = validate_device_payload(payload, partial=True)
        if not data:
            raise ValidationError("No updatable fields supplied.")
        if data.get("monitoring_method") == "none":
            data["monitoring_enabled"] = False
        enabled = data.get("monitoring_enabled", device["monitoring_enabled"])
        method = data.get("monitoring_method", device["monitoring_method"])
        if enabled and method == "none":
            raise ValidationError("monitoring cannot be enabled when monitoring_method is 'none'.")
        if "monitoring_enabled" in data or "monitoring_method" in data:
            if not enabled or method == "none":
                data["current_status"] = "Unmonitored"
            elif device["current_status"] == "Unmonitored":
                data["current_status"] = "Unknown"
        updated = self.repo.update_device(device["id"], data)
        if updated is None:
            raise NotFoundError("Device not found.")
        return updated

    def set_monitoring(self, identifier, enabled):
        return self.update(identifier, {"monitoring_enabled": bool(enabled)})

    def deactivate(self, identifier):
        """Soft delete: history is preserved, the device just stops being listed/monitored."""
        device = resolve_device(self.repo, identifier)
        return self.repo.update_device(
            device["id"],
            {"is_active": False, "monitoring_enabled": False, "current_status": "Unmonitored"},
        )

    def history(self, identifier, **filters):
        device = resolve_device(self.repo, identifier)
        return self.repo.list_monitoring_logs(device_id=device["id"], **filters)
