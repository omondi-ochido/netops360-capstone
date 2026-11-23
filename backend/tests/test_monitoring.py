import subprocess
from types import SimpleNamespace

from app.services.monitoring_service import (
    MonitoringService, build_ping_command, classify, parse_ping_output, ping_host,
)
from tests.helpers import ping_result

LINUX_OK = """PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.5 ms

--- 10.0.0.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2003ms
rtt min/avg/max/mdev = 0.400/0.500/0.600/0.080 ms
"""
LINUX_PARTIAL = """--- 10.0.0.1 ping statistics ---
3 packets transmitted, 2 received, 33.3333% packet loss, time 2003ms
rtt min/avg/max/mdev = 1.000/2.000/3.000/0.500 ms
"""
LINUX_DOWN = """--- 10.0.0.1 ping statistics ---
3 packets transmitted, 0 received, +3 errors, 100% packet loss, time 2050ms
"""
MAC_OK = """--- 10.0.0.1 ping statistics ---
3 packets transmitted, 3 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 1.1/2.2/3.3/0.4 ms
"""


def runner(stdout, returncode=0):
    return lambda cmd, **kw: SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_parse_linux_and_macos_output():
    assert parse_ping_output(LINUX_OK) == (3, 3, 0.5)
    assert parse_ping_output(MAC_OK) == (3, 3, 2.2)
    assert parse_ping_output(LINUX_DOWN) == (3, 0, None)
    assert parse_ping_output("garbage") is None


def test_command_is_a_list_never_a_shell_string():
    cmd = build_ping_command("10.0.0.1", 3, 2, system="Linux")
    assert cmd == ["ping", "-c", "3", "-W", "2", "10.0.0.1"]
    assert build_ping_command("10.0.0.1", 3, 2, system="Darwin")[4] == "2000"


def test_successful_ping():
    r = ping_host("10.0.0.1", runner=runner(LINUX_OK), system="Linux")
    assert (r["status"], r["packet_loss"], r["latency_ms"]) == ("Online", 0.0, 0.5)
    assert r["packets_sent"] == 3 and r["packets_received"] == 3


def test_failed_ping_is_offline_with_full_packet_loss():
    r = ping_host("10.0.0.1", runner=runner(LINUX_DOWN, 1), system="Linux")
    assert r["status"] == "Offline" and r["packet_loss"] == 100.0 and r["latency_ms"] is None


def test_partial_packet_loss_is_measured_not_assumed():
    r = ping_host("10.0.0.1", runner=runner(LINUX_PARTIAL), system="Linux")
    assert r["packet_loss"] == 33.33 and r["status"] == "Warning" and r["latency_ms"] == 2.0
    r2 = ping_host("10.0.0.1", partial_status="Online", runner=runner(LINUX_PARTIAL), system="Linux")
    assert r2["status"] == "Online"  # configurable rule


def test_subprocess_timeout_is_handled():
    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    r = ping_host("10.0.0.1", runner=hang, system="Linux")
    assert r["status"] == "Unknown" and "timed out" in r["error_message"]


def test_missing_ping_binary_is_handled():
    def missing(cmd, **kw):
        raise FileNotFoundError

    assert ping_host("10.0.0.1", runner=missing, system="Linux")["status"] == "Unknown"


def test_invalid_ip_never_reaches_subprocess():
    called = []
    r = ping_host("10.0.0.1; rm -rf /", runner=lambda *a, **k: called.append(1), system="Linux")
    assert r["status"] == "Unknown" and not called


def test_unsupported_platform_is_reported():
    assert ping_host("10.0.0.1", system="Windows")["status"] == "Unknown"


def test_classify():
    assert classify(0) == "Online" and classify(10) == "Warning" and classify(100) == "Offline"


