import hashlib

import pytest

netmiko_exc = pytest.importorskip("netmiko.exceptions")

CONFIG_V1 = "set system host-name 'main-rtr'\nset interfaces ethernet eth0 address '192.168.100.10/24'\n"
CONFIG_V2 = CONFIG_V1 + "set service ssh port '22'\n"
INTERFACES = "Interface  IP Address\neth0  192.168.100.10/24\n"


class FakeConn:
    def __init__(self, config=CONFIG_V1, interfaces=INTERFACES):
        self.outputs = {"show configuration commands": config, "show interfaces": interfaces}
        self.disconnected = False

    def send_command(self, cmd):
        return self.outputs[cmd]

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def ssh(container):
    state = {"config": CONFIG_V1, "conns": [], "kwargs": []}

    def connect(**kwargs):
        state["kwargs"].append(kwargs)
        conn = FakeConn(state["config"])
        state["conns"].append(conn)
        return conn

    container.backups._connect = connect
    return state


def test_successful_backup_is_persisted_with_sha256(client, repo, dev, ssh):
    router = dev("main-rtr")
    resp = client.post("/api/devices/main-rtr/backup")
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["success"] is True and data["changed"] is True
    assert data["configuration"] == CONFIG_V1 and data["interfaces"] == INTERFACES
    expected = hashlib.sha256(CONFIG_V1.encode()).hexdigest()
    assert data["backup"]["checksum"] == expected
    stored = repo.get_backup(data["backup"]["id"])
    assert stored["configuration"] == CONFIG_V1 and stored["status"] == "success"
    assert stored["device_id"] == router["id"] and stored["backup_type"] == "manual"
    assert stored["interfaces_snapshot"] == INTERFACES
    assert "configuration" not in data["backup"]  # metadata view never carries config text
    assert ssh["conns"][0].disconnected is True


def test_switch_backup_requires_configuration_not_only_runtime_diagnostics(container, client, repo, dev):
    switch = dev("SW1")
    repo.update_device(switch["id"], {"ssh_enabled": True})
    container.config.switch_ssh_username = "switch-user"
    container.config.switch_ssh_password = "switch-password"

    class SwitchConn:
        def send_command(self, command):
            return {"cat /etc/network/interfaces": "", "brctl show 2>/dev/null || ovs-vsctl show 2>/dev/null": "",
                    "ip addr": "eth0: inet 192.0.2.1/24", "ip route": "default via 192.0.2.254"}[command]
        def disconnect(self):
            pass

    container.backups._connect = lambda **kwargs: SwitchConn()
    response = client.post("/api/devices/SW1/backup")
    assert response.status_code == 502
    assert response.get_json()["error"]["details"]["reason"] == "empty_configuration"
    assert repo.list_backups(device_id=switch["id"])[0]["status"] == "failed"


def test_credentials_come_from_config_not_code(container, client, ssh):
    client.post("/api/devices/main-rtr/backup")
    kwargs = ssh["kwargs"][0]
    assert kwargs["device_type"] == "vyos" and kwargs["host"] == "192.168.100.10"
    assert kwargs["username"] == container.config.ssh_username
    assert kwargs["password"] == container.config.ssh_password


def test_unchanged_and_changed_configuration_detection(client, ssh):
    first = client.post("/api/devices/main-rtr/backup").get_json()["data"]
    same = client.post("/api/devices/main-rtr/backup").get_json()["data"]
    assert first["changed"] is True and same["changed"] is False
    assert same["backup"]["checksum"] == first["backup"]["checksum"]
    ssh["config"] = CONFIG_V2
    diff = client.post("/api/devices/main-rtr/backup").get_json()["data"]
    assert diff["changed"] is True
    assert diff["backup"]["metadata"]["previous_backup_id"] == same["backup"]["id"]


