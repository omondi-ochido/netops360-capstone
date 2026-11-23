from datetime import timedelta

from app.utils.timeutil import utcnow
from tests.helpers import ping_result

OFFLINE = ping_result("Offline", None, 100.0)
ONLINE = ping_result("Online", 1.0, 0.0)


def test_incident_created_with_correct_associations(container, repo, dev, rule):
    pc = dev("PC1")
    summary = container.rules.evaluate_and_apply(pc, OFFLINE)
    incidents = repo.list_incidents()
    offline = next(i for i in incidents if i["rule_id"] == rule("Device Offline")["id"])
    assert offline["device_id"] == pc["id"]
    assert offline["severity"] == "critical" and offline["status"] == "open"
    assert offline["trigger_metric"] == "device_status" and offline["trigger_value"] == "Offline"
    assert "PC1" in offline["title"]
    assert offline["id"] in summary["opened"]


def test_duplicate_active_incidents_are_prevented(container, repo, dev):
    pc = dev("PC1")
    first = container.rules.evaluate_and_apply(pc, OFFLINE)
    before = repo.list_incidents(limit=100)
    second = container.rules.evaluate_and_apply(pc, OFFLINE)
    third = container.rules.evaluate_and_apply(pc, OFFLINE)
    after = repo.list_incidents(limit=100)
    assert len(before) == len(after) == 2  # Device Offline + High Packet Loss, once each
    assert first["opened"] and not second["opened"] and not third["opened"]
    assert len(second["touched"]) == 2  # last_observed_at refreshed instead


def test_repository_open_incident_is_idempotent(repo, dev, rule):
    pc, r = dev("PC1"), rule("Device Offline")
    args = (pc["id"], r["id"], "t", "d", "critical", "device_status", "Offline")
    inc1, created1 = repo.open_incident(*args)
    inc2, created2 = repo.open_incident(*args)
    assert created1 is True and created2 is False and inc1["id"] == inc2["id"]


def test_new_incident_allowed_after_previous_resolved(container, repo, dev):
    pc = dev("PC1")
    container.rules.evaluate_and_apply(pc, OFFLINE)
    container.rules.evaluate_and_apply(pc, ONLINE)
    again = container.rules.evaluate_and_apply(pc, OFFLINE)
    assert len(again["opened"]) == 2
    assert len(repo.list_incidents(limit=100)) == 4  # history preserved


def test_automatic_resolution_on_recovery(container, repo, dev, rule):
    pc = dev("PC1")
    container.rules.evaluate_and_apply(pc, OFFLINE)
    summary = container.rules.evaluate_and_apply(pc, ONLINE)
    assert len(summary["resolved"]) == 2
    inc = next(i for i in repo.list_incidents() if i["rule_id"] == rule("Device Offline")["id"])
    assert inc["status"] == "resolved" and inc["resolved_at"]
    assert inc["resolution_value"] == "Online"
    assert inc["resolution_reason"]


def test_recovery_does_not_resolve_unrelated_incidents(container, repo, dev):
    pc1, pc2 = dev("PC1"), dev("PC2")
    container.rules.evaluate_and_apply(pc1, OFFLINE)
    container.rules.evaluate_and_apply(pc2, OFFLINE)
    container.rules.evaluate_and_apply(pc1, ONLINE)
    active = repo.list_incidents(active_only=True, limit=100)
    assert {i["device_id"] for i in active} == {pc2["id"]}


def test_latency_incident_untouched_while_latency_unknown(container, repo, dev):
    pc = dev("PC1")
    container.rules.evaluate_and_apply(pc, ping_result("Online", 500.0, 0.0))
    assert len(repo.list_incidents(active_only=True)) == 1
    container.rules.evaluate_and_apply(pc, OFFLINE)  # no latency available: must not resolve it
    latency_inc = [i for i in repo.list_incidents(limit=100) if i["trigger_metric"] == "latency_ms"]
    assert latency_inc[0]["status"] == "open"


