import time

from app.utils.exceptions import DatabaseError


AUTH_USER = "10000000-0000-4000-8000-000000000001"
SESSION = "20000000-0000-4000-8000-000000000001"


def setup_identity(repo, status="active", role="viewer"):
    company_id = "90000000-0000-4000-8000-000000000001"
    repo.create_profile({"id": AUTH_USER, "email": "auth-test@example.invalid",
                         "full_name": "Auth Test", "account_status": status,
                         "company_name": "Test Company", "company_id": company_id})
    assigned_role = repo.get_role_by_name(role)
    repo.assign_user_role(AUTH_USER, assigned_role["id"], AUTH_USER)
    return {"sub": AUTH_USER, "session_id": SESSION, "exp": time.time() + 3600,
            "iss": "https://project.example/auth/v1", "aud": "authenticated"}


def authenticated_app(make_app, repo, identity):
    app = make_app(auth_test_bypass=False, supabase_url="https://project.example",
                   supabase_jwt_issuer="https://project.example/auth/v1")
    test_identity = {"aal": "aal2", "iat": time.time(),
                     "amr": [{"method": "totp", "timestamp": time.time()}], **identity}
    app.extensions["jwt_verifier"] = lambda _token, _config: test_identity
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


def test_non_platform_accounts_without_company_membership_cannot_access_tenant_data(make_app, repo):
    identity = setup_identity(repo, role="viewer")
    repo.update_profile(AUTH_USER, {"company_id": None})
    client = authenticated_app(make_app, repo, identity).test_client()
    response = client.get("/api/devices", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "company_membership_required"


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


def test_administrator_mfa_gate_and_step_up_age(make_app, repo):
    identity = setup_identity(repo, role="admin")
    app = authenticated_app(make_app, repo, identity)
    client = app.test_client()
    headers = {"Authorization": "Bearer test-token"}
    app.extensions["jwt_verifier"] = lambda _token, _config: {**identity, "aal": "aal1"}
    denied = client.get("/api/devices", headers=headers)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "mfa_required"

    app.extensions["jwt_verifier"] = lambda _token, _config: {
        **identity, "aal": "aal2", "amr": [{"method": "totp", "timestamp": time.time() - 600}],
    }
    denied = client.post("/api/users/invite", json={
        "email": "new@example.invalid", "full_name": "New User", "role_id": "viewer",
    }, headers=headers)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "step_up_required"


def test_admin_me_reports_mfa_requirement(make_app, repo):
    identity = setup_identity(repo, role="admin")
    app = authenticated_app(make_app, repo, {**identity, "aal": "aal1"})
    response = app.test_client().get("/api/auth/me", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.get_json()["data"]["mfa_required"] is True


def test_registration_throttle_is_shared_by_source_address(make_app, repo):
    identity = new_identity()
    app = authenticated_app(make_app, repo, identity)
    app.extensions["netops"].config.auth_registration_limit = 1
    client = app.test_client()
    headers = {"Authorization": "Bearer test-token"}
    first = client.post("/api/auth/register-company", json={
        "full_name": "Founder", "company_name": "Throttled One",
    }, headers=headers)
    second_identity = new_identity("30000000-0000-4000-8000-000000000002", "other@example.invalid")
    app.extensions["jwt_verifier"] = lambda _token, _config: {**second_identity, "aal": "aal2"}
    second = client.post("/api/auth/register-company", json={
        "full_name": "Founder Two", "company_name": "Throttled Two",
    }, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 429


def test_profile_session_cutoff_revokes_older_tokens(make_app, repo):
    identity = setup_identity(repo, role="viewer")
    app = authenticated_app(make_app, repo, identity)
    repo.update_profile(AUTH_USER, {"sessions_revoked_at": "2099-01-01T00:00:00+00:00"})
    response = app.test_client().get("/api/devices", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "session_revoked"


def new_identity(user_id="30000000-0000-4000-8000-000000000001", email="founder@example.invalid"):
    return {
        "sub": user_id,
        "session_id": "40000000-0000-4000-8000-000000000001",
        "exp": time.time() + 3600,
        "iss": "https://project.example/auth/v1",
        "aud": "authenticated",
        "email": email,
        "app_metadata": {"provider": "google"},
        "user_metadata": {"full_name": "Company Founder", "company_name": "Untrusted Metadata Co"},
    }


def test_new_identity_is_not_provisioned_or_granted_a_role_by_authentication(make_app, repo):
    identity = new_identity()
    client = authenticated_app(make_app, repo, identity).test_client()

    response = client.get("/api/auth/me", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["onboarding_required"] is True
    assert data["roles"] == [] and data["permissions"] == []
    assert repo.get_profile(identity["sub"]) is None
    assert client.get("/api/devices", headers={"Authorization": "Bearer test-token"}).status_code == 403


def test_existing_oauth_identity_signs_into_its_existing_account(make_app, repo):
    identity = new_identity(AUTH_USER, "auth-test@example.invalid")
    setup_identity(repo, role="viewer")
    client = authenticated_app(make_app, repo, identity).test_client()
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.get_json()["data"]["onboarding_required"] is False
    assert response.get_json()["data"]["roles"] == ["viewer"]
    assert repo.companies == {}


def test_company_registration_creates_one_company_admin_and_atomic_audit(make_app, repo):
    identity = new_identity()
    client = authenticated_app(make_app, repo, identity).test_client()

    response = client.post("/api/auth/register-company", json={
        "full_name": "Company Founder", "company_name": "Example Co",
    }, headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 201
    data = response.get_json()["data"]
    company = repo.companies[data["company"]["id"]]
    assert company["initial_admin_id"] == identity["sub"]
    assert repo.get_profile(identity["sub"])["company_id"] == company["id"]
    assert repo.get_user_roles(identity["sub"]) == ["company_admin"]
    assert "super_admin" not in repo.get_user_roles(identity["sub"])
    audit = [row for row in repo.audit_logs if row["action"] == "company_registered"]
    assert len(audit) == 1 and audit[0]["resource_id"] == company["id"]


def test_social_company_registration_requires_company_and_rejects_normalized_duplicate(make_app, repo):
    identity = new_identity()
    client = authenticated_app(make_app, repo, identity).test_client()
    headers = {"Authorization": "Bearer test-token"}
    missing = client.post("/api/auth/register-company", json={"full_name": "Founder"}, headers=headers)
    assert missing.status_code == 400

    success = client.post("/api/auth/register-company", json={
        "full_name": "Founder", "company_name": "Nexyvon Technologies",
    }, headers=headers)
    assert success.status_code == 201
    duplicate_identity = new_identity("30000000-0000-4000-8000-000000000002", "other@example.invalid")
    duplicate_client = authenticated_app(make_app, repo, duplicate_identity).test_client()
    duplicate = duplicate_client.post("/api/auth/register-company", json={
        "full_name": "Other Founder", "company_name": "\tNEXYVON \t TECHNOLOGIES\t",
    }, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["message"] == (
        "This company is already registered on NetOps360. An account for this company already exists. "
        "Please sign in or contact your company's administrator for an invitation."
    )
    assert len(repo.companies) == 1
    assert repo.get_profile(duplicate_identity["sub"]) is None


def test_registration_provisioning_failure_leaves_no_partial_rows(make_app, repo):
    identity = new_identity()
    client = authenticated_app(make_app, repo, identity).test_client()
    app = client.application
    app.extensions["netops"].repo.register_company = lambda _data: (_ for _ in ()).throw(DatabaseError())
    response = client.post("/api/auth/register-company", json={
        "full_name": "Company Founder", "company_name": "Example Co",
    }, headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 503
    assert repo.get_profile(identity["sub"]) is None
    assert repo.companies == {} and repo.audit_logs == []


def test_simultaneous_same_company_claims_have_exactly_one_initial_admin(repo):
    from concurrent.futures import ThreadPoolExecutor

    payloads = [
        {"id": "30000000-0000-4000-8000-000000000001", "email": "a@example.invalid",
         "full_name": "Founder A", "company_name": "Example   Co"},
        {"id": "30000000-0000-4000-8000-000000000002", "email": "b@example.invalid",
         "full_name": "Founder B", "company_name": " example co "},
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(repo.register_company, payloads))
    assert sorted(result["status"] for result in results) == ["company_exists", "registered"]
    assert len(repo.companies) == 1
    initial_admin = next(iter(repo.companies.values()))["initial_admin_id"]
    assert sum(1 for company in repo.companies.values() if company["initial_admin_id"] == initial_admin) == 1
    assert sum(1 for role in repo.get_user_roles(initial_admin) if role == "company_admin") == 1
