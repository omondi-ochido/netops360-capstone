def test_list_devices_is_backward_compatible(client):
    body = client.get("/api/devices").get_json()
    assert set(["devices", "timestamp"]) <= set(body)
    assert len(body["devices"]) == 9
    first = body["devices"][0]
    for key in ("hostname", "ip_address", "status", "latency", "packet_loss", "name", "ip"):
        assert key in first


def test_layer2_switches_are_never_reported_online(client):
    devices = {d["hostname"]: d for d in client.get("/api/devices").get_json()["devices"]}
    for name in ("MANAGEMENT-SW", "SW1", "SW2"):
        assert devices[name]["status"] == "Unmonitored"
        assert devices[name]["monitoring_enabled"] is False
    assert devices["main-rtr"]["status"] == "Unknown"  # not yet measured, not assumed Online


def test_get_device_by_uuid_and_by_hostname(client, dev):
    d = dev("main-rtr")
    assert client.get(f"/api/devices/{d['id']}").get_json()["data"]["hostname"] == "main-rtr"
    assert client.get("/api/devices/main-rtr").get_json()["data"]["id"] == d["id"]
    assert client.get("/api/devices/does-not-exist").status_code == 404


def test_create_device_persists(client, repo):
    resp = client.post("/api/devices", json={"hostname": "PC5", "ip_address": "192.168.10.15",
                                              "device_type": "host"})
    assert resp.status_code == 201
    assert repo.get_device_by_hostname("PC5")["current_status"] == "Unknown"


def test_create_device_rejects_invalid_ip(client):
    resp = client.post("/api/devices", json={"hostname": "bad", "ip_address": "999.1.1.1",
                                              "device_type": "host"})
    assert resp.status_code == 400


def test_create_device_rejects_unknown_fields_and_bad_types(client):
    base = {"hostname": "x1", "ip_address": "10.9.9.9", "device_type": "host"}
    assert client.post("/api/devices", json={**base, "is_admin": True}).status_code == 400
    assert client.post("/api/devices", json={**base, "device_type": "toaster"}).status_code == 400
    assert client.post("/api/devices", json={**base, "hostname": "bad host!"}).status_code == 400
    assert client.post("/api/devices", json={**base, "ssh_enabled": "yes"}).status_code == 400
    assert client.post("/api/devices", data="not json").status_code == 400


def test_duplicate_hostname_or_ip_conflict(client):
    dup_host = {"hostname": "pc1", "ip_address": "10.9.9.9", "device_type": "host"}
    assert client.post("/api/devices", json=dup_host).status_code == 409
    dup_ip = {"hostname": "other", "ip_address": "192.168.10.11", "device_type": "host"}
    assert client.post("/api/devices", json=dup_ip).status_code == 409


def test_invalid_pagination_rejected(client):
    assert client.get("/api/devices?limit=0").status_code == 400
    assert client.get("/api/devices?limit=abc").status_code == 400
    assert client.get("/api/devices?status=Bogus").status_code == 400


def test_patch_and_disable_monitoring(client, dev, repo):
    d = dev("PC1")
    resp = client.patch(f"/api/devices/{d['id']}", json={"monitoring_enabled": False})
    assert resp.status_code == 200
    updated = repo.get_device(d["id"])
    assert updated["monitoring_enabled"] is False
    assert updated["current_status"] == "Unmonitored"
    # re-enabling returns to Unknown until measured
    client.patch(f"/api/devices/{d['id']}", json={"monitoring_enabled": True})
    assert repo.get_device(d["id"])["current_status"] == "Unknown"


def test_cannot_enable_monitoring_without_method(client, dev):
    sw = dev("SW1")
    resp = client.patch(f"/api/devices/{sw['id']}", json={"monitoring_enabled": True})
    assert resp.status_code == 400


def test_delete_is_soft_and_keeps_history(client, dev, repo):
    d = dev("PC2")
    assert client.delete(f"/api/devices/{d['id']}").status_code == 200
    assert repo.get_device(d["id"])["is_active"] is False  # row still exists
    hostnames = [x["hostname"] for x in client.get("/api/devices").get_json()["devices"]]
    assert "PC2" not in hostnames
    assert client.get(f"/api/devices/{d['id']}").status_code == 404


def test_bearer_auth_protects_mutations(make_app):
    client = make_app(auth_test_bypass=False).test_client()
    body = {"hostname": "PC9", "ip_address": "10.1.1.9", "device_type": "host"}
    assert client.post("/api/devices", json=body).status_code == 401
    assert client.post("/api/devices", json=body, headers={"X-API-Key": "s3cret"}).status_code == 401
