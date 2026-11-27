import hashlib
import hmac
import json

import pytest
import requests

from tests.helpers import ping_result

OFFLINE = ping_result("Offline", None, 100.0)
ONLINE = ping_result("Online", 1.0, 0.0)
URL = "http://n8n.test/webhook/netops-incident"


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {"executionId": "exec-42"}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, behaviour=None):
        self.calls = []
        self.behaviour = behaviour or (lambda: Resp(200))

    def __call__(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        result = self.behaviour()
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def http(container):
    container.config.n8n_webhook_url = URL
    container.config.n8n_webhook_secret = "whsec"
    fake = FakeHttp()
    container.automation._post = fake
    return fake


def trigger_offline(container, dev, host="PC1"):
    return container.rules.evaluate_and_apply(dev(host), OFFLINE)


def test_incident_opened_event_is_delivered_and_logged(container, repo, dev, http):
    trigger_offline(container, dev)
    logs = repo.list_automation_logs(limit=100)
    assert len(logs) == 2  # one per opened incident (offline + packet loss)
    assert all(l["status"] == "running" and l["trigger_type"] == "incident.opened" for l in logs)
    log = next(l for l in logs if l["request_payload"]["rule"]["name"] == "Device Offline")
    assert log["execution_id"] == "exec-42" and log["response_payload"]["status_code"] == 200
    assert log["incident_id"] and log["device_id"] == dev("PC1")["id"]
    payload = log["request_payload"]
    assert payload["event_type"] == "incident.opened"
    assert payload["device"]["hostname"] == "PC1" and payload["device"]["ip_address"] == "192.168.10.11"
    assert payload["incident"]["severity"] == "critical" and payload["incident"]["status"] == "open"
    assert payload["rule"]["metric"] == "device_status"
    assert payload["incident"]["trigger_value"] == "Offline"


def test_request_is_signed_and_uses_configured_timeout(container, dev, http):
    trigger_offline(container, dev)
    call = http.calls[0]
    expected = hmac.new(b"whsec", call["data"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-NetOps-Signature"] == f"sha256={expected}"
    assert call["headers"]["X-NetOps-Webhook-Token"] == "whsec"
    assert call["headers"]["X-NetOps-Event"] == "incident.opened"
    assert call["url"] == URL and call["timeout"] == container.config.automation_timeout_seconds
    assert b"whsec" not in call["data"]  # the secret is never part of the payload


def test_resolved_and_acknowledged_events(container, client, repo, dev, http):
    trigger_offline(container, dev)
    iid = repo.list_incidents(severity="critical")[0]["id"]
    client.post(f"/api/incidents/{iid}/acknowledge")
    container.rules.evaluate_and_apply(dev("PC1"), ONLINE)
    types = sorted(l["trigger_type"] for l in repo.list_automation_logs(limit=100))
    assert types.count("incident.opened") == 2
    assert types.count("incident.acknowledged") == 1
    assert types.count("incident.resolved") == 2


def test_failed_webhook_is_logged_and_incident_survives(container, repo, dev, http):
    http.behaviour = lambda: Resp(500, {"error": "boom"})
    trigger_offline(container, dev)
    assert len(repo.list_incidents(active_only=True)) == 2  # incident persisted regardless
    log = repo.list_automation_logs(limit=1)[0]
    assert log["status"] == "failed" and "500" in log["error_message"]


def test_n8n_unreachable_never_blocks_incident_creation(container, repo, dev, http):
    http.behaviour = lambda: requests.ConnectionError("refused")
    summary = trigger_offline(container, dev)
    assert len(summary["opened"]) == 2
    log = repo.list_automation_logs(limit=1)[0]
    assert log["status"] == "failed" and "unreachable" in log["error_message"]
    assert URL not in (log["error_message"] or "")


def test_timeout_is_recorded(container, repo, dev, http):
    http.behaviour = lambda: requests.Timeout("slow")
    trigger_offline(container, dev)
    assert "timed out" in repo.list_automation_logs(limit=1)[0]["error_message"]


def test_automation_bug_cannot_break_incident_flow(container, repo, dev, http):
    def explode(*a, **k):
        raise RuntimeError("automation bug")

    container.automation.notify = explode
    summary = trigger_offline(container, dev)
    assert len(summary["opened"]) == 2 and len(repo.list_incidents(active_only=True)) == 2


def test_database_failure_while_logging_does_not_break_incidents(container, repo, dev, http):
    original = repo.insert_automation_log

    def broken(data):
        from app.utils.exceptions import DatabaseError
        raise DatabaseError()

    repo.insert_automation_log = broken
    summary = trigger_offline(container, dev)
    repo.insert_automation_log = original
    assert len(summary["opened"]) == 2


def test_not_configured_means_no_log_noise(container, repo, dev):
    trigger_offline(container, dev)
    assert repo.list_automation_logs() == []


def test_flood_guard_suppresses_duplicate_events(container, repo, dev, rule, http):
    trigger_offline(container, dev)
    for _ in range(3):
        trigger_offline(container, dev)  # condition persists: no new incident, no new webhook
    assert len(repo.list_automation_logs(limit=100)) == 2 and len(http.calls) == 2
    incident = repo.list_incidents(severity="critical")[0]
    pc, r = dev("PC1"), rule("Device Offline")
    assert container.automation.notify("incident.opened", incident, pc, r) is None


def test_manual_retry_endpoint(client, container, repo, dev, http):
    http.behaviour = lambda: Resp(503)
    trigger_offline(container, dev)
    failed = repo.list_automation_logs(status="failed", limit=1)[0]
    http.behaviour = lambda: Resp(200)
    resp = client.post(f"/api/automation/retry/{failed['id']}")
    assert resp.status_code == 202
    after = repo.get_automation_log(failed["id"])
    assert after["status"] == "running" and after["retry_count"] == 1
    assert client.post(f"/api/automation/retry/{failed['id']}").status_code == 409  # awaiting callback
    assert client.post("/api/automation/retry/not-a-uuid").status_code == 400
    assert client.post("/api/automation/retry/5b3b5b3b-5b3b-4b3b-8b3b-5b3b5b3b5b3b").status_code == 404


def test_retry_count_increments_on_repeated_failure(client, container, repo, dev, http):
    http.behaviour = lambda: Resp(500)
    trigger_offline(container, dev)
    log = repo.list_automation_logs(limit=1)[0]
    client.post(f"/api/automation/retry/{log['id']}")
    client.post(f"/api/automation/retry/{log['id']}")
    assert repo.get_automation_log(log["id"])["retry_count"] == 2


def test_retry_due_honours_backoff_and_max_retries(container, repo, dev, http):
    http.behaviour = lambda: Resp(500)
    trigger_offline(container, dev)
    assert container.automation.retry_due() == 0  # backoff (30s) has not elapsed
    container.config.automation_backoff_seconds = 0
    http.behaviour = lambda: Resp(200)
    assert container.automation.retry_due() == 2
    assert all(l["status"] == "running" for l in repo.list_automation_logs(limit=100))
    assert container.automation.retry_due() == 0  # nothing left to retry


def test_retries_stop_at_max(container, repo, dev, http):
    http.behaviour = lambda: Resp(500)
    container.config.automation_backoff_seconds = 0
    container.config.automation_max_retries = 2
    trigger_offline(container, dev)
    for _ in range(6):
        container.automation.retry_due()
    assert max(l["retry_count"] for l in repo.list_automation_logs(limit=100)) == 2


def test_automation_logs_api_filters_and_auth(make_app, container, repo, dev, http):
    trigger_offline(container, dev)
    c = make_app(auth_test_bypass=False).test_client()
    assert c.get("/api/automation/logs").status_code == 401
    c = make_app().test_client()
    assert len(c.get("/api/automation/logs").get_json()["data"]) == 2
    assert len(c.get("/api/automation/logs?status=failed").get_json()["data"]) == 0
    assert c.get("/api/automation/logs?status=bogus").status_code == 400
    assert c.get("/api/automation/logs?incident_id=zzz").status_code == 400
    assert c.post("/api/automation/retry/x").status_code == 400


def test_callback_completes_original_log_and_replay_is_idempotent(client, container, repo, dev, http):
    trigger_offline(container, dev)
    log = repo.list_automation_logs(limit=1)[0]
    body = json.dumps({"automation_log_id": log["id"], "execution_id": "exec-final",
                       "status": "success", "response_summary": "Discord accepted alert"},
                      separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    response = client.post("/api/automation/callback", data=body, content_type="application/json",
                           headers={"X-NetOps-Signature": signature})
    assert response.status_code == 200
    completed = repo.get_automation_log(log["id"])
    assert completed["status"] == "success" and completed["execution_id"] == "exec-final"
    assert completed["response_payload"]["summary"] == "Discord accepted alert"
    assert completed["completed_at"]
    assert client.post("/api/automation/callback", data=body, content_type="application/json",
                       headers={"X-NetOps-Signature": signature}).status_code == 200


def test_callback_rejects_bad_signature_unknown_id_and_conflicting_replay(client, container, repo, dev, http):
    trigger_offline(container, dev)
    log = repo.list_automation_logs(limit=1)[0]
    body = json.dumps({"automation_log_id": log["id"], "execution_id": "exec-final",
                       "status": "failed", "error_details": "provider rejected alert"}).encode()
    assert client.post("/api/automation/callback", data=body, content_type="application/json",
                       headers={"X-NetOps-Signature": "sha256=invalid"}).status_code == 401
    malformed = json.dumps({"automation_log_id": log["id"], "execution_id": "exec-final",
                            "status": "accepted"}).encode()
    malformed_sig = "sha256=" + hmac.new(b"whsec", malformed, hashlib.sha256).hexdigest()
    assert client.post("/api/automation/callback", data=malformed, content_type="application/json",
                       headers={"X-NetOps-Signature": malformed_sig}).status_code == 400
    valid = "sha256=" + hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    assert client.post("/api/automation/callback", data=body, content_type="application/json",
                       headers={"X-NetOps-Signature": valid}).status_code == 200
    conflict = json.dumps({"automation_log_id": log["id"], "execution_id": "another-exec",
                           "status": "success"}).encode()
    signature = "sha256=" + hmac.new(b"whsec", conflict, hashlib.sha256).hexdigest()
    assert client.post("/api/automation/callback", data=conflict, content_type="application/json",
                       headers={"X-NetOps-Signature": signature}).status_code == 409
    unknown = json.dumps({"automation_log_id": "5b3b5b3b-5b3b-4b3b-8b3b-5b3b5b3b5b3b",
                          "execution_id": "exec", "status": "success"}).encode()
    signature = "sha256=" + hmac.new(b"whsec", unknown, hashlib.sha256).hexdigest()
    assert client.post("/api/automation/callback", data=unknown, content_type="application/json",
                       headers={"X-NetOps-Signature": signature}).status_code == 404


def test_incident_callback_cannot_complete_backup_workflow_log(client, container, repo, dev, http):
    backup_log = repo.insert_automation_log({
        "workflow_name": "n8n-config-backup", "trigger_type": "backup.scheduled",
        "device_id": dev("main-rtr")["id"], "status": "running",
    })
    body = json.dumps({"automation_log_id": backup_log["id"], "execution_id": "wrong-flow",
                       "status": "success"}).encode()
    signature = "sha256=" + hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    response = client.post("/api/automation/callback", data=body, content_type="application/json",
                           headers={"X-NetOps-Signature": signature})
    assert response.status_code == 409
    assert repo.get_automation_log(backup_log["id"])["status"] == "running"
