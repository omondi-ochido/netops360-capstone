"""ICMP monitoring: ping execution, result classification, persistence, scheduling."""
import logging
import platform
import re
import subprocess
import threading
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

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
                      timeout=max(1.5, count * (timeout + 0.5)))
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
        self._snapshot_lock = threading.Lock()
        self._latest_snapshot = None
        self._persistence_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="monitor-persist",
        )

    # ------------------------------------------------------------- one device
    def check_device(self, device):
        """Run the check for one device. Does not persist anything."""
        if not device.get("monitoring_enabled"):
            return _result("Unmonitored", error_message="monitoring disabled")
        method = device.get("monitoring_method")
        if method == "none":
            return _result("Unmonitored", error_message="device has no monitoring method")
        if method not in SUPPORTED_MONITORING_METHODS:
            return _result("Unknown", check_type=method if method in ("tcp", "snmp") else "icmp",
                           error_message=f"unsupported monitoring method: {method}")
        return self._ping(device["ip_address"], 1, 1, self.config.partial_loss_status)

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
        configured_interval = device.get("monitor_interval_seconds") or 5
        interval = min(configured_interval, 5)
        return (now - parse_ts(last)).total_seconds() >= interval * 0.9

    def latest_snapshot(self, max_age_seconds=None):
        """Return a copy of the most recent in-memory inventory and poll results."""
        with self._snapshot_lock:
            snapshot = deepcopy(self._latest_snapshot)
        if snapshot is None or max_age_seconds is None:
            return snapshot
        age = (utcnow() - parse_ts(snapshot["timestamp"])).total_seconds()
        return snapshot if age < max_age_seconds else None

    def _cache_snapshot(self, inventory, checked_devices, results):
        previous = self.latest_snapshot()
        previous_by_id = {
            device["id"]: device for device in (previous or {}).get("devices", [])
        }
        snapshot_devices = []
        for device in inventory:
            row = dict(device)
            if (
                not self.config.testing
                and not self.config.auth_test_bypass
                and str(device.get("device_type", "")).lower() == "switch"
            ):
                row.update(monitoring_enabled=True, monitoring_method="icmp")
            cached = previous_by_id.get(device["id"])
            if cached and (
                device.get("monitoring_enabled")
                or str(device.get("device_type", "")).lower() == "switch"
            ):
                for field in ("current_status", "last_latency_ms", "last_packet_loss",
                              "last_checked_at", "last_seen_at"):
                    row[field] = cached.get(field)
            snapshot_devices.append(row)

        rows_by_id = {device["id"]: device for device in snapshot_devices}
        for device, result in zip(checked_devices, results):
            row = rows_by_id[device["id"]]
            row.update({
                "current_status": result["status"],
                "last_latency_ms": result["latency_ms"],
                "last_packet_loss": result["packet_loss"],
                "last_checked_at": result["checked_at"],
            })
            if result["status"] in ("Online", "Warning"):
                row["last_seen_at"] = result["checked_at"]

        with self._snapshot_lock:
            self._latest_snapshot = {
                "timestamp": now_iso(),
                "devices": snapshot_devices,
            }

    def _persist_batch(self, checked_devices, results):
        def persist_results():
            for device, result in zip(checked_devices, results):
                try:
                    self._process(device, result)
                except Exception:
                    logger.exception("Could not persist result for %s", device.get("hostname"))

        cache_enabled_rules = getattr(self.repo, "cache_enabled_rules", None)
        if self.evaluator is not None and callable(cache_enabled_rules):
            try:
                with cache_enabled_rules():
                    persist_results()
                return
            except Exception:
                logger.exception("Could not cache active rules for monitoring batch")
        persist_results()

    def run_cycle(self, only_due=True, persist_async=False, use_snapshot=False, refresh=False):
        """Check devices in parallel and optionally persist results off-thread."""
        if refresh:
            snapshot = self.latest_snapshot(max_age_seconds=2)
            if snapshot is not None:
                return [
                    {"device_id": device["id"], "hostname": device["hostname"],
                     "status": device["current_status"],
                     "latency_ms": device.get("last_latency_ms"),
                     "packet_loss": device.get("last_packet_loss")}
                    for device in snapshot["devices"] if device.get("monitoring_enabled")
                ]
        snapshot = self.latest_snapshot() if use_snapshot else None
        inventory = (
            snapshot["devices"] if snapshot is not None
            else self.repo.list_devices(monitoring_enabled=None)
        )
        poll_switches = not self.config.testing and not self.config.auth_test_bypass
        devices = []
        for device in inventory:
            is_switch = str(device.get("device_type", "")).lower() == "switch"
            if not device.get("monitoring_enabled") and not (poll_switches and is_switch):
                continue
            devices.append(
                {**device, "monitoring_enabled": True, "monitoring_method": "icmp"}
                if poll_switches and is_switch else device
            )
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

        with ThreadPoolExecutor(max_workers=12, thread_name_prefix="ping") as pool:
            results = list(pool.map(probe, devices))

        self._cache_snapshot(inventory, devices, results)
        if persist_async:
            self._persistence_executor.submit(self._persist_batch, devices, results)
            return [
                {"device_id": device["id"], "hostname": device["hostname"],
                 "status": result["status"], "latency_ms": result["latency_ms"],
                 "packet_loss": result["packet_loss"]}
                for device, result in zip(devices, results)
            ]

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

    def refresh(self, min_age_seconds=5, persist_async=False, use_snapshot=True):
        """On-demand full check, rate-limited so dashboards cannot hammer the network."""
        with self._cycle_lock:
            if self.latest_snapshot(max_age_seconds=2) is not None:
                return None
            now = utcnow()
            if self._last_full_run and (now - self._last_full_run).total_seconds() < min_age_seconds:
                return None
            self._last_full_run = now
            return self.run_cycle(
                only_due=False, persist_async=persist_async, use_snapshot=use_snapshot,
                refresh=True,
            )

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
        logger.info("Monitoring loop started (tick=%ss)",
                    min(self.config.monitoring_interval_seconds, 5))
        return True

    def stop(self, timeout=5):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def tick(self, skip_monitoring=False):
        """One loop iteration; each part is isolated so one failure never stops the rest."""
        if not skip_monitoring:
            try:
                self.monitoring.run_cycle(only_due=True, persist_async=True)
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
        initial_cycle_succeeded = False
        try:
            self.monitoring.refresh(min_age_seconds=0, persist_async=True)
            initial_cycle_succeeded = True
        except Exception:
            logger.exception("Initial monitoring cycle failed")
        self.tick(skip_monitoring=initial_cycle_succeeded)
        while not self._stop.is_set():
            self._stop.wait(min(self.config.monitoring_interval_seconds, 5))
            if not self._stop.is_set():
                self.tick()
