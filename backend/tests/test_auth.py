import time


AUTH_USER = "10000000-0000-4000-8000-000000000001"
SESSION = "20000000-0000-4000-8000-000000000001"


def setup_identity(repo, status="active", role="viewer"):
    repo.create_profile({"id": AUTH_USER, "email": "auth-test@example.invalid",
                         "full_name": "Auth Test", "account_status": status})
    assigned_role = repo.get_role_by_name(role)
    repo.assign_user_role(AUTH_USER, assigned_role["id"], AUTH_USER)
    return {"sub": AUTH_USER, "session_id": SESSION, "exp": time.time() + 3600,
            "iss": "https://project.example/auth/v1", "aud": "authenticated"}


def authenticated_app(make_app, repo, identity):
    app = make_app(auth_test_bypass=False, supabase_url="https://project.example",
                   supabase_jwt_issuer="https://project.example/auth/v1")
    app.extensions["jwt_verifier"] = lambda _token, _config: identity
    return app


def test_bearer_token_required_and_api_key_is_rejected(make_app, repo):
    identity = setup_identity(repo)
    client = authenticated_app(make_app, repo, identity).test_client()
    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/devices", headers={"X-API-Key": "anything"}).status_code == 401
    assert client.get("/api/devices", headers={"Authorization": "Bearer test-token"}).status_code == 200


def test_role_permissions_and_inactive_accounts(make_app, repo):
    identity = setup_identity(repo, role="viewer")
    client = authenticated_app(make_app, repo, identity).test_client()
    headers = {"Authorization": "Bearer test-token"}
    assert client.get("/api/devices", headers=headers).status_code == 200
    assert client.post("/api/devices", json={"hostname": "restricted", "ip_address": "192.0.2.8",
                                            "device_type": "host"}, headers=headers).status_code == 403
    repo.update_profile(AUTH_USER, {"account_status": "suspended"})
    assert client.get("/api/devices", headers=headers).status_code == 401


def test_revoked_session_is_denied(make_app, repo):
    identity = setup_identity(repo)
    repo.revoke_session(SESSION, AUTH_USER, "2099-01-01T00:00:00+00:00")
    client = authenticated_app(make_app, repo, identity).test_client()
    assert client.get("/api/devices", headers={"Authorization": "Bearer test-token"}).status_code == 401


def test_identity_endpoint_and_logout_revoke_session(make_app, repo):
    identity = setup_identity(repo, role="admin")
    client = authenticated_app(make_app, repo, identity).test_client()
    headers = {"Authorization": "Bearer test-token"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["id"] == AUTH_USER
    assert "users.create" in response.get_json()["data"]["permissions"]
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/devices", headers=headers).status_code == 401
