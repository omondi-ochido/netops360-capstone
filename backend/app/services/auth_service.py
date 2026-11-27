"""Profile and role provisioning for authenticated Supabase identities."""
import re

from app.utils.exceptions import AuthError, ConflictError, DatabaseError, ValidationError

DUPLICATE_COMPANY_MESSAGE = (
    "This company is already registered on NetOps360. An account for this company already exists. "
    "Please sign in or contact your company's administrator for an invitation."
)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_NAME_LENGTH = 120
MAX_COMPANY_LENGTH = 150


class AuthService:
    def __init__(self, repo):
        self.repo = repo

    def register_company(self, identity, payload):
        if not isinstance(payload, dict) or set(payload) != {"full_name", "company_name"}:
            raise ValidationError("Provide only full_name and company_name.")
        full_name = self._normalize_text(payload.get("full_name"), MAX_NAME_LENGTH)
        company_name = self._normalize_text(payload.get("company_name"), MAX_COMPANY_LENGTH)
        if not full_name:
            raise ValidationError("full_name is required and must be at most 120 characters.")
        if not company_name:
            raise ValidationError("company_name is required and must be at most 150 characters.")
        email = identity.get("email")
        if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
            raise AuthError("A valid email address is required for this account.")
        result = self.repo.register_company({
            "id": identity["sub"],
            "email": email.strip().lower(),
            "full_name": full_name,
            "company_name": company_name,
        })
        if not isinstance(result, dict):
            raise DatabaseError("Company registration could not be completed.")
        if result.get("status") == "company_exists":
            raise ConflictError(DUPLICATE_COMPANY_MESSAGE, code="company_already_registered")
        if result.get("status") == "existing_account":
            raise ConflictError("This account is already registered. Sign in or contact your company's administrator.",
                                code="account_already_registered")
        if result.get("status") != "registered" or not isinstance(result.get("profile"), dict):
            raise DatabaseError("Company registration could not be completed.")
        return result

    # Kept as a source-compatible alias for clients from the previous release.
    onboard_company = register_company

    @staticmethod
    def _normalize_text(value, maximum):
        if not isinstance(value, str):
            return None
        value = " ".join(value.split())
        if not value or len(value) > maximum:
            return None
        return value
