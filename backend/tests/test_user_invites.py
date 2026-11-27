from types import SimpleNamespace

from tests.test_auth import AUTH_USER, authenticated_app, setup_identity


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


def test_company_admin_can_invite_only_one_junior_user(make_app, repo):
    identity = setup_identity(repo, role="admin")
    repo.update_profile(AUTH_USER, {"company_name": "Example Co"})
    app = authenticated_app(make_app, repo, identity)
    auth_admin = FakeAuthAdmin()
    app.extensions["netops"].users.auth_admin = auth_admin
    client = app.test_client()
    headers = {"Authorization": "Bearer test-token"}
    viewer_id = repo.get_role_by_name("viewer")["id"]

    first = client.post("/api/users/invite", json={
        "email": "assistant@example.invalid", "full_name": "Assistant", "role_id": viewer_id,
    }, headers=headers)
    second = client.post("/api/users/invite", json={
        "email": "second@example.invalid", "full_name": "Second Assistant", "role_id": viewer_id,
    }, headers=headers)

    invited = first.get_json()["data"]
    profile = repo.get_profile(invited["id"])
    assert first.status_code == 201
    assert profile["company_name"] == "Example Co"
    assert profile["invited_by"] == AUTH_USER
    usage = client.get("/api/auth/me", headers=headers).get_json()["data"]["user"]
    assert usage["assistant_invites_used"] == 1
    assert second.status_code == 403
    assert second.get_json()["error"]["message"] == (
        "Company Admin accounts can invite at most 1 assistant user."
    )
    assert len(auth_admin.invites) == 1


def test_company_admin_cannot_invite_another_admin(make_app, repo):
    identity = setup_identity(repo, role="admin")
    app = authenticated_app(make_app, repo, identity)
    auth_admin = FakeAuthAdmin()
    app.extensions["netops"].users.auth_admin = auth_admin
    admin_id = repo.get_role_by_name("admin")["id"]

    response = app.test_client().post(
        "/api/users/invite",
        json={"email": "another-admin@example.invalid", "full_name": "Another Admin",
              "role_id": admin_id},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    assert auth_admin.invites == []