def test_monitoring_disabled_and_unsupported_method(repo, container, dev):
    svc = container.monitoring
    assert svc.check_device(dev("SW1"))["status"] == "Unmonitored"
    pc = dev("PC1")
    assert svc.check_device({**pc, "monitoring_enabled": False})["status"] == "Unmonitored"
    r = svc.check_device({**pc, "monitoring_method": "snmp"})
    assert r["status"] == "Unknown" and "unsupported" in r["error_message"]


def test_results_are_persisted(repo, container, dev):
    container.monitoring._ping = lambda *a, **k: ping_result("Online", 2.5, 0.0)
    pc = dev("PC1")
    container.monitoring.check_and_record(pc)
    logs = repo.list_monitoring_logs(device_id=pc["id"])
    assert len(logs) == 1 and logs[0]["latency_ms"] == 2.5
    updated = repo.get_device(pc["id"])
    assert updated["current_status"] == "Online" and updated["last_seen_at"]


def test_offline_device_updates_state_but_not_last_seen(repo, container, dev):
    container.monitoring._ping = lambda *a, **k: ping_result("Offline", None, 100.0)
    pc = dev("PC3")
    container.monitoring.check_and_record(pc)
    updated = repo.get_device(pc["id"])
    assert updated["current_status"] == "Offline" and updated["last_seen_at"] is None


def test_unmonitored_devices_are_not_logged(repo, container, dev):
    container.monitoring.check_and_record(dev("SW1"))
    assert repo.monitoring_logs == []


def test_run_cycle_checks_only_monitored_devices(repo, container):
    container.monitoring._ping = lambda *a, **k: ping_result("Online", 1.0, 0.0)
    summary = container.monitoring.run_cycle()
    assert len(summary) == 6  # 3 switches excluded
    assert len(repo.monitoring_logs) == 6
    # nothing is due immediately afterwards
    assert container.monitoring.run_cycle() == []


def test_run_cycle_survives_a_crashing_check(repo, container):
    calls = {"n": 0}

    def flaky(ip, *a, **k):
        calls["n"] += 1
        if ip == "192.168.10.11":
            raise RuntimeError("boom")
        return ping_result("Online", 1.0, 0.0)

    container.monitoring._ping = flaky
    summary = container.monitoring.run_cycle()
    assert len(summary) == 6
    assert next(s for s in summary if s["hostname"] == "PC1")["status"] == "Unknown"


def test_history_summary_and_latest_endpoints(client, repo, container, dev):
    container.monitoring._ping = lambda *a, **k: ping_result("Online", 4.0, 0.0)
    container.monitoring.run_cycle()
    pc = dev("PC1")
    hist = client.get(f"/api/monitoring/history?device_id={pc['id']}&limit=5").get_json()
    assert hist["pagination"]["count"] == 1
    assert client.get("/api/monitoring/history?device_id=PC1").get_json()["pagination"]["count"] == 1
    assert client.get("/api/monitoring/history?since=not-a-date").status_code == 400
    assert client.get("/api/monitoring/history?status=Bogus").status_code == 400
    latest = client.get("/api/monitoring/latest").get_json()["data"]
    assert len(latest) == 9
    summary = client.get("/api/monitoring/summary").get_json()["data"]
    assert summary["by_status"]["Online"] == 6 and summary["by_status"]["Unmonitored"] == 3
    assert summary["average_latency_ms"] == 4.0


def test_refresh_is_rate_limited(container):
    calls = []
    container.monitoring._ping = lambda *a, **k: calls.append(1) or ping_result()
    assert container.monitoring.refresh() is not None
    assert container.monitoring.refresh() is None  # within min age
    assert len(calls) == 6


def test_monitor_runner_is_idempotent_and_stoppable(container):
    runner_ = container.monitor_runner
    container.monitoring._ping = lambda *a, **k: ping_result()
    container.config.monitoring_interval_seconds = 5
    assert runner_.start() is True
    assert runner_.start() is False  # never two loops
    runner_.stop()
    assert not runner_.running
