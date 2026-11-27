"""Profile and role provisioning for authenticated Supabase identities."""
import re

from app.utils.exceptions import AuthError, ConflictError, DatabaseError, ValidationError

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_NAME_LENGTH = 120
MAX_COMPANY_LENGTH = 150


class AuthService:
    def __init__(self, repo):
        self.repo = repo

    def provision_identity(self, identity):
        metadata = identity.get("user_metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        email = identity.get("email")
        if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
            raise AuthError("A valid email address is required for this account.")
        email = email.strip().lower()
        full_name = self._metadata_text(metadata.get("full_name") or metadata.get("name"),
                                        MAX_NAME_LENGTH)
        if not full_name:
            full_name = email.split("@", 1)[0][:MAX_NAME_LENGTH] or "NetOps360 User"
        company_name = self._metadata_text(metadata.get("company_name"), MAX_COMPANY_LENGTH)
        app_metadata = identity.get("app_metadata")
        provider = app_metadata.get("provider") if isinstance(app_metadata, dict) else None
        default_role = "admin" if provider == "email" else "viewer"
        result = self.repo.provision_auth_profile({
            "id": identity["sub"],
            "email": email,
            "full_name": full_name,
            "company_name": company_name,
        }, default_role)
        if not isinstance(result, dict) or not isinstance(result.get("profile"), dict):
            raise DatabaseError("The authenticated profile could not be provisioned.")
        return result["profile"]

    def onboard_company(self, identity, payload):
        if not isinstance(payload, dict) or set(payload) != {"full_name", "company_name"}:
            raise ValidationError("Provide only full_name and company_name.")
        full_name = self._metadata_text(payload.get("full_name"), MAX_NAME_LENGTH)
        company_name = self._metadata_text(payload.get("company_name"), MAX_COMPANY_LENGTH)
        if not full_name:
            raise ValidationError("full_name is required and must be at most 120 characters.")
        if not company_name:
            raise ValidationError("company_name is required and must be at most 150 characters.")
        email = identity.get("email")
        if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
            raise AuthError("A valid email address is required for this account.")
        existing = self.repo.get_profile(identity["sub"])
        existing_company = (existing or {}).get("company_name")
        if existing_company and existing_company != company_name:
            raise ConflictError("The company name cannot be changed through onboarding.")
        result = self.repo.provision_auth_profile({
            "id": identity["sub"],
            "email": email.strip().lower(),
            "full_name": full_name,
            "company_name": company_name,
        }, "admin")
        if not isinstance(result, dict) or not isinstance(result.get("profile"), dict):
            raise DatabaseError("The authenticated profile could not be provisioned.")
        return result["profile"]

    @staticmethod
    def _metadata_text(value, maximum):
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or len(value) > maximum:
            return None
        return value