def test_authentication_failure_is_recorded_and_safe(container, client, repo, dev):
    def deny(**kw):
        raise netmiko_exc.NetmikoAuthenticationException("Authentication to device failed for admin/pw")

    container.backups._connect = deny
    resp = client.post("/api/devices/main-rtr/backup")
    assert resp.status_code == 502
    err = resp.get_json()["error"]
    assert err["code"] == "backup_failed" and err["details"]["reason"] == "authentication_failed"
    assert "pw" not in resp.get_data(as_text=True)
    failed = repo.list_backups(device_id=dev("main-rtr")["id"])
    assert len(failed) == 1 and failed[0]["status"] == "failed" and failed[0]["checksum"] is None
    assert repo.latest_successful_backup(dev("main-rtr")["id"]) is None


def test_connection_timeout_is_recorded(container, client, repo):
    def timeout(**kw):
        raise netmiko_exc.NetmikoTimeoutException("timed out")

    container.backups._connect = timeout
    resp = client.post("/api/devices/main-rtr/backup")
    assert resp.status_code == 502
    assert resp.get_json()["error"]["details"]["reason"] == "connection_timeout"
    assert [b["status"] for b in repo.backups.values()] == ["failed"]


def test_empty_configuration_is_never_stored_as_success(container, client, repo, ssh):
    ssh["config"] = "   \n"
    resp = client.post("/api/devices/main-rtr/backup")
    assert resp.status_code == 502
    assert resp.get_json()["error"]["details"]["reason"] == "empty_configuration"
    assert all(b["status"] == "failed" for b in repo.backups.values())


def test_repository_refuses_successful_backup_without_config(repo, dev):
    from app.utils.exceptions import ValidationError

    with pytest.raises(ValidationError):
        repo.insert_backup({"device_id": dev("main-rtr")["id"], "status": "success",
                            "configuration": "", "checksum": "a" * 64})


def test_ssh_disabled_device_rejected(client, ssh):
    assert client.post("/api/devices/PC1/backup").status_code == 400
    assert ssh["conns"] == []


def test_missing_ssh_credentials_reported_without_attempt(container, client, ssh):
    container.config.ssh_password = ""
    resp = client.post("/api/devices/main-rtr/backup")
    assert resp.status_code == 503 and resp.get_json()["error"]["code"] == "ssh_not_configured"
    assert ssh["conns"] == []


def test_unknown_device_404(client, ssh):
    assert client.post("/api/devices/nope/backup").status_code == 404


def test_backup_history_and_retrieval(client, dev, ssh):
    router = dev("main-rtr")
    ids = [client.post("/api/devices/main-rtr/backup").get_json()["data"]["backup"]["id"]
           for _ in range(2)]
    hist = client.get(f"/api/devices/{router['id']}/backups").get_json()
    assert hist["pagination"]["count"] == 2
    assert all("configuration" not in row for row in hist["data"])
    assert len(client.get("/api/backups?limit=1").get_json()["data"]) == 1
    assert len(client.get(f"/api/backups?device_id={router['id']}&status=success").get_json()["data"]) == 2
    one = client.get(f"/api/backups/{ids[0]}").get_json()["data"]
    assert one["configuration"] == CONFIG_V1
    assert client.get("/api/backups/not-a-uuid").status_code == 400
    assert client.get("/api/backups/5b3b5b3b-5b3b-4b3b-8b3b-5b3b5b3b5b3b").status_code == 404


def test_backup_endpoints_require_bearer_auth(make_app, container):
    client = make_app(auth_test_bypass=False).test_client()
    assert client.get("/api/backups").status_code == 401
    assert client.get("/api/backups/5b3b5b3b-5b3b-4b3b-8b3b-5b3b5b3b5b3b").status_code == 401
    assert client.post("/api/devices/main-rtr/backup").status_code == 401


def test_scheduled_backups_only_touch_ssh_devices(container, repo, ssh):
    results = container.backups.run_scheduled_backups()
    assert results == [("main-rtr", "success")]
    assert next(iter(repo.backups.values()))["backup_type"] == "scheduled"


