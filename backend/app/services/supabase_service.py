"""Reusable Supabase client. One client is created per process and reused."""
import threading

from app.config import ConfigError

_client = None
_lock = threading.Lock()


def get_client(config):
    global _client
    with _lock:
        if _client is None:
            try:
                from supabase import create_client

                _client = create_client(config.supabase_url, config.supabase_service_role_key)
            except Exception:
                # Do not chain: the original message could echo configuration values.
                raise ConfigError(
                    "Supabase client initialisation failed. Check SUPABASE_URL and "
                    "SUPABASE_SERVICE_ROLE_KEY."
                ) from None
        return _client


def create_repository(config):
    from app.repositories.supabase_repository import SupabaseRepository

    return SupabaseRepository(get_client(config))
