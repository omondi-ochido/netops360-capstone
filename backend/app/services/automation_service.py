"""n8n webhook delivery with persistence, retries and flood protection.

Incident handling never waits on, or fails because of, n8n: the automation_logs
row is written first and delivery happens on a worker thread.
"""
import hashlib
import hmac
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import requests

from app.models.constants import EVENT_TYPES
from app.utils.exceptions import ConflictError, NotFoundError
from app.utils.timeutil import now_iso, parse_ts, utcnow
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)

WORKFLOW_NAME = "netops-incident"


class AutomationService:
    def __init__(self, repo, config, http_post=None):
        self.repo = repo
        self.config = config
        self._post = http_post or requests.post
        self._executor = None

    @property
    def configured(self):
        return bool(self.config.n8n_webhook_url)

    # ----------------------------------------------------------------- payload
    @staticmethod
    def build_payload(event_type, incident, device, rule):
        return {
            "event_type": event_type,
            "timestamp": now_iso(),
            "incident": {
                "id": incident["id"], "title": incident.get("title"),
                "description": incident.get("description"), "severity": incident["severity"],
                "status": incident["status"], "triggered_at": incident.get("triggered_at"),
                "acknowledged_at": incident.get("acknowledged_at"),
                "resolved_at": incident.get("resolved_at"),
                "duration_seconds": incident.get("duration_seconds"),
                "trigger_metric": incident.get("trigger_metric"),
                "trigger_value": incident.get("trigger_value"),
                "resolution_value": incident.get("resolution_value"),
            },
            "device": {
                "id": device["id"], "hostname": device["hostname"],
                "ip_address": device["ip_address"], "device_type": device["device_type"],
                "site": device.get("site"), "current_status": device.get("current_status"),
            },
            "rule": {
                "id": rule["id"], "name": rule["name"], "metric": rule["metric"],
                "operator": rule["operator"], "threshold": rule["threshold"],
                "severity": rule["severity"],
            },
        }

    # ------------------------------------------------------------------ notify
    def notify(self, event_type, incident, device, rule):
        """Record the event and dispatch delivery without blocking the caller."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type}")
        if not self.configured:
            logger.debug("N8N_WEBHOOK_URL not set; skipping %s", event_type)
            return None
        # flood guard: at most one event of each type per incident
        if self.repo.find_automation_log(incident["id"], event_type):
            logger.info("Duplicate %s for incident %s suppressed", event_type, incident["id"])
            return None
        log = self.repo.insert_automation_log({
            "workflow_name": WORKFLOW_NAME, "trigger_type": event_type,
            "incident_id": incident["id"], "device_id": device["id"], "rule_id": rule["id"],
            "status": "pending",
            "request_payload": self.build_payload(event_type, incident, device, rule),
        })
        self._dispatch(log["id"])
        return log

    def _dispatch(self, log_id, is_retry=False):
        if self.config.automation_synchronous:
            self._safe_deliver(log_id, is_retry)
            return
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="n8n")
        self._executor.submit(self._safe_deliver, log_id, is_retry)

    def _safe_deliver(self, log_id, is_retry=False):
        try:
            self.deliver(log_id, is_retry)
        except Exception:
            logger.exception("Webhook delivery crashed for log %s", log_id)

    # ---------------------------------------------------------------- delivery
    def deliver(self, log_id, is_retry=False):
        log = self.repo.get_automation_log(log_id)
        if log is None or log["status"] == "success":
            return log
        retries = log["retry_count"] + (1 if is_retry else 0)
        self.repo.update_automation_log(log_id, {"status": "running", "started_at": now_iso(),
                                                 "retry_count": retries})
        body = json.dumps(log["request_payload"], separators=(",", ":"), default=str).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-NetOps-Event": log["trigger_type"],
                   "X-NetOps-Delivery": str(log_id)}
        if self.config.n8n_webhook_secret:
            digest = hmac.new(self.config.n8n_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-NetOps-Signature"] = f"sha256={digest}"

        update = {"completed_at": now_iso()}
        try:
            resp = self._post(self.config.n8n_webhook_url, data=body, headers=headers,
                              timeout=self.config.automation_timeout_seconds)
            text = (getattr(resp, "text", "") or "")[:2000]
            update["response_payload"] = {"status_code": resp.status_code, "body": text}
            if 200 <= resp.status_code < 300:
                update.update(status="success", error_message=None)
                try:
                    update["execution_id"] = str(resp.json().get("executionId") or "") or None
                except Exception:
                    pass
            else:
                update.update(status="failed", error_message=f"n8n returned HTTP {resp.status_code}")
        except requests.Timeout:
            update.update(status="failed", error_message="Webhook request timed out.")
        except requests.RequestException:
            update.update(status="failed", error_message="Webhook endpoint unreachable.")
        except Exception:
            logger.exception("Unexpected webhook error")
            update.update(status="failed", error_message="Unexpected webhook error.")
        return self.repo.update_automation_log(log_id, update)

    # ------------------------------------------------------------------ retries
    def retry(self, log_id):
        """Manual retry of a failed/pending delivery."""
        log = self.repo.get_automation_log(validate_uuid(log_id, "log_id"))
        if log is None:
            raise NotFoundError("Automation log not found.")
        if log["status"] not in ("failed", "pending"):
            raise ConflictError(f"A log with status '{log['status']}' cannot be retried.")
        if not self.configured:
            raise ConflictError("N8N_WEBHOOK_URL is not configured.")
        self._dispatch(log["id"], is_retry=True)
        return self.repo.get_automation_log(log["id"])

    def retry_due(self):
        """Retry failed deliveries whose exponential backoff has elapsed. Returns count."""
        if not self.configured:
            return 0
        now, count = utcnow(), 0
        for log in self.repo.list_retryable_automation_logs(self.config.automation_max_retries):
            reference = parse_ts(log.get("completed_at") or log["created_at"])
            wait = self.config.automation_backoff_seconds * (2 ** log["retry_count"])
            if log["status"] == "pending":
                wait = max(wait, 60)  # a delivery thread may still be working on it
            if (now - reference).total_seconds() >= wait:
                self._dispatch(log["id"], is_retry=True)
                count += 1
        return count

    # ------------------------------------------------------------------ queries
    def list_logs(self, status=None, incident_id=None, device_id=None, limit=50, offset=0):
        return self.repo.list_automation_logs(status=status, incident_id=incident_id,
                                              device_id=device_id, limit=limit, offset=offset)
