"""Permission catalogue mirrored by the additive Auth/RBAC migration."""
ROLE_PERMISSIONS = {
    "super_admin": "*",
    "admin": {
        "devices.read", "devices.create", "devices.update", "devices.delete",
        "monitoring.read", "monitoring.manage", "rules.read", "rules.create",
        "rules.update", "rules.delete", "incidents.read", "incidents.acknowledge",
        "incidents.resolve", "automation.read", "automation.execute", "backups.read",
        "backups.create", "users.read", "users.create", "users.update", "users.suspend",
        "roles.read", "roles.assign", "audit.read",
    },
    "network_operator": {
        "devices.read", "monitoring.read", "monitoring.manage", "rules.read",
        "incidents.read", "incidents.acknowledge", "incidents.resolve",
        "automation.read", "automation.execute", "backups.read",
    },
    "viewer": {"devices.read", "monitoring.read", "rules.read", "incidents.read"},
}

PERMISSION_KEYS = (
    "devices.read", "devices.create", "devices.update", "devices.delete",
    "monitoring.read", "monitoring.manage", "rules.read", "rules.create", "rules.update", "rules.delete",
    "incidents.read", "incidents.acknowledge", "incidents.resolve", "automation.read", "automation.execute",
    "backups.read", "backups.create", "backups.restore", "users.read", "users.create", "users.update",
    "users.suspend", "roles.read", "roles.assign", "audit.read", "system.manage",
)
