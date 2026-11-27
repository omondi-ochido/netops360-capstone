from datetime import timedelta
from types import SimpleNamespace

from app.utils.timeutil import utcnow
from tests.test_auth import authenticated_app


class FakeAuthAdmin:
    def __init__(self):
        self.invites = []
        self.next_id = 1

    def invite_user_by_email(self, email, options):
        self.invites.append((email, options))
        user_id = f"50000000-0000-4000-8000-{self.next_id:012d}"
        self.next_id += 1
        return SimpleNamespace(user=SimpleNamespace(id=user_id))

    def delete_user(self, user_id):
        return None

    def update_user_by_id(self, user_id, attributes):
        return None


def company_admin(repo, user_id, email, company_name):
    company = repo.register_company({"id": user_id, "email": email, "full_name": "Company Admin",
                                     "company_name": company_name})["company"]
    return {"sub": user_id, "session_id": f"20000000-0000-4000-8000-{user_id[-12:]}",
            "exp": 1924905600, "iss": "https://project.example/auth/v1", "aud": "authenticated"}, company


def test_company_admin_can_invite_many_users_with_company_bound_expiring_records(make_app, repo):
    identity, company = company_admin(repo, "10000000-0000-4000-8000-000000000011", "admin-a@example.invalid", "Company A")
    app = authenticated_app(make_app, repo, identity)
    auth_admin = FakeAuthAdmin()
    app.extensions["netops"].users.auth_admin = auth_admin
    client = app.test_client()
    headers = {"Authorization": "Bearer test-token"}
    viewer_id = repo.get_role_by_name("viewer")["id"]
    manipulated = client.post("/api/users/invite", json={
        "email": "manipulated@example.invalid", "full_name": "Manipulated", "role_id": viewer_id,
        "company_id": "90000000-0000-4000-8000-000000000099",
    }, headers=headers)
    assert manipulated.status_code == 400
    assert auth_admin.invites == []

    responses = [client.post("/api/users/invite", json={
        "email": f"member{n}@example.invalid", "full_name": f"Member {n}", "role_id": viewer_id,
    }, headers=headers) for n in (1, 2)]

    assert [response.status_code for response in responses] == [201, 201]
    for response in responses:
        invite = response.get_json()["data"]["invitation"]
        profile = repo.get_profile(invite["user_id"])
        assert invite["company_id"] == company["id"]
        assert invite["invited_by"] == identity["sub"]
        assert invite["role_id"] == viewer_id
        assert invite["status"] == "pending"
        assert profile["company_id"] == company["id"]
        assert profile["account_status"] == "pending"
        assert invite["expires_at"] > utcnow().isoformat()
    assert len(auth_admin.invites) == 2
    audit = client.get("/api/company/audit-logs", headers=headers)
    assert audit.status_code == 200
    assert any(row["action"] == "invited" for row in audit.get_json()["data"])


def test_company_admin_can_suspend_and_reactivate_same_company_users(make_app, repo):
    identity, company = company_admin(repo, "10000000-0000-4000-8000-000000000013", "admin-a@example.invalid", "Company A")
    member_id = "50000000-0000-4000-8000-000000000013"
    repo.create_profile({"id": member_id, "email": "member@example.invalid", "full_name": "Member",
                         "company_name": "Company A", "company_id": company["id"], "account_status": "active"})
    client = authenticated_app(make_app, repo, identity).test_client()
    app_container = client.application.extensions["netops"]
    app_container.users.auth_admin = FakeAuthAdmin()
    headers = {"Authorization": "Bearer test-token"}

    suspended = client.patch(f"/api/users/{member_id}/status", json={"status": "suspended"}, headers=headers)
    assert suspended.status_code == 200
    assert repo.get_profile(member_id)["account_status"] == "suspended"
    reactivated = client.patch(f"/api/users/{member_id}/status", json={"status": "active"}, headers=headers)
    assert reactivated.status_code == 200
    assert repo.get_profile(member_id)["account_status"] == "active"
    assert client.patch(f"/api/users/{identity['sub']}/status", json={"status": "suspended"}, headers=headers).status_code == 403


