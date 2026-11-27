"""Supabase JWT authentication and database-backed permission checks."""
import hmac
import logging
import time
import uuid
from functools import wraps
from threading import Lock

import requests
from flask import current_app, g, request

from app.utils.exceptions import AuthError, DatabaseError, ForbiddenError, ServiceUnavailableError
from app.utils.timeutil import parse_ts

logger = logging.getLogger(__name__)
_jwks_clients = {}
_jwks_lock = Lock()
_TEST_USER_ID = "00000000-0000-4000-8000-000000000001"


def _jwks_client(config):
    uri = f"{config.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    with _jwks_lock:
        if uri not in _jwks_clients:
            try:
                import jwt
                _jwks_clients[uri] = jwt.PyJWKClient(uri, cache_jwk_set=True, lifespan=300, timeout=5)
            except Exception:
                raise ServiceUnavailableError("JWT verification is unavailable.") from None
        return _jwks_clients[uri]


def _verify_legacy_hs256(token, config, header):
    """Use GoTrue to verify legacy symmetric tokens; never keep the shared secret locally."""
    import jwt

    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False,
                                            "verify_aud": False, "verify_iss": False})
    except jwt.PyJWTError:
        raise AuthError() from None
    if claims.get("iss") != config.supabase_jwt_issuer or config.supabase_jwt_audience not in (claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]):
        raise AuthError()
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= time.time():
        raise AuthError("The access token has expired.")
    try:
        response = requests.get(
            f"{config.supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": config.supabase_service_role_key, "Authorization": f"Bearer {token}"},
            timeout=5,
        )
    except requests.RequestException:
        raise ServiceUnavailableError("Supabase Auth could not verify the access token.") from None
    if response.status_code == 401:
        raise AuthError()
    if response.status_code != 200:
        raise ServiceUnavailableError("Supabase Auth could not verify the access token.")
    try:
        remote_user = response.json()
        sub = str(uuid.UUID(str(claims.get("sub"))))
    except (ValueError, TypeError):
        raise AuthError() from None
    if remote_user.get("id") != sub:
        raise AuthError()
    return claims


def verify_supabase_token(token, config):
    """Verify signature, issuer, audience, expiry and UUID subject."""
    try:
        import jwt

        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            claims = _verify_legacy_hs256(token, config, header)
        elif algorithm in ("ES256", "RS256"):
            try:
                key = _jwks_client(config).get_signing_key_from_jwt(token).key
            except jwt.PyJWKClientConnectionError:
                raise ServiceUnavailableError("Supabase signing keys could not be retrieved.") from None
            except jwt.PyJWTError:
                raise AuthError() from None
            claims = jwt.decode(token, key, algorithms=[algorithm], issuer=config.supabase_jwt_issuer,
                                audience=config.supabase_jwt_audience,
                                options={"require": ["exp", "sub", "iss", "aud"]}, leeway=5)
        else:
            raise AuthError("The access token uses an unsupported signing algorithm.")
    except AuthError:
        raise
    except ServiceUnavailableError:
        raise
    except ImportError:
        raise ServiceUnavailableError("JWT verification dependencies are not installed.") from None
    except Exception as exc:
        # Network/JWKS errors are infrastructure failures; malformed/signature errors are 401.
        logger.warning("JWT verification failed (%s)", type(exc).__name__)
        raise AuthError() from None

    try:
        subject = str(uuid.UUID(str(claims.get("sub"))))
        session_id = str(uuid.UUID(str(claims.get("session_id"))))
    except (ValueError, TypeError, AttributeError):
        raise AuthError("The access token subject is invalid.") from None
    if claims.get("iss") != config.supabase_jwt_issuer:
        raise AuthError()
    audiences = claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]
    if config.supabase_jwt_audience not in audiences:
        raise AuthError()
    if claims.get("is_anonymous") is True:
        raise AuthError("Anonymous accounts are not allowed.")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= time.time():
        raise AuthError("The access token has expired.")
    return {**claims, "sub": subject, "session_id": session_id}


def _authenticate():
    container = current_app.extensions["netops"]
    config = container.config
    if config.testing and config.auth_test_bypass:
        identity = {"sub": _TEST_USER_ID, "email": "test-admin@netops360.invalid", "aud": "authenticated",
                    "session_id": "00000000-0000-4000-8000-000000000002", "exp": time.time() + 3600}
        g.auth_identity = identity
        g.auth_profile = {"id": _TEST_USER_ID, "account_status": "active", "full_name": "Test Admin"}
        g.auth_token = "test-token"
        g.auth_roles = {"super_admin"}
        g.auth_requires_mfa = False
        return identity

    authorization = request.headers.get("Authorization", "")
    if len(authorization) > 8192 or not authorization.startswith("Bearer "):
        raise AuthError()
    token = authorization[7:].strip()
    if not token or " " in token:
        raise AuthError()
    verifier = current_app.extensions.get("jwt_verifier") or verify_supabase_token
    identity = verifier(token, config)
    try:
        profile = container.repo.get_profile(identity["sub"])
        if profile and profile.get("account_status") == "suspended":
            raise AuthError("This account is not active.", code="account_inactive")
        cutoff = profile.get("sessions_revoked_at") if profile else None
        if cutoff:
            issued_at = identity.get("iat")
            if not isinstance(issued_at, (int, float)) or parse_ts(cutoff).timestamp() >= issued_at:
                raise AuthError("This session has been revoked.", code="session_revoked")
    except DatabaseError:
        raise
    if container.repo.is_session_revoked(identity["session_id"]):
        raise AuthError("This session has been revoked.", code="session_revoked")
    g.auth_identity = identity
    g.auth_profile = profile
    g.auth_token = token
    roles = set(container.repo.get_user_roles(identity["sub"])) if profile else set()
    g.auth_roles = roles
    g.auth_requires_mfa = bool(roles.intersection({"super_admin", "company_admin", "admin"}))
    return identity


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        _authenticate()
        return fn(*args, **kwargs)
    return wrapper


