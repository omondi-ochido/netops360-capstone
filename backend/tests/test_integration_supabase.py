"""Integration tests against a REAL Supabase project.

Skipped unless SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set. They require
database/schema.sql and database/seed.sql to have been applied. Run with:
    pytest -m integration
They create and clean up their own rows and never touch the seeded devices' history.
"""
import os
import uuid

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
        reason="Supabase credentials not configured",
    ),
]


@pytest.fixture(scope="module")
def sb_repo():
    from app.config import Config
    from app.services.supabase_service import create_repository

    return create_repository(Config.from_env(load_env_file=False))


@pytest.fixture
def temp_device(sb_repo):
    suffix = uuid.uuid4().hex[:8]
    device = sb_repo.create_device({"hostname": f"it-{suffix}", "ip_address": "10.255.%d.%d" % (
        int(suffix[:2], 16) % 250, int(suffix[2:4], 16) % 250 + 1), "device_type": "host"})
    yield device
    sb_repo.update_device(device["id"], {"is_active": False, "monitoring_enabled": False,
                                         "current_status": "Unmonitored"})


def test_ping_and_seed_data(sb_repo):
    assert sb_repo.ping() is True
    assert len(sb_repo.list_devices()) >= 9
    names = {r["name"] for r in sb_repo.list_rules()}
    assert {"Device Offline", "High Latency", "High Packet Loss"} <= names


def test_device_and_monitoring_log_persistence(sb_repo, temp_device):
    sb_repo.insert_monitoring_log({"device_id": temp_device["id"], "status": "Online",
                                   "latency_ms": 1.5, "packet_loss": 0, "check_type": "icmp"})
    logs = sb_repo.list_monitoring_logs(device_id=temp_device["id"])
    assert logs and logs[0]["status"] == "Online"


def test_database_rejects_invalid_values(sb_repo, temp_device):
    from app.utils.exceptions import ValidationError

    with pytest.raises(ValidationError):
        sb_repo.insert_monitoring_log({"device_id": temp_device["id"], "status": "Online",
                                       "packet_loss": 150})


def test_incident_rpc_prevents_duplicates_and_resolves(sb_repo, temp_device):
    rule = next(r for r in sb_repo.list_rules() if r["name"] == "High Latency")
    args = (temp_device["id"], rule["id"], "t", "d", "warning", "latency_ms", 250)
    first, created1 = sb_repo.open_incident(*args)
    second, created2 = sb_repo.open_incident(*args)
    assert created1 is True and created2 is False and first["id"] == second["id"]
    resolved, changed = sb_repo.resolve_incident(first["id"], 20, "test")
    assert changed is True and resolved["status"] == "resolved"
    assert resolved["duration_seconds"] is not None
    again, changed_again = sb_repo.resolve_incident(first["id"], 20, "test")
    assert changed_again is False


def test_empty_successful_backup_is_rejected_by_database(sb_repo, temp_device):
    with pytest.raises(Exception):
        sb_repo.client.table("config_backups").insert({
            "device_id": temp_device["id"], "status": "success", "configuration": "",
            "checksum": "a" * 64}).execute()
