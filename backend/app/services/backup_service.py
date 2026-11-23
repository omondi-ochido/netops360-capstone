"""Configuration backups over SSH (Netmiko / VyOS). Credentials come from the environment."""
import hashlib
import logging

from app.models.constants import BACKUP_TYPES
from app.services.device_service import resolve_device
from app.utils.exceptions import (
    AppError, ExternalServiceError, NotFoundError, ServiceUnavailableError, ValidationError,
)
from app.utils.timeutil import now_iso
from app.utils.validators import validate_choice, validate_uuid

logger = logging.getLogger(__name__)

CONFIG_COMMAND = "show configuration commands"
INTERFACES_COMMAND = "show interfaces"


class BackupFailedError(ExternalServiceError):
    code = "backup_failed"
    default_message = "The configuration backup failed."


def _default_connect(**kwargs):
    from netmiko import ConnectHandler  # imported lazily: it is slow to import

    return ConnectHandler(**kwargs)


def classify_ssh_error(exc):
    name = type(exc).__name__.lower()
    if "authentication" in name:
        return "authentication_failed", "SSH authentication failed."
    if "timeout" in name or isinstance(exc, TimeoutError):
        return "connection_timeout", "SSH connection timed out."
    return "connection_error", "SSH connection to the device failed."


def safe_backup_view(row):
    """Backup metadata only - never the configuration text."""
    return {k: row.get(k) for k in ("id", "device_id", "backup_type", "status", "checksum",
                                    "created_at", "completed_at", "error_message", "metadata")}


class BackupService:
    def __init__(self, repo, config, connect=None):
        self.repo = repo
        self.config = config
        self._connect = connect or _default_connect

    def run_backup(self, identifier, backup_type="manual"):
        validate_choice(backup_type, BACKUP_TYPES, "backup_type")
        device = resolve_device(self.repo, identifier)
        if not device.get("ssh_enabled"):
            raise ValidationError("SSH is not enabled for this device.")
        if not (self.config.ssh_username and self.config.ssh_password):
            raise ServiceUnavailableError(
                "SSH credentials are not configured (NETOPS_SSH_USERNAME / NETOPS_SSH_PASSWORD).",
                code="ssh_not_configured",
            )

        started = now_iso()
        try:
            conn = self._connect(
                device_type="vyos", host=device["ip_address"],
                username=self.config.ssh_username, password=self.config.ssh_password,
                timeout=self.config.ssh_timeout_seconds,
                conn_timeout=self.config.ssh_timeout_seconds,
                auth_timeout=self.config.ssh_timeout_seconds,
            )
            try:
                configuration = conn.send_command(CONFIG_COMMAND)
                interfaces = conn.send_command(INTERFACES_COMMAND)
            finally:
                try:
                    conn.disconnect()
                except Exception:  # pragma: no cover
                    pass
        except AppError:
            raise
        except Exception as exc:
            kind, message = classify_ssh_error(exc)
            logger.error("Backup SSH failure for %s: %s", device["hostname"], kind)
            self._record_failure(device, backup_type, message, {"error_type": kind})
            raise BackupFailedError(message, details={"reason": kind}) from None

        if not isinstance(configuration, str) or not configuration.strip():
            message = "The device returned an empty configuration."
            row = self._record_failure(device, backup_type, message, {"error_type": "empty_configuration"})
            raise BackupFailedError(message, details={"reason": "empty_configuration",
                                                      "backup_id": row["id"]})

        checksum = hashlib.sha256(configuration.encode("utf-8")).hexdigest()
        previous = self.repo.latest_successful_backup(device["id"])
        changed = previous is None or previous.get("checksum") != checksum
        row = self.repo.insert_backup({
            "device_id": device["id"], "configuration": configuration,
            "interfaces_snapshot": interfaces if isinstance(interfaces, str) else None,
            "backup_type": backup_type, "status": "success", "checksum": checksum,
            "created_at": started, "completed_at": now_iso(),
            "metadata": {"changed": changed, "previous_backup_id": previous["id"] if previous else None,
                         "config_lines": len(configuration.splitlines()),
                         "commands": [CONFIG_COMMAND, INTERFACES_COMMAND]},
        })
        return {"success": True, "changed": changed, "backup": safe_backup_view(row),
                "configuration": configuration, "interfaces": interfaces}

    def _record_failure(self, device, backup_type, message, metadata):
        try:
            return self.repo.insert_backup({
                "device_id": device["id"], "backup_type": backup_type, "status": "failed",
                "error_message": message, "completed_at": now_iso(), "metadata": metadata,
            })
        except AppError:
            logger.error("Could not persist failed backup record for %s", device["hostname"])
            return {"id": None}

    # ------------------------------------------------------------------ history
    def history(self, identifier, status=None, limit=50, offset=0):
        device = resolve_device(self.repo, identifier)
        return self.repo.list_backups(device_id=device["id"], status=status, limit=limit, offset=offset)

    def list(self, device_id=None, status=None, limit=50, offset=0):
        if device_id:
            device_id = validate_uuid(device_id, "device_id")
        return self.repo.list_backups(device_id=device_id, status=status, limit=limit, offset=offset)

    def get(self, backup_id):
        row = self.repo.get_backup(validate_uuid(backup_id, "backup_id"))
        if row is None:
            raise NotFoundError("Backup not found.")
        return row

    # ---------------------------------------------------------------- scheduling
    def run_scheduled_backups(self):
        results = []
        for device in self.repo.list_devices(monitoring_enabled=None):
            if not device.get("ssh_enabled"):
                continue
            try:
                self.run_backup(device["id"], "scheduled")
                results.append((device["hostname"], "success"))
            except AppError as exc:
                results.append((device["hostname"], exc.code))
        return results
