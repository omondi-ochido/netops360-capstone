"""Extension singletons and the service container (dependency wiring)."""
import logging
import threading

from flask import current_app
from flask_cors import CORS

from app.services.automation_service import AutomationService
from app.services.audit_service import AuditService
from app.services.backup_service import BackupService
from app.services.device_service import DeviceService
from app.services.incident_service import IncidentService
from app.services.monitoring_service import MonitoringService, MonitorRunner
from app.services.rule_engine import RuleEngine
from app.services.user_service import UserService
from app.utils.exceptions import AppError

logger = logging.getLogger(__name__)

cors = CORS()


class Container:
    """Holds one instance of every service; built once per app."""

    def __init__(self, config, repo):
        self.config = config
        self.repo = repo
        self.audit = AuditService(repo)
        auth_admin = getattr(repo, "auth_admin", None)
        if auth_admin is None:
            auth_admin = getattr(getattr(getattr(repo, "client", None), "auth", None), "admin", None)
        self.users = UserService(repo, auth_admin, config, self.audit)
        self.automation = AutomationService(repo, config)
        self.incidents = IncidentService(repo, automation=self.automation)
        self.rules = RuleEngine(repo, incident_service=self.incidents)
        self.devices = DeviceService(repo)
        self.monitoring = MonitoringService(repo, config, evaluator=self.rules.evaluate_and_apply)
        self.backups = BackupService(repo, config)
        self.monitor_runner = MonitorRunner(self.monitoring, config,
                                            automation=self.automation, backups=self.backups)
        if config.backup_on_critical_incident:
            self.incidents.on_opened.append(self._backup_on_critical)

    def _backup_on_critical(self, incident, device, rule):
        if incident["severity"] != "critical" or not device.get("ssh_enabled"):
            return

        def run():
            try:
                self.backups.run_backup(device["id"], "incident_triggered")
            except AppError as exc:
                logger.warning("Incident-triggered backup for %s failed: %s",
                               device["hostname"], exc.code)

        threading.Thread(target=run, name="incident-backup", daemon=True).start()


def get_container() -> Container:
    return current_app.extensions["netops"]