def test_unknown_and_unmonitored_results_do_not_open_or_resolve(container, repo, dev):
    pc = dev("PC1")
    container.rules.evaluate_and_apply(pc, OFFLINE)
    skipped = container.rules.evaluate_and_apply(pc, ping_result("Unknown", None, None))
    assert skipped["skipped"]
    assert len(repo.list_incidents(active_only=True)) == 2


def test_duration_is_calculated_on_resolution(container, repo, dev):
    pc = dev("PC1")
    container.rules.evaluate_and_apply(pc, OFFLINE)
    for inc in repo.incidents.values():
        inc["triggered_at"] = (utcnow() - timedelta(seconds=120)).isoformat()
    container.rules.evaluate_and_apply(pc, ONLINE)
    durations = [i["duration_seconds"] for i in repo.list_incidents()]
    assert all(120 <= d < 130 for d in durations)


def test_acknowledge_flow_via_api(client, container, repo, dev):
    container.rules.evaluate_and_apply(dev("PC1"), OFFLINE)
    iid = repo.list_incidents(severity="critical")[0]["id"]
    resp = client.post(f"/api/incidents/{iid}/acknowledge")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["status"] == "acknowledged" and data["acknowledged_at"]
    # still counts as active: no duplicate is opened while acknowledged
    container.rules.evaluate_and_apply(dev("PC1"), OFFLINE)
    assert len(repo.list_incidents(severity="critical", limit=100)) == 1
    # acknowledging again is idempotent
    assert client.post(f"/api/incidents/{iid}/acknowledge").status_code == 200


def test_manual_resolve_and_cannot_acknowledge_resolved(client, container, repo, dev):
    container.rules.evaluate_and_apply(dev("PC1"), OFFLINE)
    iid = repo.list_incidents(severity="critical")[0]["id"]
    resolved = client.post(f"/api/incidents/{iid}/resolve").get_json()["data"]
    assert resolved["status"] == "resolved" and resolved["duration_seconds"] is not None
    assert client.post(f"/api/incidents/{iid}/acknowledge").status_code == 409
    assert client.post(f"/api/incidents/{iid}/resolve").status_code == 200  # idempotent


def test_incident_api_filters_and_errors(client, container, repo, dev):
    pc1, pc2 = dev("PC1"), dev("PC2")
    container.rules.evaluate_and_apply(pc1, OFFLINE)
    container.rules.evaluate_and_apply(pc2, ping_result("Online", 300.0, 0.0))
    assert len(client.get("/api/incidents").get_json()["data"]) == 3
    assert len(client.get("/api/incidents?severity=critical").get_json()["data"]) == 1
    assert len(client.get("/api/incidents?device_id=PC2").get_json()["data"]) == 1
    assert len(client.get("/api/incidents?status=open&active=true").get_json()["data"]) == 3
    assert client.get("/api/incidents?status=bogus").status_code == 400
    assert client.get("/api/incidents?rule_id=nope").status_code == 400
    assert client.get("/api/incidents/not-a-uuid").status_code == 400
    assert client.get("/api/incidents/5b3b5b3b-5b3b-4b3b-8b3b-5b3b5b3b5b3b").status_code == 404


def test_end_to_end_monitoring_cycle_opens_and_resolves(container, repo):
    state = {"down": True}

    def ping(ip, *a, **k):
        if ip == "192.168.100.10":
            return ping_result("Offline", None, 100.0) if state["down"] else ping_result()
        return ping_result()

    container.monitoring._ping = ping
    container.monitoring.run_cycle(only_due=False)
    active = repo.list_incidents(active_only=True)
    assert {i["severity"] for i in active} == {"critical", "warning"}
    router = repo.get_device_by_hostname("main-rtr")
    assert router["current_status"] == "Offline"
    state["down"] = False
    container.monitoring.run_cycle(only_due=False)
    assert repo.list_incidents(active_only=True) == []
