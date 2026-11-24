"""ICMP monitoring: ping execution, result classification, persistence, scheduling."""
import logging
import platform
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

from app.models.constants import SUPPORTED_MONITORING_METHODS
from app.utils.exceptions import ValidationError
from app.utils.timeutil import now_iso, parse_ts, utcnow
from app.utils.validators import validate_ip

logger = logging.getLogger(__name__)

_STATS_RE = re.compile(r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets\s+)?received", re.I)
_RTT_RE = re.compile(r"(?:rtt|round-trip)[^=]*=\s*[\d.]+/([\d.]+)/", re.I)


def parse_ping_output(output):
    """Return (packets_sent, packets_received, avg_latency_ms|None) or None if unparseable."""
    stats = _STATS_RE.search(output or "")
    if not stats:
        return None
    sent, received = int(stats.group(1)), int(stats.group(2))
    rtt = _RTT_RE.search(output)
    return sent, received, (float(rtt.group(1)) if rtt else None)


def build_ping_command(ip, count, timeout, system=None, interval=None):
    system = system or platform.system()
    command = ["ping", "-c", str(count)]
    if interval is not None:
        command.extend(["-i", str(interval)])
    if system == "Linux":
        return [*command, "-W", str(timeout), ip]
    if system == "Darwin":  # macOS -W is in milliseconds
        return [*command, "-W", str(timeout * 1000), ip]
    raise OSError(f"ICMP monitoring is not supported on {system}")


def classify(packet_loss, partial_status="Warning"):
    if packet_loss >= 100:
        return "Offline"
    if packet_loss > 0:
        return partial_status
    return "Online"


def _result(status, **extra):
    base = {
        "status": status, "latency_ms": None, "packet_loss": None, "packets_sent": None,
        "packets_received": None, "error_message": None, "check_type": "icmp",
        "checked_at": now_iso(),
    }
    base.update(extra)
    return base


def _check_gns3_node_status(hostname, gns3_url="http://127.0.0.1:3080"):
    offline_result = _result(
        "Offline", latency_ms=None, packet_loss=100.0, check_type="manual",
    )
    try:
        response = requests.get(f"{gns3_url}/v2/projects", timeout=2)
        response.raise_for_status()
        projects = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("GNS3 project lookup failed for %s (%s)", hostname, type(exc).__name__)
        return offline_result

    if not isinstance(projects, list):
        logger.warning("GNS3 returned an invalid project list for %s", hostname)
        return offline_result

    opened_projects = [
        project for project in projects
        if isinstance(project, dict) and project.get("status") == "opened"
    ]
    for project in opened_projects or projects:
        if not isinstance(project, dict):
            continue
        project_id = project.get("project_id") or project.get("id")
        if not project_id:
            continue
        try:
            response = requests.get(
                f"{gns3_url}/v2/projects/{project_id}/nodes", timeout=2,
            )
            response.raise_for_status()
            nodes = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                "GNS3 node lookup failed for %s (%s)", hostname, type(exc).__name__,
            )
            continue

        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            if isinstance(name, str) and name.casefold() == hostname.casefold():
                if node.get("status") == "started":
                    return _result(
                        "Online", latency_ms=0.5, packet_loss=0.0, check_type="manual",
                    )

    return offline_result


