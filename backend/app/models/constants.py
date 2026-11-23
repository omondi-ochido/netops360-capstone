"""Shared enumerations. Must stay in sync with database/schema.sql CHECK constraints."""

DEVICE_STATUSES = ("Online", "Offline", "Warning", "Unknown", "Unmonitored")
DEVICE_TYPES = ("router", "switch", "server", "host", "firewall", "access_point", "other")
MONITORING_METHODS = ("icmp", "tcp", "snmp", "none")
SUPPORTED_MONITORING_METHODS = ("icmp",)  # implemented checks

RULE_METRICS = ("device_status", "latency_ms", "packet_loss")
RULE_OPERATORS = ("eq", "neq", "gt", "gte", "lt", "lte")
RULE_SEVERITIES = ("info", "warning", "critical")
RULE_SCOPES = ("global", "device")

INCIDENT_STATUSES = ("open", "acknowledged", "resolved")
ACTIVE_INCIDENT_STATUSES = ("open", "acknowledged")

BACKUP_TYPES = ("manual", "scheduled", "incident_triggered")
BACKUP_STATUSES = ("success", "failed")

AUTOMATION_STATUSES = ("pending", "running", "success", "failed")
EVENT_TYPES = ("incident.opened", "incident.acknowledged", "incident.resolved")