def require_permission(*permission_keys):
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            identity = _authenticate()
            container = current_app.extensions["netops"]
            if g.auth_profile is None:
                raise ForbiddenError(
                    "Complete company registration or accept an administrator invitation.",
                    code="onboarding_required",
                )
            if g.auth_profile.get("account_status") != "active":
                raise ForbiddenError("Accept your company invitation before using this account.",
                                     code="invitation_pending")
            if not (container.config.testing and container.config.auth_test_bypass):
                permissions = set(container.repo.get_user_permissions(identity["sub"]))
                if not set(permission_keys).issubset(permissions):
                    raise ForbiddenError()
                if g.auth_requires_mfa and identity.get("aal", "aal1") != "aal2":
                    raise ForbiddenError("Verify your authenticator app before continuing.", code="mfa_required")
                if ("system.manage" not in permissions and not g.auth_profile.get("company_id")
                        and set(permission_keys) != {"system.manage"}):
                    raise ForbiddenError("This account must be assigned to a company before accessing tenant data.",
                                         code="company_membership_required")
                g.auth_permissions = permissions
            else:
                g.auth_permissions = {"*"}
            return fn(*args, **kwargs)
        return wrapper
    return decorate


def require_backup_automation(permission_key):
    """Permit a narrowly scoped n8n bearer token or a normal RBAC user."""
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            config = current_app.extensions["netops"].config
            authorization = request.headers.get("Authorization", "")
            prefix = "Bearer "
            token = authorization[len(prefix):].strip() if authorization.startswith(prefix) else ""
            service_token = config.n8n_backup_api_token
            if service_token and token and len(token) <= 8192 and hmac.compare_digest(token, service_token):
                g.backup_automation_token = True
                return fn(*args, **kwargs)
            identity = _authenticate()
            container = current_app.extensions["netops"]
            if not (container.config.testing and container.config.auth_test_bypass):
                permissions = set(container.repo.get_user_permissions(identity["sub"]))
                if permission_key not in permissions:
                    raise ForbiddenError()
                if g.auth_requires_mfa and identity.get("aal", "aal1") != "aal2":
                    raise ForbiddenError("Verify your authenticator app before continuing.", code="mfa_required")
                profile = getattr(g, "auth_profile", None)
                if profile and "system.manage" not in permissions and not profile.get("company_id"):
                    raise ForbiddenError("This account must be assigned to a company before accessing tenant data.",
                                         code="company_membership_required")
                g.auth_permissions = permissions
            else:
                g.auth_permissions = {"*"}
            g.backup_automation_token = False
            return fn(*args, **kwargs)
        return wrapper
    return decorate


def require_recent_mfa(fn):
    """Require an AAL2 TOTP proof less than five minutes old for sensitive actions."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        identity = _authenticate()
        container = current_app.extensions["netops"]
        if container.config.testing and container.config.auth_test_bypass:
            return fn(*args, **kwargs)
        if g.auth_requires_mfa:
            if identity.get("aal", "aal1") != "aal2":
                raise ForbiddenError("Verify your authenticator app before continuing.", code="mfa_required")
            methods = identity.get("amr")
            now = time.time()
            recent_totp = any(
                isinstance(method, dict) and method.get("method") == "totp"
                and isinstance(method.get("timestamp"), (int, float))
                and now - 300 <= method["timestamp"] <= now + 60
                for method in (methods if isinstance(methods, list) else [])
            )
            if not recent_totp:
                raise ForbiddenError("Verify your authenticator code again to confirm this action.",
                                     code="step_up_required")
        return fn(*args, **kwargs)
    return wrapper


def require_role(*role_names):
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            identity = _authenticate()
            container = current_app.extensions["netops"]
            if not (container.config.testing and container.config.auth_test_bypass):
                roles = set(container.repo.get_user_roles(identity["sub"]))
                if not roles.intersection(role_names):
                    raise ForbiddenError()
            return fn(*args, **kwargs)
        return wrapper
    return decorate


def require_api_key(fn):
    """Deprecated compatibility decorator; protected routes must use require_permission."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        raise AuthError("API keys are no longer accepted; provide a Supabase access token.")

    return wrapper
