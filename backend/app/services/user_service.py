"""Invite-only user provisioning and database-backed RBAC administration."""
import logging
import re
import uuid
from datetime import timedelta

from app.utils.exceptions import ConflictError, DatabaseError, ForbiddenError, NotFoundError, ServiceUnavailableError, ValidationError
from app.utils.timeutil import utcnow

logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class UserService:
    def __init__(self, repo, auth_admin, config, audit):
        self.repo = repo
        self.auth_admin = auth_admin
        self.config = config
        self.audit = audit

    @staticmethod
    def _safe_profile(profile):
        return {key: profile.get(key) for key in (
            "id", "full_name", "email", "phone_number", "account_status", "created_at",
            "updated_at", "last_login_at", "company_name", "company_id",
        )}

    def list_users(self, actor_id, limit, offset, search=None, status=None):
        if status not in (None, "active", "pending", "suspended"):
            raise ValidationError("status must be active, pending, or suspended.")
        company_id = self._managed_company_id(actor_id)
        rows, total = self.repo.list_profiles(limit=limit, offset=offset, search=search,
                                              status=status, company_id=company_id)
        result = []
        for profile in rows:
            row = self._safe_profile(profile)
            row["roles"] = [item["role"] for item in self.repo.list_user_role_rows(profile["id"])
                            if item.get("role")]
            result.append(row)
        return result, total

    def get_user(self, user_id, actor_id=None):
        user_id = self._validate_id(user_id, "user_id")
        profile = self.repo.get_profile(user_id)
        if not profile:
            raise NotFoundError("User not found.")
        if actor_id:
            self._assert_target_company(actor_id, profile)
        row = self._safe_profile(profile)
        row["roles"] = [item["role"] for item in self.repo.list_user_role_rows(user_id)
                        if item.get("role")]
        return row

    def _managed_company_id(self, actor_id):
        actor_id = self._validate_id(actor_id, "actor_id")
        if "company_admin" not in set(self.repo.get_user_roles(actor_id)):
            return None
        profile = self.repo.get_profile(actor_id)
        if not profile or not profile.get("company_id"):
            raise ForbiddenError("Company Admin is not associated with a registered company.")
        return str(profile["company_id"])

    def _assert_target_company(self, actor_id, target):
        company_id = self._managed_company_id(actor_id)
        if company_id and str(target.get("company_id") or "") != company_id:
            raise NotFoundError("User not found.")
        if company_id and str(target.get("id")) == str(actor_id):
            raise ForbiddenError("Company Admins cannot modify their own account through user management.")
        target_roles = set(self.repo.get_user_roles(target["id"])) if company_id else set()
        if company_id and target_roles.intersection({"admin", "super_admin", "company_admin"}):
            raise ForbiddenError("Administrator accounts cannot be managed by a Company Admin.")

    @staticmethod
    def _validate_id(value, field):
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError(f"{field} must be a valid UUID.") from None

    def invite_user(self, payload, actor_id):
        if not isinstance(payload, dict) or set(payload) - {"email", "full_name", "phone_number", "role_id"}:
            raise ValidationError("Provide only email, full_name, phone_number, and role_id.")
        email = payload.get("email")
        if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()) or len(email.strip()) > 254:
            raise ValidationError("email must be a valid email address.")
        email = email.strip().lower()
        name = payload.get("full_name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValidationError("full_name is required and must be at most 120 characters.")
        phone = payload.get("phone_number")
        if phone is not None and (not isinstance(phone, str) or len(phone.strip()) > 32):
            raise ValidationError("phone_number must be a string of at most 32 characters.")
        if self.repo.profile_exists_by_email(email):
            raise ConflictError("A user with this email already exists.")
        actor_id = self._validate_id(actor_id, "actor_id")
        actor_roles = set(self.repo.get_user_roles(actor_id))
        if "company_admin" not in actor_roles:
            raise ForbiddenError("Invitations must be issued by a Company Admin.")
        actor_profile = self.repo.get_profile(actor_id)
        company_name = (actor_profile or {}).get("company_name")
        company_id = (actor_profile or {}).get("company_id")
        if not company_id:
            raise ForbiddenError("Company Admin is not associated with a registered company.")
        role_id = self._validate_id(payload["role_id"], "role_id") if payload.get("role_id") else None
        role = self.repo.get_role(role_id) if role_id else self.repo.get_role_by_name("viewer")
        if not role:
            raise ServiceUnavailableError("The initial Viewer role is not configured.")
        if role["name"] not in ("network_operator", "viewer"):
            raise ForbiddenError("Company Admins may invite only network_operator or viewer users.")
        self._ensure_role_within_authority(actor_id, role)
        if self.auth_admin is None:
            raise ServiceUnavailableError("Supabase Auth administration is unavailable.")

        invited_id = None
        try:
            response = self.auth_admin.invite_user_by_email(email, options={
                "data": {"full_name": name.strip(), "company_name": company_name},
                "redirect_to": f"{self.config.frontend_url}/accept-invite",
            })
            user = getattr(response, "user", None)
            raw_id = getattr(user, "id", None)
            if not raw_id and isinstance(user, dict):
                raw_id = user.get("id")
            invited_id = str(raw_id or "")
            invited_id = self._validate_id(invited_id, "invited user id")
            expires_at = (utcnow() + timedelta(hours=24)).isoformat()
            provisioned = self.repo.provision_company_invitation({
                "user_id": invited_id, "email": email, "full_name": name.strip(),
                "phone_number": phone.strip() if isinstance(phone, str) and phone.strip() else None,
                "role_id": role["id"], "invited_by": actor_id, "expires_at": expires_at,
            })
            profile = provisioned.get("profile")
            invitation = provisioned.get("invitation")
            if not profile or not invitation:
                raise DatabaseError("Company invitation provisioning did not complete.")
            self.audit.record("invited", "user", row=profile)
            return {**self.get_user(invited_id), "invitation": invitation}
        except (ValidationError, ConflictError, ForbiddenError):
            self._rollback_invitation(invited_id)
            raise
        except Exception as exc:
            self._rollback_invitation(invited_id)
            if isinstance(exc, DatabaseError):
                raise
            logger.error("Supabase user invitation failed (%s)", type(exc).__name__)
            raise ServiceUnavailableError("The user invitation could not be completed.") from None

    def accept_invitation(self, user_id):
        user_id = self._validate_id(user_id, "user_id")
        result = self.repo.accept_company_invitation(user_id)
        profile = result.get("profile") if isinstance(result, dict) else None
        if not profile:
            raise NotFoundError("No active invitation was found for this account.")
        self.audit.record("invitation_accepted", "user", row=profile)
        return self.get_user(user_id)

    def _rollback_invitation(self, user_id):
        if not user_id or self.auth_admin is None:
            return
        try:
            self.auth_admin.delete_user(user_id)
        except Exception as exc:
            logger.error("Auth invitation compensation failed (%s)", type(exc).__name__)

    def update_user(self, user_id, payload, actor_id):
        user_id = self._validate_id(user_id, "user_id")
        if not isinstance(payload, dict) or not payload or set(payload) - {"full_name", "phone_number"}:
            raise ValidationError("Only full_name and phone_number can be updated here.")
        before = self.repo.get_profile(user_id)
        if not before:
            raise NotFoundError("User not found.")
        self._assert_target_company(actor_id, before)
        changes = {}
        if "full_name" in payload:
            value = payload["full_name"]
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
                raise ValidationError("full_name is required and must be at most 120 characters.")
            changes["full_name"] = value.strip()
        if "phone_number" in payload:
            value = payload["phone_number"]
            if value is not None and (not isinstance(value, str) or len(value.strip()) > 32):
                raise ValidationError("phone_number must be a string of at most 32 characters.")
            changes["phone_number"] = value.strip() or None if isinstance(value, str) else None
        after = self.repo.update_profile(user_id, changes)
        self.audit.record("updated", "user", row=after, before=before)
        return self.get_user(user_id)

    def set_status(self, user_id, status, actor_id):
        user_id = self._validate_id(user_id, "user_id")
        actor_id = self._validate_id(actor_id, "actor_id")
        if status not in ("active", "suspended"):
            raise ValidationError("status must be active or suspended.")
        before = self.repo.get_profile(user_id)
        if not before:
            raise NotFoundError("User not found.")
        self._assert_target_company(actor_id, before)
        if before.get("account_status") == "pending":
            raise ForbiddenError("Pending accounts must accept their invitation before activation.")
        if before["account_status"] == status:
            return self.get_user(user_id)
        if self.auth_admin is None:
            raise ServiceUnavailableError("Supabase Auth administration is unavailable.")
        if status == "suspended":
            after = self.repo.update_profile(user_id, {
                "account_status": status,
                "sessions_revoked_at": utcnow().isoformat(),
            })
            try:
                self.auth_admin.update_user_by_id(user_id, {"ban_duration": "876000h"})
            except Exception as exc:
                # Active database authorization is already denied for suspended users.
                logger.error("Supabase Auth ban update failed (%s)", type(exc).__name__)
        else:
            try:
                self.auth_admin.update_user_by_id(user_id, {"ban_duration": "none"})
            except Exception as exc:
                logger.error("Supabase Auth unban update failed (%s)", type(exc).__name__)
                raise ServiceUnavailableError("The Auth account could not be reactivated.") from None
            after = self.repo.update_profile(user_id, {"account_status": status})
        self.audit.record(status, "user", row=after, before=before)
        return self.get_user(user_id)

    def _ensure_role_within_authority(self, actor_id, role):
        actor_roles = set(self.repo.get_user_roles(actor_id))
        if role["name"] == "company_admin":
            raise ForbiddenError("Company Admin is assigned only by company registration.")
        if "company_admin" in actor_roles:
            if role["name"] not in ("network_operator", "viewer"):
                raise ForbiddenError("Company Admins may assign only network_operator or viewer users.")
            return
        actor_permissions = set(self.repo.get_user_permissions(actor_id))
        target_permissions = set(self.repo.get_role_permissions(role["id"]))
        if role["name"] == "super_admin" and "system.manage" not in actor_permissions:
            raise ForbiddenError("Only a Super Admin can grant Super Admin access.")
        if not target_permissions.issubset(actor_permissions):
            raise ForbiddenError("You cannot grant privileges beyond your own authority.")

    def assign_role(self, user_id, role_id, actor_id):
        user_id = self._validate_id(user_id, "user_id")
        role_id = self._validate_id(role_id, "role_id")
        actor_id = self._validate_id(actor_id, "actor_id")
        target = self.repo.get_profile(user_id)
        role = self.repo.get_role(role_id)
        if not target or not role:
            raise NotFoundError("User or role not found.")
        self._assert_target_company(actor_id, target)
        if role["name"] == "company_admin":
            raise ForbiddenError("Company Admin is assigned only by company registration.")
        self._ensure_role_within_authority(actor_id, role)
        if user_id == actor_id and role["name"] == "super_admin" and "super_admin" not in self.repo.get_user_roles(actor_id):
            raise ForbiddenError("You cannot promote yourself to Super Admin.")
        result = self.repo.assign_user_role(user_id, role_id, actor_id)
        self.audit.record("role_assigned", "user_role", row=result)
        return self.get_user(user_id)

    def remove_role(self, user_id, role_id, actor_id):
        user_id = self._validate_id(user_id, "user_id")
        role_id = self._validate_id(role_id, "role_id")
        actor_id = self._validate_id(actor_id, "actor_id")
        target = self.repo.get_profile(user_id)
        role = self.repo.get_role(role_id)
        if not target or not role:
            raise NotFoundError("User or role not found.")
        self._assert_target_company(actor_id, target)
        if role["name"] == "company_admin":
            raise ConflictError("Transfer company administration before removing this role.")
        self._ensure_role_within_authority(actor_id, role)
        before = next((item for item in self.repo.list_user_role_rows(user_id)
                       if item["role_id"] == role_id), None)
        if not before:
            raise NotFoundError("User role assignment not found.")
        self.repo.remove_user_role(user_id, role_id)
        self.audit.record("role_removed", "user_role", row=before, before=before, after={})
        return self.get_user(user_id)

    def get_roles(self):
        return self.repo.list_roles()

    def get_permissions(self):
        return self.repo.list_permissions()

    def company_audit_logs(self, actor_id, limit=50, offset=0):
        company_id = self._managed_company_id(actor_id)
        if not company_id:
            raise ForbiddenError("Company audit history is available to Company Admins only.")
        return self.repo.list_company_audit_logs(company_id, limit, offset)
