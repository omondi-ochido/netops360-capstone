import pytest

from app import create_app
from app.repositories.memory_repository import InMemoryRepository

SEED_DEVICES = [
    ("main-rtr", "192.168.100.10", "router", "VyOS 1.5", True, True, "icmp", "Unknown"),
    ("MAIN-SERVER", "192.168.10.100", "server", "Linux", False, True, "icmp", "Unknown"),
    ("PC1", "192.168.10.11", "host", "VPCS", False, True, "icmp", "Unknown"),
    ("PC2", "192.168.10.12", "host", "VPCS", False, True, "icmp", "Unknown"),
    ("PC3", "192.168.10.13", "host", "VPCS", False, True, "icmp", "Unknown"),
    ("PC4", "192.168.10.14", "host", "VPCS", False, True, "icmp", "Unknown"),
    ("MANAGEMENT-SW", "192.168.100.2", "switch", "GNS3 Ethernet Switch", False, False, "none", "Unmonitored"),
    ("SW1", "192.168.10.2", "switch", "GNS3 Ethernet Switch", False, False, "none", "Unmonitored"),
    ("SW2", "192.168.10.3", "switch", "GNS3 Ethernet Switch", False, False, "none", "Unmonitored"),
]

DEFAULT_RULES = [
    {"name": "Device Offline", "metric": "device_status", "operator": "eq",
     "threshold": "Offline", "severity": "critical"},
    {"name": "High Latency", "metric": "latency_ms", "operator": "gt",
     "threshold": 100, "severity": "warning"},
    {"name": "High Packet Loss", "metric": "packet_loss", "operator": "gte",
     "threshold": 50, "severity": "warning"},
]

TEST_CONFIG = {
    "testing": True,
    "auth_test_bypass": True,
    "api_key": "",
    "n8n_webhook_url": "",
    "n8n_webhook_secret": "",
    "ssh_username": "admin",
    "ssh_password": "pw",
    "automation_synchronous": True,
    "automation_backoff_seconds": 30,
}


@pytest.fixture
def repo():
    r = InMemoryRepository()
    for host, ip, dtype, os_, ssh, mon, method, status in SEED_DEVICES:
        r.create_device({
            "hostname": host, "ip_address": ip, "device_type": dtype, "operating_system": os_,
            "ssh_enabled": ssh, "monitoring_enabled": mon, "monitoring_method": method,
            "current_status": status,
        })
    for rule in DEFAULT_RULES:
        r.create_rule({**rule, "enabled": True, "scope": "global", "device_id": None})
    return r


@pytest.fixture
def make_app(repo):
    def _make(**overrides):
        return create_app({**TEST_CONFIG, **overrides}, repository=repo)
    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def container(app):
    return app.extensions["netops"]


@pytest.fixture
def dev(repo):
    return lambda hostname: repo.get_device_by_hostname(hostname)


@pytest.fixture
def rule(repo):
    return lambda name: next(r for r in repo.list_rules() if r["name"] == name)
