# Authentication, Authorization and User Management Audit

This is the baseline audit for the state before the auth implementation. Current implementation and setup notes are recorded at the end.

## Existing implementation

- `frontend/src/pages/Login.jsx` is a demo gate: any non-empty username/password calls `onLogin`; it does not contact an identity provider. OAuth buttons are placeholders.
- `frontend/src/App.jsx` stores an in-memory boolean for authentication, loses it on refresh, and does not restore sessions or protect routes based on server identity.
- `frontend/src/services/api.js` currently sends a Vite-exposed `VITE_API_KEY` as `X-API-Key`; this shared secret is not user authentication and must not be used for a public browser deployment.
- Flask `backend/app/utils/auth.py` only has `require_api_key`; it accepts every request when `API_KEY` is empty. There is no bearer token/JWT verifier, principal context, role/permission check, account-status check, or logout endpoint.
- `backend/app/services/supabase_service.py` constructs only the service-role Supabase client. Its key is backend-only, and this client bypasses RLS.
- `database/schema.sql` has six operational tables and RLS with no public policies. The existing audit migration adds `audit_logs` with nullable `actor_id`; there are no user profiles, roles, permissions or mappings.
- No user or role API/management UI exists. Existing GETs for devices, rules, incidents, monitoring and health are public. Device/rule/incident mutations have optional API-key protection; automation and backup routes require that same optional key.

## Required changes and authorization map

- Add Supabase Auth client configuration and session-aware React context; use invite-only account creation. Add request-access handling only through an administrator invitation.
- Implement login, global logout, session restoration, token refresh/401 handling, account-status verification, invite acceptance, and email-code password recovery.
- Forgot password sends an email using Supabase Auth. The recovery page asks for email and code, verifies the code with recovery type, then requires a new password and matching confirmation before calling Auth to update the password. The Supabase recovery email template must be configured to show the OTP token.
- Verify access JWT signatures through Supabase JWKS for asymmetric keys; check fixed issuer, audience, expiry and UUID subject. Query active profile and permissions on the server for authorization; never read roles from user-editable metadata or request bodies.
- Replace route-level optional API keys with `require_auth` and permission decorators. Keep `/api/health` public. Protect other resource reads and writes with least-privilege keys: `devices.*`, `monitoring.read/manage`, `rules.*`, `incidents.read/acknowledge/resolve`, `automation.read/execute`, `backups.read/create`, `users.*`, `roles.*`, `audit.read`.
- Add private `profiles`, `roles`, `permissions`, `user_roles`, `role_permissions` tables, seeded role/permission mappings, strict RLS/no public policies, and server-side service-role grants only. Extend the existing audit table additively for user actor, description and IP.
- Add invite-only user management endpoints/UI, role assignment checks bounded by the acting administrator's permissions, account suspension checks on every protected request, and last-active-super-admin protection.

## Security risks and constraints

- `service_role` bypasses RLS; API authentication and RBAC must be enforced in Flask for every protected request.
- Do not trust `user_metadata` roles, browser-supplied user IDs as actors, or browser-hidden controls. Permission data comes from database joins for the verified `sub`.
- No bootstrap administrator exists. Document a first-super-admin procedure that starts from an already invited/verified Auth user and is run by an authorized database operator. Do not add default credentials.
- A Supabase asymmetric signing key/JWKS is required for local JWKS verification; document the Auth project signing-key prerequisite. Legacy symmetric HS256 can be verified by the Supabase Auth server rather than reimplementing shared-secret verification.
- Email OTP recovery depends on the project's Auth email template, SMTP delivery, and allowed redirect URL. These deployment settings cannot be committed or verified in the local repository.
- The working tree already contains `frontend/package-lock.json` modifications and an untracked root `package-lock.json` before this task. Preserve both while adding the client dependency.

## Implementation status

Implemented in this repository: invite-only Supabase Auth login and session restoration; email OTP password recovery followed by code verification and new-password confirmation; invite acceptance; Flask JWT verification and permission decorators; active account/session checks; RBAC migration and repositories; user invite/profile/status/role endpoints and UI; and auth setup documentation. The package and API tests are listed in `AUTH_TEST_REPORT.md`.

Deployment-specific SMTP settings, Supabase redirect allowlists, first-admin bootstrap, and live database migration remain operator tasks documented in `AUTH_SETUP.md`. No live Supabase project was available in this implementation session.

## Files changed

- Frontend: shared Supabase client, auth context/provider, API token forwarding, login/recovery/invite pages, guarded App flow, user administration page, permission-aware navigation, env example and pinned package lock.
- Backend: JWT and permission decorators, config, exception types, user/auth routes and services, Supabase and memory repository methods, audit actor handling, existing resource route decorators, tests and requirements.
- Database/docs: additive auth/RBAC migration, `AUTH_SETUP.md`, `AUTH_TEST_REPORT.md`, and backend auth/RBAC tests.
