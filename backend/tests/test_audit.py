def test_device_mutations_write_redacted_audit_records(client, repo):
    response = client.post("/api/devices", json={
        "hostname": "audit-host", "ip_address": "192.168.99.10", "device_type": "host",
        "site": "lab", "ssh_enabled": True,
    }, headers={"X-Request-ID": "trace-123"})
    assert response.status_code == 201
    device = response.get_json()["data"]
    assert response.headers["X-Request-ID"] == "trace-123"
    created = repo.audit_logs[-1]
    assert created["action"] == "created" and created["resource_type"] == "device"
    assert created["resource_id"] == device["id"] and created["request_id"] == "trace-123"
    assert "ssh_enabled" not in created["after_metadata"]

    updated = client.patch(f"/api/devices/{device['id']}", json={"site": "branch"})
    assert updated.status_code == 200
    changed = repo.audit_logs[-1]
    assert changed["action"] == "updated"
    assert changed["before_metadata"]["site"] == "lab"
    assert changed["after_metadata"]["site"] == "branch"

    assert client.delete(f"/api/devices/{device['id']}").status_code == 200
    assert repo.audit_logs[-1]["action"] == "deactivated"


def test_backup_detail_access_requires_api_key_and_audits_read(make_app, client, repo, dev):
    device = dev("main-rtr")
    backup = repo.insert_backup({"device_id": device["id"], "configuration": "set system host-name safe",
                                 "status": "success", "checksum": "a" * 64, "backup_type": "manual"})
    secured = make_app(api_key="secret").test_client()
    assert secured.get(f"/api/backups/{backup['id']}").status_code == 401
    response = secured.get(f"/api/backups/{backup['id']}", headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    row = repo.audit_logs[-1]
    assert row["action"] == "sensitive_contents_read"
    assert "configuration" not in row["after_metadata"]


def test_production_requires_api_key(make_app):
    from app.config import ConfigError
    import pytest

    with pytest.raises(ConfigError, match="API_KEY is required in production"):
        make_app(env="production", api_key="")
