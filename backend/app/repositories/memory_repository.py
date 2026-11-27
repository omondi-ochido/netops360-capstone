"""In-memory repository with the same interface as SupabaseRepository.

Used by the test-suite so tests need no network, no Supabase and no GNS3.
It mirrors the database rules that matter: unique hostnames/IPs, one active
incident per device+rule, and no successful backup with an empty configuration.
"""
import copy
import threading
import time
import uuid
from functools import wraps

from app.models.constants import ACTIVE_INCIDENT_STATUSES
from app.models.rbac import PERMISSION_KEYS, ROLE_PERMISSIONS
from app.utils.exceptions import ConflictError, DatabaseError, NotFoundError, ValidationError
from app.utils.timeutil import now_iso, parse_ts, utcnow


def guarded(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if self.fail:
            raise DatabaseError()
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper


def _page(rows, limit, offset):
    rows = rows[offset:]
    return rows[:limit] if limit is not None else rows


class InMemoryRepository:
    def __init__(self):
        self._lock = threading.RLock()
        self.fail = False  # set True to simulate a database outage
        self.devices = {}
        self.monitoring_logs = []
        self.rules = {}
        self.incidents = {}
        self.backups = {}
        self.automation_logs = {}
        self.audit_logs = []
        self.profiles = {}
        self.companies = {}
        self.roles = {str(uuid.uuid5(uuid.NAMESPACE_URL, f"netops360:role:{name}")):
                      {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"netops360:role:{name}")),
                       "name": name, "description": ""} for name in ROLE_PERMISSIONS}
        self.permissions = {key: {"permission_key": key, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"netops360:permission:{key}")),
                                  "description": key, "resource": key.split(".")[0], "action": key.split(".")[1]}
                            for key in PERMISSION_KEYS}
        self.user_roles = []
        self.assistant_invite_reservations = {}
        self.revoked_sessions = {}
        self.auth_rate_limits = {}

    # ------------------------------------------------------------------ health
    @guarded
    def ping(self):
        return True

    @guarded
    def insert_audit_log(self, data):
        row = {"id": str(uuid.uuid4()), "occurred_at": now_iso(), **data}
        self.audit_logs.append(row)
        return copy.deepcopy(row)

    # ---------------------------------------------------------- auth / RBAC
    @guarded
    def get_profile(self, user_id):
        return copy.deepcopy(self.profiles.get(str(user_id)))

    @guarded
    def profile_exists_by_email(self, email):
        return any(p["email"].lower() == str(email).lower() for p in self.profiles.values())

    @guarded
    def create_profile(self, data):
        if any(p["email"].lower() == data["email"].lower() for p in self.profiles.values()):
            raise ConflictError("A user with this email already exists.")
        row = {"phone_number": None, "account_status": "active", "last_login_at": None,
               "created_at": now_iso(), "updated_at": now_iso(), **data}
        self.profiles[str(row["id"])] = row
        return copy.deepcopy(row)

    @guarded
    def register_company(self, data):
        company_name = " ".join(str(data["company_name"]).split())
        normalized = company_name.lower()
        if any(c["normalized_company_name"] == normalized for c in self.companies.values()):
            return {"status": "company_exists"}
        user_id = str(data["id"])
        email = str(data["email"]).lower()
        if user_id in self.profiles or any(p["email"].lower() == email for p in self.profiles.values()):
            return {"status": "existing_account"}
        role = next((r for r in self.roles.values() if r["name"] == "company_admin"), None)
        if not role:
            raise DatabaseError("Company Admin role is not configured.")

        created = now_iso()
        profile = {"id": user_id, "email": email, "full_name": data["full_name"],
                   "company_name": company_name, "company_id": None, "invited_by": None,
                   "account_status": "active", "phone_number": None,
                   "created_at": created, "updated_at": created, "last_login_at": None}
        company_id = str(uuid.uuid4())
        company = {"id": company_id, "company_name": company_name,
                   "normalized_company_name": normalized, "registration_status": "active",
                   "initial_admin_id": user_id, "created_at": created, "updated_at": created}
        profile["company_id"] = company_id
        role_assignment = {"id": str(uuid.uuid4()), "user_id": user_id, "role_id": role["id"],
                           "assigned_by": user_id, "assigned_at": created}
        audit = {"id": str(uuid.uuid4()), "actor_id": None, "actor_user_id": user_id,
                 "action": "company_registered", "resource_type": "company",
                 "resource_id": company_id, "company_id": company_id,
                 "description": "Company registered and initial Company Admin assigned.",
                 "occurred_at": created, "before_metadata": {},
                 "after_metadata": {"company_id": company_id, "company_name": company_name,
                                    "initial_admin_id": user_id, "role": "company_admin"}}
        self.profiles[user_id] = profile
        self.companies[company_id] = company
        self.user_roles.append(role_assignment)
        self.audit_logs.append(audit)
        return {"status": "registered", "profile": copy.deepcopy(profile),
                "company": copy.deepcopy(company), "roles": ["company_admin"]}

    @guarded
    def list_profiles(self, limit=50, offset=0, search=None, status=None, company_id=None):
        rows = list(self.profiles.values())
        if company_id:
            rows = [p for p in rows if p.get("company_id") == str(company_id)]
        if status:
            rows = [p for p in rows if p["account_status"] == status]
        if search:
            term = search.lower()
            rows = [p for p in rows if term in p["email"].lower() or term in p["full_name"].lower()]
        rows.sort(key=lambda p: p["email"].lower())
        total = len(rows)
        return copy.deepcopy(_page(rows, limit, offset)), total

    @guarded
    def create_company_invitation(self, data):
        row = {"id": str(uuid.uuid4()), "status": "pending", **data}
        self.company_invitations = getattr(self, "company_invitations", {})
        self.company_invitations[row["id"]] = row
        return copy.deepcopy(row)

    @guarded
    def provision_company_invitation(self, data):
        inviter = self.profiles.get(str(data["invited_by"]))
        role = self.roles.get(str(data["role_id"]))
        if not inviter or not inviter.get("company_id") or not role or role["name"] not in ("network_operator", "viewer"):
            raise ValidationError("The company invitation is not valid.")
        if "company_admin" not in self.get_user_roles(data["invited_by"]):
            raise ValidationError("Only a Company Admin may invite users.")
        if any(profile["email"].lower() == data["email"].lower() for profile in self.profiles.values()):
            raise ConflictError("A user with this email already exists.")
        user_id = str(data["user_id"])
        profile = {"id": user_id, "email": data["email"], "full_name": data["full_name"],
                   "phone_number": data.get("phone_number"), "account_status": "pending",
                   "company_name": inviter.get("company_name"), "company_id": inviter["company_id"],
                   "invited_by": data["invited_by"], "created_at": now_iso(), "updated_at": now_iso(),
                   "last_login_at": None}
        self.profiles[user_id] = profile
        self.user_roles.append({"id": str(uuid.uuid4()), "user_id": user_id, "role_id": role["id"],
                                "assigned_by": data["invited_by"], "assigned_at": now_iso()})
        invitation = self.create_company_invitation({**data, "company_id": inviter["company_id"]})
        return {"profile": copy.deepcopy(profile), "invitation": invitation}

    @guarded
    def accept_company_invitation(self, user_id):
        now = utcnow()
        invitation = next((item for item in getattr(self, "company_invitations", {}).values()
                           if item["user_id"] == str(user_id) and item["status"] == "pending"), None)
        if not invitation:
            raise NotFoundError("No active invitation was found for this account.")
        if parse_ts(invitation["expires_at"]) <= now:
            invitation["status"] = "expired"
            raise NotFoundError("No active invitation was found for this account.")
        invitation["status"] = "accepted"
        invitation["accepted_at"] = now.isoformat()
        profile = self.update_profile(user_id, {"account_status": "active"})
        return {"profile": profile, "invitation": copy.deepcopy(invitation)}

    @guarded
    def update_profile(self, user_id, data):
        row = self.profiles.get(str(user_id))
        if row is None:
            return None
        if "account_status" in data and data["account_status"] != "active" and row["account_status"] == "active":
            roles = self.get_user_roles(str(user_id))
            if "super_admin" in roles and self.count_active_super_admins() <= 1:
                raise ConflictError("Cannot disable the last active Super Admin.")
        row.update(data); row["updated_at"] = now_iso()
        return copy.deepcopy(row)

    @guarded
    def list_roles(self):
        return copy.deepcopy(list(self.roles.values()))

    @guarded
    def get_role(self, role_id):
        return copy.deepcopy(self.roles.get(str(role_id)))

    @guarded
    def get_role_by_name(self, name):
        return copy.deepcopy(next((r for r in self.roles.values() if r["name"] == name), None))

    @guarded
    def list_permissions(self):
        return copy.deepcopy(list(self.permissions.values()))

    @guarded
    def list_user_role_rows(self, user_id):
        result = []
        for row in self.user_roles:
            if row["user_id"] == str(user_id):
                result.append({**copy.deepcopy(row), "role": copy.deepcopy(self.roles[row["role_id"]])})
        return result

    @guarded
    def get_user_roles(self, user_id):
        return [row["role"]["name"] for row in self.list_user_role_rows(user_id)]

    @guarded
    def get_user_permissions(self, user_id):
        keys = set()
        for name in self.get_user_roles(user_id):
            if ROLE_PERMISSIONS[name] == "*":
                return list(PERMISSION_KEYS)
            keys.update(ROLE_PERMISSIONS[name])
        return sorted(keys)

    @guarded
    def get_role_permissions(self, role_id):
        role = self.roles.get(str(role_id))
        if not role:
            return []
        keys = ROLE_PERMISSIONS[role["name"]]
        return list(PERMISSION_KEYS) if keys == "*" else sorted(keys)

    @guarded
    def assign_user_role(self, user_id, role_id, assigned_by):
        if any(r["user_id"] == str(user_id) and r["role_id"] == str(role_id) for r in self.user_roles):
            raise ConflictError("This role is already assigned to the user.")
        if str(user_id) not in self.profiles or str(role_id) not in self.roles:
            raise ValidationError("User or role does not exist.")
        row = {"id": str(uuid.uuid4()), "user_id": str(user_id), "role_id": str(role_id),
               "assigned_by": str(assigned_by) if assigned_by is not None else None,
               "assigned_at": now_iso()}
        self.user_roles.append(row)
        return copy.deepcopy(row)

    @guarded
    def remove_user_role(self, user_id, role_id):
        target = next((r for r in self.user_roles if r["user_id"] == str(user_id) and r["role_id"] == str(role_id)), None)
        if not target:
            return False
        profile = self.profiles.get(str(user_id))
        role = self.roles[str(role_id)]
        if role["name"] == "super_admin" and profile and profile["account_status"] == "active" and self.count_active_super_admins() <= 1:
            raise ConflictError("Cannot remove the last active Super Admin.")
        self.user_roles.remove(target)
        return True

    @guarded
    def count_active_super_admins(self):
        role_id = next(r["id"] for r in self.roles.values() if r["name"] == "super_admin")
        return sum(1 for row in self.user_roles if row["role_id"] == role_id
                   and self.profiles.get(row["user_id"], {}).get("account_status") == "active")

    @guarded
    def count_company_assistant_users(self, actor_id, company_name):
        actor_id = str(actor_id)
        used_emails = set()
        for profile in self.profiles.values():
            if profile["id"] == actor_id:
                continue
            roles = set(self.get_user_roles(profile["id"]))
            invited_by_actor = str(profile.get("invited_by") or "") == actor_id
            in_company = (
                bool(company_name)
                and (profile.get("company_name") or "").casefold() == company_name.casefold()
                and bool(roles.intersection({"network_operator", "viewer"}))
            )
            if invited_by_actor or in_company:
                used_emails.add(profile["email"].lower())
        for reservation in self.assistant_invite_reservations.values():
            if (
                reservation["status"] == "reserved"
                and (
                    reservation["invited_by"] == actor_id
                    or (
                        company_name
                        and (reservation.get("company_name") or "").casefold() == company_name.casefold()
                    )
                )
            ):
                used_emails.add(reservation["invitee_email"].lower())
        return len(used_emails)

    @guarded
    def reserve_company_assistant_invite(self, actor_id, invitee_email, company_name):
        actor_id = str(actor_id)
        if self.count_company_assistant_users(actor_id, company_name) >= 1:
            return False
        key = (actor_id, invitee_email.lower())
        self.assistant_invite_reservations[key] = {
            "invited_by": actor_id,
            "invitee_email": invitee_email.lower(),
            "company_name": company_name,
            "status": "reserved",
        }
        return True

    @guarded
    def cancel_company_assistant_invite(self, actor_id, invitee_email):
        self.assistant_invite_reservations.pop((str(actor_id), invitee_email.lower()), None)

    @guarded
    def list_user_audit_logs(self, user_id, limit=50, offset=0):
        rows = [r for r in self.audit_logs if r.get("actor_user_id") == str(user_id)]
        rows.sort(key=lambda r: r.get("occurred_at", ""), reverse=True)
        return copy.deepcopy(_page(rows, limit, offset))

    @guarded
    def list_company_audit_logs(self, company_id, limit=50, offset=0):
        rows = [r for r in self.audit_logs if str(r.get("company_id") or "") == str(company_id)]
        rows.sort(key=lambda r: r.get("occurred_at", ""), reverse=True)
        return copy.deepcopy(_page(rows, limit, offset)), len(rows)

    @guarded
    def is_session_revoked(self, session_id):
        return str(session_id) in self.revoked_sessions

    @guarded
    def revoke_session(self, session_id, user_id, expires_at):
        row = {"session_id": str(session_id), "user_id": str(user_id),
               "expires_at": expires_at, "revoked_at": now_iso()}
        self.revoked_sessions[str(session_id)] = row
        return copy.deepcopy(row)

    @guarded
    def consume_auth_rate_limit(self, bucket_key, limit, window_seconds):
        now = time.time()
        item = self.auth_rate_limits.get(str(bucket_key))
        if not item or now - item["started_at"] >= window_seconds:
            self.auth_rate_limits[str(bucket_key)] = {"started_at": now, "count": 1}
            return True
        if item["count"] >= limit:
            return False
        item["count"] += 1
        return True

    # ----------------------------------------------------------------- devices
    @guarded
    def list_devices(self, include_inactive=False, monitoring_enabled=None, status=None,
                     limit=None, offset=0):
        rows = [d for d in self.devices.values()
                if (include_inactive or d["is_active"])
                and (monitoring_enabled is None or d["monitoring_enabled"] == monitoring_enabled)
                and (status is None or d["current_status"] == status)]
        rows.sort(key=lambda d: d["hostname"].lower())
        return copy.deepcopy(_page(rows, limit, offset))

    @guarded
    def get_device(self, device_id):
        return copy.deepcopy(self.devices.get(str(device_id)))

    @guarded
    def get_device_by_hostname(self, hostname):
        for d in self.devices.values():
            if d["hostname"].lower() == str(hostname).lower():
                return copy.deepcopy(d)
        return None

    @guarded
    def create_device(self, data):
        for d in self.devices.values():
            if d["hostname"].lower() == data["hostname"].lower() or d["ip_address"] == data["ip_address"]:
                raise ConflictError("A device with the same hostname or IP address already exists.")
        now = now_iso()
        row = {
            "id": str(uuid.uuid4()), "operating_system": None, "site": "main-site",
            "description": None, "ssh_enabled": False, "monitoring_enabled": True,
            "monitoring_method": "icmp", "monitor_interval_seconds": 5,
            "current_status": "Unknown", "last_latency_ms": None, "last_packet_loss": None,
            "last_checked_at": None, "last_seen_at": None, "is_active": True,
            "created_at": now, "updated_at": now,
        }
        row.update(data)
        if row["monitoring_method"] == "none" and row["monitoring_enabled"]:
            raise ValidationError("monitoring cannot be enabled when monitoring_method is 'none'.")
        self.devices[row["id"]] = row
        return copy.deepcopy(row)

    @guarded
    def update_device(self, device_id, data):
        row = self.devices.get(str(device_id))
        if row is None:
            return None
        for other in self.devices.values():
            if other["id"] != row["id"] and (
                other["hostname"].lower() == str(data.get("hostname", "")).lower()
                or other["ip_address"] == data.get("ip_address")
            ):
                raise ConflictError("A device with the same hostname or IP address already exists.")
        candidate = {**row, **data}
        if candidate["monitoring_method"] == "none" and candidate["monitoring_enabled"]:
            raise ValidationError("monitoring cannot be enabled when monitoring_method is 'none'.")
        candidate["updated_at"] = now_iso()
        self.devices[row["id"]] = candidate
        return copy.deepcopy(candidate)

    # ------------------------------------------------------- monitoring logs
    @guarded
    def insert_monitoring_log(self, data):
        row = {"id": str(uuid.uuid4()), "checked_at": now_iso(), "metadata": {}, **data}
        self.monitoring_logs.append(row)
        return copy.deepcopy(row)

    @guarded
    def list_monitoring_logs(self, device_id=None, status=None, since=None, until=None,
                             limit=50, offset=0):
        rows = [r for r in self.monitoring_logs
                if (device_id is None or r["device_id"] == device_id)
                and (status is None or r["status"] == status)
                and (since is None or parse_ts(r["checked_at"]) >= parse_ts(since))
                and (until is None or parse_ts(r["checked_at"]) <= parse_ts(until))]
        rows.sort(key=lambda r: parse_ts(r["checked_at"]), reverse=True)
        return copy.deepcopy(_page(rows, limit, offset))

    # ------------------------------------------------------------------ rules
    @guarded
    def list_rules(self, enabled_only=False, limit=None, offset=0):
        rows = [r for r in self.rules.values() if not enabled_only or r["enabled"]]
        rows.sort(key=lambda r: r["name"].lower())
        return copy.deepcopy(_page(rows, limit, offset))

    @guarded
    def get_rule(self, rule_id):
        return copy.deepcopy(self.rules.get(str(rule_id)))

    @guarded
    def create_rule(self, data):
        if any(r["name"].lower() == data["name"].lower() for r in self.rules.values()):
            raise ConflictError("A rule with this name already exists.")
        now = now_iso()
        row = {"id": str(uuid.uuid4()), "description": None, "enabled": True, "scope": "global",
               "device_id": None, "created_at": now, "updated_at": now, **data}
        self.rules[row["id"]] = row
        return copy.deepcopy(row)

    @guarded
    def update_rule(self, rule_id, data):
        row = self.rules.get(str(rule_id))
        if row is None:
            return None
        if "name" in data and any(
            r["id"] != row["id"] and r["name"].lower() == data["name"].lower()
            for r in self.rules.values()
        ):
            raise ConflictError("A rule with this name already exists.")
        row.update(data)
        row["updated_at"] = now_iso()
        return copy.deepcopy(row)

    @guarded
    def delete_rule(self, rule_id):
        return self.rules.pop(str(rule_id), None) is not None

    @guarded
    def rule_has_incidents(self, rule_id):
        return any(i["rule_id"] == str(rule_id) for i in self.incidents.values())

    # -------------------------------------------------------------- incidents
    @guarded
    def open_incident(self, device_id, rule_id, title, description, severity,
                      trigger_metric, trigger_value):
        for inc in self.incidents.values():
            if (inc["device_id"] == device_id and inc["rule_id"] == rule_id
                    and inc["status"] in ACTIVE_INCIDENT_STATUSES):
                inc["last_observed_at"] = now_iso()
                return copy.deepcopy(inc), False
        now = now_iso()
        row = {
            "id": str(uuid.uuid4()), "device_id": device_id, "rule_id": rule_id,
            "title": title, "description": description, "severity": severity,
            "status": "open", "triggered_at": now, "resolved_at": None,
            "acknowledged_at": None, "last_observed_at": now,
            "trigger_metric": trigger_metric, "trigger_value": trigger_value,
            "resolution_value": None, "duration_seconds": None, "resolution_reason": None,
            "created_at": now, "updated_at": now,
        }
        self.incidents[row["id"]] = row
        return copy.deepcopy(row), True

    @guarded
    def resolve_incident(self, incident_id, resolution_value, reason):
        row = self.incidents.get(str(incident_id))
        if row is None:
            return None, False
        if row["status"] not in ACTIVE_INCIDENT_STATUSES:
            return copy.deepcopy(row), False
        now = utcnow()
        row.update(
            status="resolved", resolved_at=now.isoformat(), resolution_value=resolution_value,
            resolution_reason=reason, last_observed_at=now.isoformat(), updated_at=now.isoformat(),
            duration_seconds=max(0, int((now - parse_ts(row["triggered_at"])).total_seconds())),
        )
        return copy.deepcopy(row), True

    @guarded
    def acknowledge_incident(self, incident_id):
        row = self.incidents.get(str(incident_id))
        if row is None:
            return None, False
        if row["status"] != "open":
            return copy.deepcopy(row), False
        now = now_iso()
        row.update(status="acknowledged", acknowledged_at=now, updated_at=now)
        return copy.deepcopy(row), True

    @guarded
    def find_active_incident(self, device_id, rule_id):
        for inc in self.incidents.values():
            if (inc["device_id"] == device_id and inc["rule_id"] == rule_id
                    and inc["status"] in ACTIVE_INCIDENT_STATUSES):
                return copy.deepcopy(inc)
        return None

    @guarded
    def get_incident(self, incident_id):
        return copy.deepcopy(self.incidents.get(str(incident_id)))

    @guarded
    def list_incidents(self, status=None, severity=None, device_id=None, rule_id=None,
                       active_only=False, limit=50, offset=0):
        rows = [i for i in self.incidents.values()
                if (status is None or i["status"] == status)
                and (severity is None or i["severity"] == severity)
                and (device_id is None or i["device_id"] == device_id)
                and (rule_id is None or i["rule_id"] == rule_id)
                and (not active_only or i["status"] in ACTIVE_INCIDENT_STATUSES)]
        rows.sort(key=lambda i: parse_ts(i["triggered_at"]), reverse=True)
        return copy.deepcopy(_page(rows, limit, offset))

    # ---------------------------------------------------------------- backups
    @guarded
    def insert_backup(self, data):
        if data.get("status") == "success" and not (data.get("configuration") or "").strip():
            raise ValidationError("A successful backup cannot have an empty configuration.")
        row = {"id": str(uuid.uuid4()), "created_at": now_iso(), "configuration": None,
               "interfaces_snapshot": None, "checksum": None, "completed_at": None,
               "error_message": None, "metadata": {}, **data}
        self.backups[row["id"]] = row
        return copy.deepcopy(row)

    @guarded
    def list_backups(self, device_id=None, status=None, limit=50, offset=0):
        rows = [b for b in self.backups.values()
                if (device_id is None or b["device_id"] == device_id)
                and (status is None or b["status"] == status)]
        rows.sort(key=lambda b: parse_ts(b["created_at"]), reverse=True)
        rows = copy.deepcopy(_page(rows, limit, offset))
        for r in rows:  # list responses never carry configuration contents
            r.pop("configuration", None)
            r.pop("interfaces_snapshot", None)
        return rows

    @guarded
    def get_backup(self, backup_id):
        return copy.deepcopy(self.backups.get(str(backup_id)))

    @guarded
    def latest_successful_backup(self, device_id):
        rows = [b for b in self.backups.values()
                if b["device_id"] == device_id and b["status"] == "success"]
        rows.sort(key=lambda b: parse_ts(b["created_at"]), reverse=True)
        if not rows:
            return None
        row = copy.deepcopy(rows[0])
        row.pop("configuration", None)
        row.pop("interfaces_snapshot", None)
        return row

    # ------------------------------------------------------- automation logs
    @guarded
    def insert_automation_log(self, data):
        row = {"id": str(uuid.uuid4()), "status": "pending", "execution_id": None,
               "response_payload": None, "started_at": None, "completed_at": None,
               "error_message": None, "retry_count": 0, "created_at": now_iso(),
               "incident_id": None, "device_id": None, "rule_id": None, **data}
        self.automation_logs[row["id"]] = row
        return copy.deepcopy(row)

    @guarded
    def update_automation_log(self, log_id, data):
        row = self.automation_logs.get(str(log_id))
        if row is None:
            return None
        row.update(data)
        return copy.deepcopy(row)

    @guarded
    def complete_automation_log(self, log_id, data):
        row = self.automation_logs.get(str(log_id))
        if row is None:
            return None
        if row["status"] not in ("pending", "running"):
            return copy.deepcopy(row)
        row.update(data)
        return copy.deepcopy(row)

    @guarded
    def update_automation_log_if_open(self, log_id, data):
        row = self.automation_logs.get(str(log_id))
        if row is None:
            return None
        if row["status"] not in ("pending", "running") or row.get("completed_at"):
            return copy.deepcopy(row)
        row.update(data)
        return copy.deepcopy(row)

    @guarded
    def get_automation_log(self, log_id):
        return copy.deepcopy(self.automation_logs.get(str(log_id)))

    @guarded
    def list_automation_logs(self, status=None, incident_id=None, device_id=None,
                             limit=50, offset=0):
        rows = [a for a in self.automation_logs.values()
                if (status is None or a["status"] == status)
                and (incident_id is None or a["incident_id"] == incident_id)
                and (device_id is None or a["device_id"] == device_id)]
        rows.sort(key=lambda a: parse_ts(a["created_at"]), reverse=True)
        return copy.deepcopy(_page(rows, limit, offset))

    @guarded
    def find_automation_log(self, incident_id, trigger_type):
        for a in self.automation_logs.values():
            if a["incident_id"] == incident_id and a["trigger_type"] == trigger_type:
                return copy.deepcopy(a)
        return None

    @guarded
    def find_automation_log_for_execution(self, execution_id, device_id, trigger_type):
        for row in self.automation_logs.values():
            if (row.get("workflow_name") == "n8n-config-backup"
                    and row.get("execution_id") == execution_id
                    and row.get("device_id") == device_id
                    and row.get("trigger_type") == trigger_type):
                return copy.deepcopy(row)
        return None

    @guarded
    def list_retryable_automation_logs(self, max_retries):
        rows = [a for a in self.automation_logs.values()
                if a["status"] in ("failed", "pending") and a["retry_count"] < max_retries]
        return copy.deepcopy(rows)
