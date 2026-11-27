"""Shared PostgreSQL-backed throttling for app-managed auth operations."""
import hashlib
from functools import wraps

from flask import g, request

from app.extensions import get_container
from app.utils.exceptions import RateLimitError


def auth_rate_limit(scope, *, limit=None, window_seconds=None, identity_key=False):
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            config = get_container().config
            limit_value = limit or getattr(config, f"auth_{scope}_limit")
            window_value = window_seconds or getattr(config, f"auth_{scope}_window_seconds")
            subject = (getattr(g, "auth_identity", {}).get("sub") if identity_key
                       else request.remote_addr or "unknown")
            bucket = hashlib.sha256(f"netops360:{scope}:{subject}".encode()).hexdigest()
            if not get_container().repo.consume_auth_rate_limit(bucket, limit_value, window_value):
                raise RateLimitError()
            return fn(*args, **kwargs)
        return wrapper
    return decorate