def test_scheduled_backup_failure_does_not_stop_other_devices(container, repo, dev):
    from app.utils.exceptions import ExternalServiceError

    repo.update_device(dev("SW1")["id"], {"ssh_enabled": True})
    attempted = []

    def run(identifier, backup_type):
        device = repo.get_device(identifier)
        attempted.append(device["hostname"])
        if device["hostname"] == "main-rtr":
            raise ExternalServiceError("temporary device failure")
        return {"success": True}

    container.backups.run_backup = run
    results = container.backups.run_scheduled_backups()
    assert attempted == ["main-rtr", "SW1"]
    assert results == [("main-rtr", "external_service_error"), ("SW1", "success")]


def test_scoped_n8n_token_lists_devices_and_records_metadata_only_backup(make_app, repo, container, ssh, dev):
    token = "long-random-machine-token-with-32-plus-characters"
    app = make_app(auth_test_bypass=False, n8n_backup_api_token=token)
    app.extensions["netops"].backups._connect = container.backups._connect
    client = app.test_client()

    assert client.get("/api/devices", headers={"Authorization": "Bearer " + token}).status_code == 200
    assert client.get("/api/devices", headers={"Authorization": "Bearer wrong-token"}).status_code == 401
    assert client.get("/api/backups", headers={"Authorization": "Bearer " + token}).status_code == 401

    response = client.post(
        f"/api/devices/{dev('main-rtr')['id']}/backup",
        json={"backup_type": "scheduled"},
        headers={"Authorization": "Bearer " + token, "X-N8N-Execution-Id": "schedule-exec-1"},
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["backup"]["backup_type"] == "scheduled"
    assert "configuration" not in data
    assert data["automation_log_id"]
    log = repo.get_automation_log(data["automation_log_id"])
    assert log["status"] == "success" and log["execution_id"] == "schedule-exec-1"
    assert log["response_payload"]["checksum"] == data["backup"]["checksum"]


def test_n8n_incident_backup_repeated_event_is_deduplicated(make_app, repo, container, dev, rule, ssh):
    token = "long-random-machine-token-with-32-plus-characters"
    app = make_app(auth_test_bypass=False, n8n_backup_api_token=token)
    app.extensions["netops"].backups._connect = container.backups._connect
    client = app.test_client()
    incident, _ = repo.open_incident(
        dev("main-rtr")["id"], rule("Device Offline")["id"], "Router offline", "Offline",
        "critical", "device_status", "Offline",
    )
    headers = {"Authorization": "Bearer " + token, "X-N8N-Execution-Id": "event-exec-1"}
    payload = {"backup_type": "incident_triggered", "incident_id": incident["id"]}
    path = f"/api/devices/{dev('main-rtr')['id']}/backup"
    first = client.post(path, json=payload, headers=headers)
    second = client.post(path, json=payload, headers=headers)
    assert first.status_code == 201 and second.status_code == 200
    assert second.get_json()["data"]["duplicate"] is True
    assert len(repo.list_backups(device_id=dev("main-rtr")["id"])) == 1
    assert len([x for x in repo.list_automation_logs() if x["trigger_type"] == "backup.incident_triggered"]) == 1


def test_n8n_scheduled_retry_reuses_execution_log(make_app, repo, container, dev, ssh):
    token = "long-random-machine-token-with-32-plus-characters"
    app = make_app(auth_test_bypass=False, n8n_backup_api_token=token)
    app.extensions["netops"].backups._connect = container.backups._connect
    client = app.test_client()
    calls = {"count": 0}
    connect = container.backups._connect

    def temporary_timeout(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise netmiko_exc.NetmikoTimeoutException("temporary connection timeout")
        return connect(**kwargs)

    app.extensions["netops"].backups._connect = temporary_timeout
    headers = {"Authorization": "Bearer " + token, "X-N8N-Execution-Id": "schedule-retry-1"}
    path = f"/api/devices/{dev('main-rtr')['id']}/backup"
    first = client.post(path, json={"backup_type": "scheduled"}, headers=headers)
    second = client.post(path, json={"backup_type": "scheduled"}, headers=headers)
    assert first.status_code == 502 and second.status_code == 201
    log = repo.list_automation_logs(device_id=dev("main-rtr")["id"], limit=10)[0]
    assert log["status"] == "success" and log["retry_count"] == 1
    assert len(repo.list_backups(device_id=dev("main-rtr")["id"])) == 2
