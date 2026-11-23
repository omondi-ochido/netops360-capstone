import pytest

from app.config import Config, ConfigError
from app.utils.exceptions import ConflictError, DatabaseError, ValidationError


def test_health_ok(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert "monitoring" in body


def test_health_reports_database_outage(client, repo):
    repo.fail = True
    resp = client.get("/api/health")
    assert resp.status_code == 200  # the backend itself is alive
    body = resp.get_json()
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "unavailable"


def test_database_outage_returns_safe_503(client, repo):
    repo.fail = True
    resp = client.get("/api/devices")
    assert resp.status_code == 503
    assert resp.get_json()["error"]["code"] == "database_unavailable"


def test_unexpected_errors_do_not_leak_details(app, client, container):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    container.devices.list = boom
    app.config["PROPAGATE_EXCEPTIONS"] = False
    resp = client.get("/api/devices")
    assert resp.status_code == 500
    assert "secret internal detail" not in resp.get_data(as_text=True)


def test_missing_supabase_env_is_reported(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    config = Config.from_env(load_env_file=False)
    with pytest.raises(ConfigError) as exc:
        config.validate(require_supabase=True)
    assert "SUPABASE_URL" in str(exc.value) and "SUPABASE_SERVICE_ROLE_KEY" in str(exc.value)
    config.validate(require_supabase=False)  # not required when a repository is injected


def test_config_values_never_appear_in_errors(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-key-123")
    monkeypatch.setenv("PING_COUNT", "99")
    config = Config.from_env(load_env_file=False)
    with pytest.raises(ConfigError) as exc:
        config.validate(require_supabase=True)
    assert "super-secret-key-123" not in str(exc.value)


def test_config_defaults_are_safe(monkeypatch):
    for name in ("FLASK_DEBUG", "CORS_ALLOWED_ORIGINS", "API_KEY"):
        monkeypatch.delenv(name, raising=False)
    config = Config.from_env(load_env_file=False)
    assert config.debug is False
    assert config.cors_origins == ["http://localhost:5173"]


def test_config_rejects_wildcard_cors_and_bad_values():
    with pytest.raises(ConfigError):
        Config.from_env({"cors_origins": ["*"]}, load_env_file=False).validate(False)
    with pytest.raises(ConfigError):
        Config.from_env({"ping_count": 0}, load_env_file=False).validate(False)
    with pytest.raises(ConfigError):
        Config.from_env({"nonexistent_setting": 1}, load_env_file=False)


def test_cors_only_allows_configured_origin(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    other = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert other.headers.get("Access-Control-Allow-Origin") is None


# ---- Supabase error mapping (no network: fake query builders) ------------------
postgrest = pytest.importorskip("postgrest")


class _Builder:
    def __init__(self, exc):
        self.exc = exc

    def execute(self):
        raise self.exc


def _api_error(code):
    from postgrest.exceptions import APIError

    return APIError({"message": "m", "code": code, "details": "", "hint": ""})


@pytest.mark.parametrize("code,expected", [
    ("23505", ConflictError), ("23503", ConflictError),
    ("23514", ValidationError), ("XX000", DatabaseError),
])
def test_supabase_errors_are_mapped(code, expected):
    from app.repositories.supabase_repository import _execute

    with pytest.raises(expected):
        _execute(_Builder(_api_error(code)))


def test_supabase_connection_failure_becomes_database_error():
    from app.repositories.supabase_repository import _execute

    with pytest.raises(DatabaseError):
        _execute(_Builder(ConnectionError("refused: https://x.supabase.co key=abc")))
