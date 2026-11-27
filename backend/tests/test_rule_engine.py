import pytest

from app.services.rule_engine import RuleEngine, compare, validate_rule
from app.utils.exceptions import ValidationError
from tests.helpers import ping_result


@pytest.fixture
def engine(repo):
    return RuleEngine(repo)


@pytest.mark.parametrize("op,a,b,expected", [
    ("eq", 5, 5, True), ("eq", 5, 6, False),
    ("neq", 5, 6, True), ("neq", 5, 5, False),
    ("gt", 6, 5, True), ("gt", 5, 5, False),
    ("gte", 5, 5, True), ("gte", 4, 5, False),
    ("lt", 4, 5, True), ("lt", 5, 5, False),
    ("lte", 5, 5, True), ("lte", 6, 5, False),
])
def test_all_operators(op, a, b, expected):
    assert compare(op, a, b) is expected


def test_compare_rejects_unknown_operator_and_type_mismatch():
    with pytest.raises(ValidationError):
        compare("regex", 1, 1)
    with pytest.raises(ValidationError):
        compare("gt", "Offline", 5)


def test_offline_rule_triggers(engine, repo):
    result = engine.evaluate(ping_result("Offline", None, 100.0), repo.list_rules(enabled_only=True))
    triggered = {e["rule"]["name"] for e in result if e["triggered"]}
    assert triggered == {"Device Offline", "High Packet Loss"}


def test_latency_rule_triggers_only_above_threshold(engine, repo):
    rules = repo.list_rules()
    high = engine.evaluate(ping_result("Online", 150.0, 0.0), rules)
    assert {e["rule"]["name"] for e in high if e["triggered"]} == {"High Latency"}
    edge = engine.evaluate(ping_result("Online", 100.0, 0.0), rules)  # gt, not gte
    assert not any(e["triggered"] for e in edge)


def test_packet_loss_rule_boundary(engine, repo):
    rules = repo.list_rules()
    at = engine.evaluate(ping_result("Warning", 5.0, 50.0), rules)
    assert "High Packet Loss" in {e["rule"]["name"] for e in at if e["triggered"]}
    below = engine.evaluate(ping_result("Warning", 5.0, 49.0), rules)
    assert "High Packet Loss" not in {e["rule"]["name"] for e in below if e["triggered"]}


def test_company_rule_is_not_evaluated_for_another_company(engine):
    company_a = "30000000-0000-4000-8000-000000000001"
    company_b = "30000000-0000-4000-8000-000000000002"
    company_rule = {"id": "rule-a", "name": "Company A secret threshold",
                    "metric": "device_status", "operator": "eq", "threshold": "Offline",
                    "severity": "critical", "enabled": True, "scope": "global",
                    "device_id": None, "company_id": company_a}
    unrelated = engine.evaluate(ping_result("Offline", None, None), [company_rule],
                                company_id=company_b)
    owned = engine.evaluate(ping_result("Offline", None, None), [company_rule],
                            company_id=company_a)
    assert unrelated == []
    assert len(owned) == 1 and owned[0]["triggered"] is True


def test_missing_metric_is_not_evaluable(engine, repo):
    evals = engine.evaluate(ping_result("Offline", None, None), repo.list_rules())
    by_name = {e["rule"]["name"]: e for e in evals}
    assert by_name["High Latency"]["evaluable"] is False and not by_name["High Latency"]["triggered"]
    assert by_name["High Packet Loss"]["evaluable"] is False
    assert by_name["Device Offline"]["triggered"] is True


def test_disabled_rule_does_not_trigger(engine, repo, rule):
    r = rule("Device Offline")
    repo.update_rule(r["id"], {"enabled": False})
    evals = engine.evaluate(ping_result("Offline", None, 100.0), repo.list_rules())
    assert all(e["rule"]["name"] != "Device Offline" for e in evals)


