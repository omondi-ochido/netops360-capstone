"""Centralised, validated configuration. Secret values are never logged or returned."""
import os


class ConfigError(RuntimeError):
    pass


def _env_bool(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer.") from None


def _env_str(name, default=""):
    return os.environ.get(name, default).strip()


class Config:
    def __init__(self):
        self.env = "development"
        self.debug = False
        self.testing = False
        self.port = 5050

        self.supabase_url = ""
        self.supabase_service_role_key = ""

        self.api_key = ""
        self.supabase_jwt_issuer = ""
        self.supabase_jwt_audience = "authenticated"
        self.auth_test_bypass = False
        self.frontend_url = "http://localhost:5173"

        self.ssh_username = ""
        self.ssh_password = ""
        self.ssh_timeout_seconds = 15

        self.n8n_webhook_url = ""
        self.n8n_webhook_secret = ""
        self.automation_timeout_seconds = 10
        self.automation_max_retries = 5
        self.automation_backoff_seconds = 30
        self.automation_synchronous = False  # tests only

        self.monitoring_enabled = True
        self.monitoring_interval_seconds = 30
        self.monitoring_workers = 8
        self.ping_count = 3
        self.ping_timeout_seconds = 2
        self.partial_loss_status = "Warning"  # status for 0% < loss < 100%

        self.backup_schedule_seconds = 0  # 0 disables scheduled backups
        self.backup_on_critical_incident = False

        self.cors_origins = ["http://localhost:5173"]

    @classmethod
    def from_env(cls, overrides=None, load_env_file=True):
        if load_env_file:
            from dotenv import load_dotenv

            load_dotenv(override=False)

        c = cls()
        c.env = _env_str("FLASK_ENV", "development")
        c.debug = _env_bool("FLASK_DEBUG", False)  # debug is OFF unless explicitly enabled
        c.port = _env_int("PORT", 5050)

        c.supabase_url = _env_str("SUPABASE_URL")
        c.supabase_service_role_key = _env_str("SUPABASE_SERVICE_ROLE_KEY")
        c.api_key = _env_str("API_KEY")
        c.supabase_jwt_issuer = _env_str("SUPABASE_JWT_ISSUER", f"{c.supabase_url.rstrip('/')}/auth/v1" if c.supabase_url else "")
        c.supabase_jwt_audience = _env_str("SUPABASE_JWT_AUDIENCE", "authenticated")
        c.auth_test_bypass = _env_bool("AUTH_TEST_BYPASS", False)
        c.frontend_url = _env_str("FRONTEND_URL", "http://localhost:5173").rstrip("/")

        c.ssh_username = _env_str("NETOPS_SSH_USERNAME")
        c.ssh_password = os.environ.get("NETOPS_SSH_PASSWORD", "")
        c.ssh_timeout_seconds = _env_int("SSH_TIMEOUT_SECONDS", 15)

        c.n8n_webhook_url = _env_str("N8N_WEBHOOK_URL")
        c.n8n_webhook_secret = _env_str("N8N_WEBHOOK_SECRET")
        c.automation_timeout_seconds = _env_int("AUTOMATION_TIMEOUT_SECONDS", 10)
        c.automation_max_retries = _env_int("AUTOMATION_MAX_RETRIES", 5)
        c.automation_backoff_seconds = _env_int("AUTOMATION_BACKOFF_SECONDS", 30)

        c.monitoring_enabled = _env_bool("MONITORING_ENABLED", True)
        c.monitoring_interval_seconds = _env_int("MONITORING_INTERVAL_SECONDS", 30)
        c.monitoring_workers = _env_int("MONITORING_WORKERS", 8)
        c.ping_count = _env_int("PING_COUNT", 3)
        c.ping_timeout_seconds = _env_int("PING_TIMEOUT_SECONDS", 2)
        c.partial_loss_status = _env_str("PARTIAL_LOSS_STATUS", "Warning") or "Warning"

        c.backup_schedule_seconds = _env_int("BACKUP_SCHEDULE_SECONDS", 0)
        c.backup_on_critical_incident = _env_bool("BACKUP_ON_CRITICAL_INCIDENT", False)

        origins = _env_str("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
        c.cors_origins = [o.strip() for o in origins.split(",") if o.strip()]

        for key, value in (overrides or {}).items():
            if not hasattr(c, key):
                raise ConfigError(f"Unknown config override: {key}")
            setattr(c, key, value)
        return c

    def validate(self, require_supabase=True):
        """Raise ConfigError naming every problem. Never includes secret values."""
        problems = []
        if require_supabase:
            if not self.supabase_url:
                problems.append("SUPABASE_URL is required")
            if not self.supabase_service_role_key:
                problems.append("SUPABASE_SERVICE_ROLE_KEY is required")
        if self.auth_test_bypass and not self.testing:
            problems.append("AUTH_TEST_BYPASS is allowed only in testing")
        if not 1 <= self.ping_count <= 10:
            problems.append("PING_COUNT must be between 1 and 10")
        if not 1 <= self.ping_timeout_seconds <= 30:
            problems.append("PING_TIMEOUT_SECONDS must be between 1 and 30")
        if self.monitoring_interval_seconds < 5:
            problems.append("MONITORING_INTERVAL_SECONDS must be at least 5")
        if not 1 <= self.monitoring_workers <= 32:
            problems.append("MONITORING_WORKERS must be between 1 and 32")
        if self.partial_loss_status not in ("Online", "Warning"):
            problems.append("PARTIAL_LOSS_STATUS must be 'Online' or 'Warning'")
        if self.automation_max_retries < 0:
            problems.append("AUTOMATION_MAX_RETRIES must be 0 or greater")
        if "*" in self.cors_origins:
            problems.append("CORS_ALLOWED_ORIGINS must list explicit origins, not '*'")
        if problems:
            raise ConfigError("Invalid configuration: " + "; ".join(problems) + ".")
        return self