def ping_host(ip, count=3, timeout=2, partial_status="Warning", runner=subprocess.run, system=None,
              interval=None):
    """Ping one host without a shell. Never raises; failures become result dicts."""
    try:
        ip = validate_ip(ip)
        cmd = build_ping_command(ip, count, timeout, system, interval)
    except ValidationError as exc:
        return _result("Unknown", error_message=exc.message)
    except OSError as exc:
        return _result("Unknown", error_message=str(exc))

    try:
        proc = runner(cmd, capture_output=True, text=True, shell=False,
                      timeout=count * (timeout + 1) + 2)
    except subprocess.TimeoutExpired:
        return _result("Unknown", error_message="ping command timed out")
    except FileNotFoundError:
        return _result("Unknown", error_message="ping executable not found")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected ping failure: %s", type(exc).__name__)
        return _result("Unknown", error_message="unexpected ping failure")

    output = (proc.stdout or "") + (proc.stderr or "")
    parsed = parse_ping_output(output)
    if parsed is None:
        if "unreachable" in output.lower():
            return _result("Offline", packet_loss=100.0, packets_sent=count, packets_received=0,
                           error_message="network unreachable")
        return _result("Unknown", error_message=f"unparseable ping output (exit code {proc.returncode})")

    sent, received, avg = parsed
    loss = round(100.0 * (sent - received) / sent, 2) if sent else 100.0
    return _result(
        classify(loss, partial_status),
        latency_ms=avg if received else None,
        packet_loss=loss, packets_sent=sent, packets_received=received,
    )