def test_company_admin_cannot_access_or_manage_another_company_users(make_app, repo):
    identity_a, company_a = company_admin(repo, "10000000-0000-4000-8000-000000000021", "admin-a@example.invalid", "Company A")
    identity_b, company_b = company_admin(repo, "10000000-0000-4000-8000-000000000022", "admin-b@example.invalid", "Company B")
    member_id = "50000000-0000-4000-8000-000000000099"
    repo.create_profile({"id": member_id, "email": "member-b@example.invalid", "full_name": "Member B",
                         "company_name": "Company B", "company_id": company_b["id"], "account_status": "active"})
    viewer_id = repo.get_role_by_name("viewer")["id"]
    repo.assign_user_role(member_id, viewer_id, identity_b["sub"])

    app = authenticated_app(make_app, repo, identity_a)
    client = app.test_client()
    headers = {"Authorization": "Bearer test-token"}
    listed = client.get("/api/users", headers=headers)
    assert listed.status_code == 200
    assert all(row.get("company_id") == company_a["id"] for row in listed.get_json()["data"])
    assert client.get(f"/api/users/{member_id}", headers=headers).status_code == 404
    assert client.patch(f"/api/users/{member_id}/status", json={"status": "suspended"}, headers=headers).status_code == 404
    assert client.post(f"/api/users/{member_id}/roles", json={"role_id": viewer_id}, headers=headers).status_code == 404


def test_company_admin_cannot_promote_self_or_assign_admin_roles(make_app, repo):
    identity, _company = company_admin(repo, "10000000-0000-4000-8000-000000000031", "admin-a@example.invalid", "Company A")
    client = authenticated_app(make_app, repo, identity).test_client()
    headers = {"Authorization": "Bearer test-token"}
    super_admin_id = repo.get_role_by_name("super_admin")["id"]
    company_admin_id = repo.get_role_by_name("company_admin")["id"]
    assert client.post(f"/api/users/{identity['sub']}/roles", json={"role_id": super_admin_id}, headers=headers).status_code == 403
    assert client.post(f"/api/users/{identity['sub']}/roles", json={"role_id": company_admin_id}, headers=headers).status_code == 403


def test_invitation_acceptance_uses_authenticated_user_and_rejects_expired_or_tampered_requests(make_app, repo):
    identity, company = company_admin(repo, "10000000-0000-4000-8000-000000000041", "admin-a@example.invalid", "Company A")
    invited_id = "50000000-0000-4000-8000-000000000041"
    role_id = repo.get_role_by_name("viewer")["id"]
    repo.create_profile({"id": invited_id, "email": "invitee@example.invalid", "full_name": "Invitee",
                         "company_id": company["id"], "company_name": company["company_name"],
                         "invited_by": identity["sub"], "account_status": "pending"})
    invitation = repo.create_company_invitation({"user_id": invited_id, "email": "invitee@example.invalid",
        "full_name": "Invitee", "company_id": company["id"], "role_id": role_id,
        "invited_by": identity["sub"], "expires_at": (utcnow() + timedelta(hours=1)).isoformat()})
    repo.assign_user_role(invited_id, role_id, identity["sub"])
    invite_identity = {**identity, "sub": invited_id, "session_id": "20000000-0000-4000-8000-000000000042"}
    client = authenticated_app(make_app, repo, invite_identity).test_client()
    headers = {"Authorization": "Bearer test-token"}

    tampered = client.post("/api/users/accept-invitation", json={"company_id": "different", "role_id": "different"}, headers=headers)
    assert tampered.status_code == 400
    identity_response = client.get("/api/auth/me", headers=headers)
    assert identity_response.status_code == 200
    assert identity_response.get_json()["data"]["invitation_required"] is True
    accepted = client.post("/api/users/accept-invitation", json={}, headers=headers)
    assert accepted.status_code == 200
    assert repo.get_profile(invited_id)["company_id"] == company["id"]
    assert repo.get_profile(invited_id)["account_status"] == "active"
    assert repo.company_invitations[invitation["id"]]["status"] == "accepted"

    expired_id = "50000000-0000-4000-8000-000000000042"
    repo.create_profile({"id": expired_id, "email": "expired@example.invalid", "full_name": "Expired",
                         "company_id": company["id"], "account_status": "pending"})
    expired = repo.create_company_invitation({"user_id": expired_id, "email": "expired@example.invalid",
        "full_name": "Expired", "company_id": company["id"], "role_id": role_id,
        "invited_by": identity["sub"], "expires_at": (utcnow() - timedelta(seconds=1)).isoformat()})
    repo.assign_user_role(expired_id, role_id, identity["sub"])
    expired_client = authenticated_app(make_app, repo, {**identity, "sub": expired_id,
        "session_id": "20000000-0000-4000-8000-000000000043"}).test_client()
    expired_response = expired_client.post("/api/users/accept-invitation", json={}, headers=headers)
    assert expired_response.status_code == 404
    assert repo.get_profile(expired_id)["account_status"] == "pending"
    assert repo.company_invitations[expired["id"]]["status"] == "expired"