def test_invalid_stored_rule_is_skipped_not_fatal(engine):
    bad = {"id": "x", "name": "bad", "metric": "cpu", "operator": "eq", "threshold": 1,
           "severity": "info", "enabled": True, "scope": "global", "device_id": None}
    evals = engine.evaluate(ping_result(), [bad])
    assert evals[0]["valid"] is False and evals[0]["triggered"] is False


@pytest.mark.parametrize("patch", [
    {"metric": "cpu"},
    {"operator": "like"},
    {"severity": "fatal"},
    {"metric": "device_status", "operator": "gt", "threshold": "Offline"},
    {"metric": "device_status", "operator": "eq", "threshold": "Exploded"},
    {"metric": "device_status", "operator": "eq", "threshold": 5},
    {"metric": "latency_ms", "operator": "gt", "threshold": "fast"},
    {"metric": "latency_ms", "operator": "gt", "threshold": -1},
    {"metric": "latency_ms", "operator": "gt", "threshold": True},
    {"metric": "packet_loss", "operator": "gte", "threshold": 101},
    {"name": ""},
    {"scope": "device"},                      # device scope needs a device_id
    {"scope": "global", "device_id": "5b3b5b3b-5b3b-4b3b-8b3b-5b3b5b3b5b3b"},
    {"enabled": "yes"},
    {"threshold": "__import__('os').system('x')"},  # code is just an invalid threshold
])
def test_invalid_rules_are_rejected(patch):
    base = {"name": "r", "metric": "latency_ms", "operator": "gt", "threshold": 10, "severity": "info"}
    with pytest.raises(ValidationError):
        validate_rule({**base, **patch})


def test_valid_rule_is_normalised():
    r = validate_rule({"name": " r ", "metric": "device_status", "operator": "eq",
                       "threshold": "offline", "severity": "critical"})
    assert r["threshold"] == "Offline" and r["name"] == "r" and r["scope"] == "global"
    r2 = validate_rule({"name": "n", "metric": "latency_ms", "operator": "gt",
                        "threshold": "100", "severity": "info"})
    assert r2["threshold"] == 100


def test_rule_api_crud(client, rule):
    body = {"name": "Very High Latency", "metric": "latency_ms", "operator": "gte",
            "threshold": 500, "severity": "critical"}
    created = client.post("/api/rules", json=body)
    assert created.status_code == 201
    rid = created.get_json()["data"]["id"]
    assert client.post("/api/rules", json=body).status_code == 409  # duplicate name
    assert client.get(f"/api/rules/{rid}").status_code == 200
    patched = client.patch(f"/api/rules/{rid}", json={"threshold": 600, "enabled": False})
    assert patched.get_json()["data"]["threshold"] == 600
    assert client.patch(f"/api/rules/{rid}", json={"metric": "nope"}).status_code == 400
    assert client.patch(f"/api/rules/{rid}", json={}).status_code == 400
    assert client.get("/api/rules/not-a-uuid").status_code == 400
    assert len(client.get("/api/rules").get_json()["data"]) == 4
    assert len(client.get("/api/rules?enabled=true").get_json()["data"]) == 3
    assert client.delete(f"/api/rules/{rid}").status_code == 200
    assert client.get(f"/api/rules/{rid}").status_code == 404


def test_rule_with_incident_history_cannot_be_deleted(client, container, dev, rule):
    container.rules.evaluate_and_apply(dev("PC1"), ping_result("Offline", None, 100.0))
    resp = client.delete(f"/api/rules/{rule('Device Offline')['id']}")
    assert resp.status_code == 409


def test_device_scoped_rule_only_applies_to_its_device(container, repo, dev):
    pc1, pc2 = dev("PC1"), dev("PC2")
    container.rules.create_rule({"name": "PC1 slow", "metric": "latency_ms", "operator": "gt",
                                 "threshold": 10, "severity": "info", "scope": "device",
                                 "device_id": pc1["id"]})
    res = ping_result("Online", 50.0, 0.0)
    assert len(container.rules.evaluate_and_apply(pc2, res)["opened"]) == 0
    assert len(container.rules.evaluate_and_apply(pc1, res)["opened"]) == 1