class MonitoringService:
    def __init__(self, repo, config, evaluator=None, ping=ping_host):
        self.repo = repo
        self.config = config
        self.evaluator = evaluator  # callable(device, result) -> any; set by the container
        self._ping = ping
        self._cycle_lock = threading.Lock()
        self._last_full_run = None

    # ------------------------------------------------------------- one device
    def check_device(self, device):
        """Run the check for one device. Does not persist anything."""
        if str(device.get("device_type", "")).lower() == "switch":
            if self.config.testing or self.config.auth_test_bypass:
                return _result("Unmonitored", error_message="GNS3 polling is disabled in test mode")
            return _check_gns3_node_status(device["hostname"])
        if not device.get("monitoring_enabled"):
            return _result("Unmonitored", error_message="monitoring disabled")
        method = device.get("monitoring_method")
        if method == "none":
            return _result("Unmonitored", error_message="device has no monitoring method")
        if method not in SUPPORTED_MONITORING_METHODS:
            return _result("Unknown", check_type=method if method in ("tcp", "snmp") else "icmp",
                           error_message=f"unsupported monitoring method: {method}")
        return self._ping(device["ip_address"], self.config.ping_count,
                          self.config.ping_timeout_seconds, self.config.partial_loss_status,
                          interval=self.config.ping_interval_seconds)

    def record_result(self, device, result):
        """Persist the log row and refresh the device's latest-state columns."""
        if result["status"] == "Unmonitored":
            return device
        self.repo.insert_monitoring_log({
            "device_id": device["id"], "status": result["status"],
            "latency_ms": result["latency_ms"], "packet_loss": result["packet_loss"],
            "checked_at": result["checked_at"], "check_type": result["check_type"],
            "packets_sent": result["packets_sent"], "packets_received": result["packets_received"],
            "error_message": result["error_message"], "metadata": {"ip_address": device["ip_address"]},
        })
        update = {
            "current_status": result["status"], "last_latency_ms": result["latency_ms"],
            "last_packet_loss": result["packet_loss"], "last_checked_at": result["checked_at"],
        }
        if result["status"] in ("Online", "Warning"):
            update["last_seen_at"] = result["checked_at"]
        return self.repo.update_device(device["id"], update) or device

    def check_and_record(self, device):
        result = self.check_device(device)
        self._process(device, result)
        return result

    def _process(self, device, result):
        updated = self.record_result(device, result)
        if self.evaluator is not None and result["status"] != "Unmonitored":
            try:
                self.evaluator(updated, result)
            except Exception:
                logger.exception("Rule evaluation failed for device %s", device.get("hostname"))

    # --------------------------------------------------------------- scheduling
    @staticmethod
    def _is_due(device, now):
        last = device.get("last_checked_at")
        if not last:
            return True
        interval = device.get("monitor_interval_seconds") or 30
        return (now - parse_ts(last)).total_seconds() >= interval * 0.9

    def run_cycle(self, only_due=True):
        """Check every monitored device (pings in parallel, DB writes sequential)."""
        devices = self.repo.list_devices(monitoring_enabled=None)
        devices = [
            device for device in devices
            if device.get("monitoring_enabled")
            or (
                not self.config.testing
                and not self.config.auth_test_bypass
                and str(device.get("device_type", "")).lower() == "switch"
            )
        ]
        now = utcnow()
        if only_due:
            devices = [d for d in devices if self._is_due(d, now)]
        if not devices:
            return []

        def probe(device):
            try:
                return self.check_device(device)
            except Exception:
                logger.exception("Check crashed for %s", device.get("hostname"))
                return _result("Unknown", error_message="check failed unexpectedly")

        workers = max(1, min(self.config.monitoring_workers, len(devices)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ping") as pool:
            results = list(pool.map(probe, devices))

        summary = []
        for device, result in zip(devices, results):
            try:
                self._process(device, result)
            except Exception:
                logger.exception("Could not persist result for %s", device.get("hostname"))
                continue
            summary.append({"device_id": device["id"], "hostname": device["hostname"],
                            "status": result["status"], "latency_ms": result["latency_ms"],
                            "packet_loss": result["packet_loss"]})
        return summary

    def refresh(self, min_age_seconds=5):
        """On-demand full check, rate-limited so dashboards cannot hammer the network."""
        with self._cycle_lock:
            now = utcnow()
            if self._last_full_run and (now - self._last_full_run).total_seconds() < min_age_seconds:
                return None
            self._last_full_run = now
            return self.run_cycle(only_due=False)

    # ------------------------------------------------------------------ summary
    def summary(self):
        devices = self.repo.list_devices()
        by_status = {}
        for d in devices:
            by_status[d["current_status"]] = by_status.get(d["current_status"], 0) + 1
        latencies = [float(d["last_latency_ms"]) for d in devices
                     if d.get("last_latency_ms") is not None and d["current_status"] in ("Online", "Warning")]
        active = self.repo.list_incidents(active_only=True, limit=200)
        by_sev = {"critical": 0, "warning": 0, "info": 0}
        for inc in active:
            by_sev[inc["severity"]] = by_sev.get(inc["severity"], 0) + 1
        return {
            "total_devices": len(devices),
            "monitored_devices": sum(1 for d in devices if d["monitoring_enabled"]),
            "by_status": by_status,
            "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "active_incidents": {"total": len(active), **by_sev},
        }


class MonitorRunner:
    """Background loop: monitoring cycle, automation retries, optional scheduled backups."""

    def __init__(self, monitoring, config, automation=None, backups=None):
        self.monitoring = monitoring
        self.config = config
        self.automation = automation
        self.backups = backups
        self._stop = threading.Event()
        self._thread = None
        self._last_scheduled_backup = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running:  # idempotent: never two loops in one process
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="netops-monitor", daemon=True)
        self._thread.start()
        logger.info("Monitoring loop started (tick=%ss)", self.config.monitoring_interval_seconds)
        return True

    def stop(self, timeout=5):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def tick(self):
        """One loop iteration; each part is isolated so one failure never stops the rest."""
        try:
            self.monitoring.run_cycle(only_due=True)
        except Exception:
            logger.exception("Monitoring cycle failed")
        if self.automation is not None:
            try:
                self.automation.retry_due()
            except Exception:
                logger.exception("Automation retry pass failed")
        self._maybe_scheduled_backups()

    def _maybe_scheduled_backups(self):
        every = self.config.backup_schedule_seconds
        if not every or self.backups is None:
            return
        now = utcnow()
        if self._last_scheduled_backup and (now - self._last_scheduled_backup).total_seconds() < every:
            return
        self._last_scheduled_backup = now
        try:
            self.backups.run_scheduled_backups()
        except Exception:
            logger.exception("Scheduled backups failed")

    def _loop(self):
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.config.monitoring_interval_seconds)
