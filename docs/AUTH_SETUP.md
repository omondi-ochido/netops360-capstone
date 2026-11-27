# NetOps360 authentication setup

NetOps360 uses Supabase Auth for credentials and email recovery, and verifies access tokens in Flask. Application roles and permissions are stored in Postgres and checked by the API on every protected request. Company accounts can be created through the public sign-up form; additional users are invited by administrators.

## Configure Supabase

1. In Supabase Auth, allow email and password sign-in, enable public sign-ups, and set the minimum password length to 12 characters. Configure a working SMTP sender before signing up, inviting users, or sending recovery codes.
2. In the Auth URL configuration, add each deployed frontend origin and the exact callback paths `/accept-invite`, `/reset-password`, and `/auth/callback`. For local development, allow `http://localhost:5173/accept-invite`, `http://localhost:5173/reset-password`, and `http://localhost:5173/auth/callback`.
3. In the password recovery email template, show the one-time code using `{{ .Token }}`. The user enters that code in NetOps360. Do not replace the code flow with a password reset link. The invitation email should direct the invited user to `/accept-invite`.
4. Use an asymmetric JWT signing key (ES256 or RS256) where the project supports it. The backend reads public keys from the project JWKS endpoint. Existing HS256 keys are checked online with Supabase Auth; the signing secret is never stored in this application.
5. Keep the Supabase service-role key only in the backend secret store. The frontend uses the project URL and publishable key; publishable keys do not authorize application data access because public roles have no table grants or RLS policies.

### Social sign-in providers

The login page keeps Google, GitHub, and Microsoft sign-in. Enable and configure each provider in Supabase Auth before offering it; Microsoft uses the `azure` provider and requests the `email` scope. Register Supabase's `/auth/v1/callback` URL with each OAuth provider and allow the frontend `/auth/callback` URL as the app redirect. Supabase supports these redirects through `signInWithOAuth` and automatically links identities that have the same email address. On the first authenticated API request, a valid OAuth identity without a profile or role is provisioned with its JWT email/name/company metadata; the first user becomes Super Admin and later OAuth-only users receive Viewer. See [Supabase social sign-in](https://supabase.com/docs/guides/auth/social-sign-in), [Azure provider setup](https://supabase.com/docs/guides/auth/social-sign-in/auth-azure), and [identity linking](https://supabase.com/docs/guides/auth/auth-identity-linking).

## Environment

Copy `backend/.env.example` to `backend/.env`, and `frontend/.env.example` to `frontend/.env`.

Backend required values:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-server-only-secret
SUPABASE_JWT_ISSUER=https://YOUR_PROJECT_REF.supabase.co/auth/v1
SUPABASE_JWT_AUDIENCE=authenticated
FRONTEND_URL=https://your-frontend.example
CORS_ALLOWED_ORIGINS=https://your-frontend.example
```

Frontend values:

```dotenv
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
VITE_API_BASE_URL=https://your-api.example
```

Never use a `VITE_` variable for a service-role key. `AUTH_TEST_BYPASS` is restricted to test configurations and must not be enabled in a deployed environment.

## Apply schema and bootstrap the first Super Admin

Apply `database/migrations/202611230001_audit_logs.sql`, `database/migrations/202611230002_auth_rbac.sql`, and `database/migrations/202611270001_company_auth_onboarding.sql` in filename order through the Supabase SQL editor or the project's migration workflow. These migrations create profiles, roles, permission mappings, company onboarding fields, session revocation records, and the last-Super-Admin safeguards. The latest migration provisions the first Super Admin atomically; manual SQL bootstrap should only be used for recovery.

Company sign-up and OAuth provisioning assign the first Super Admin automatically. The SQL below is a recovery-only bootstrap for deployments where the initial user must be repaired manually; replace the UUID and profile data with that Auth user's values:

```sql
insert into public.profiles (id, email, full_name, account_status)
values ('AUTH_USER_UUID', 'admin@example.com', 'Initial Administrator', 'active')
on conflict (id) do update set email = excluded.email,
  full_name = excluded.full_name, account_status = 'active';

insert into public.user_roles (user_id, role_id, assigned_by)
select 'AUTH_USER_UUID', id, 'AUTH_USER_UUID'
from public.roles where name = 'super_admin'
on conflict (user_id, role_id) do nothing;
```

The first successful company signup or authenticated OAuth login becomes Super Admin if no Super Admin exists. Later company signups become Company Admins; OAuth-only accounts without an existing profile/role receive the least-privilege Viewer role. The application prevents removal or suspension of the last active Super Admin.

## User flows

- **Sign in:** Supabase verifies email/password. The browser sends its short-lived access token as `Authorization: Bearer …`; Flask verifies signature, issuer, audience, expiry, subject, active profile, and revocation state before evaluating permissions.
- **Company sign-up:** the user enters a full name, work email, 12-character-minimum password, and company name. Supabase stores the name/company metadata and returns to `/auth/callback`; the authenticated API provisions the profile and first role.
- **Invitation:** an administrator invites an email and selects an allowed role. The invitee follows the email to `/accept-invite`, sets and confirms a password, then signs in. A Company Admin may invite only one `network_operator` or `viewer` assistant for their company.
- **Forgot password:** the user selects **Forgot password?**, enters an email, and receives a one-time recovery code. On `/reset-password`, the user enters the email and code; only after Supabase accepts that code does the UI ask for a new password and confirmation. Passwords must be at least 12 characters. The code is single use and expires according to Supabase Auth settings.
- **Logout:** the API records the current session ID as revoked, then Supabase signs out. If the backend cannot persist revocation, the UI reports that the current browser was signed out but immediate API revocation could not be recorded.

## API permissions

`super_admin` receives every seeded permission. `admin` manages operations and ordinary accounts but cannot manage system settings or grant Super Admin. `network_operator` can operate network resources. `viewer` has read-only operational permissions. The API requires the corresponding permission for every protected operational endpoint. Frontend navigation visibility is convenience only; Flask is the authorization boundary.

The user API is under `/api/users` and includes invite/list/detail/profile/status, role assignment, and audit history. `POST /api/users/invite` enforces Company Admin invite limits (`POST /api/users` remains an alias). `/api/auth/me` returns the authenticated profile and effective roles/permissions. `POST /api/auth/onboard-company` updates the signed-in user's company profile. `/api/auth/logout` revokes the current session.

## Troubleshooting and limitations

- `401`: check the Supabase project URL, JWT issuer/audience, system clock, token signing algorithm, user status, and session revocation.
- `403`: check the role-to-permission mapping in `role_permissions` and whether the user's role assignment exists.
- Recovery email missing: confirm SMTP delivery, recovery template `{{ .Token }}`, provider email limits, and that `/reset-password` is allow-listed.
- Changes to database permissions take effect on the next API request. Existing JWTs do not contain application roles.
- The app has not been connected to a real Supabase project as part of repository implementation. Apply migrations and validate Auth email delivery in a non-production project before deployment.
