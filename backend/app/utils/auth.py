"""Minimal API-key authentication (interim measure, NOT user authentication).

If API_KEY is empty, auth is disabled (development only) and a warning is logged
at startup. Compare with hmac.compare_digest to avoid timing leaks.
"""
import hmac
from functools import wraps

from flask import request

from app.utils.exceptions import AuthError


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from app.extensions import get_container  # local import avoids cycles

        expected = get_container().config.api_key
        if expected:
            supplied = request.headers.get("X-API-Key", "")
            if not hmac.compare_digest(supplied.encode(), expected.encode()):
                raise AuthError()
        return fn(*args, **kwargs)

    return wrapper
