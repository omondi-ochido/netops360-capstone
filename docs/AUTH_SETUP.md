# NetOps360 authentication setup

NetOps360 uses Supabase Auth for credentials and email recovery, and verifies access tokens in Flask. Application roles and permissions are stored in Postgres and checked by the API on every protected request. Account creation is invite only.

## Configure Supabase

1. In Supabase Auth, allow email and password sign-in, set the minimum password length to 12 characters, and disable public sign-ups. Configure a working SMTP sender before inviting users or sending recovery codes.
2. In the Auth URL configuration, add the deployed frontend origin plus `http://localhost:5173/accept-invite` and `http://localhost:5173/reset-password` to the allowed redirect URLs.
3. In the password recovery email template, show the one-time code using `{{ .Token }}`. The user enters that code in NetOps360. Do not replace the code flow with a password reset link. The invitation email should direct the invited user to `/accept-invite`.
4. Use an asymmetric JWT signing key (ES256 or RS256) where the project supports it. The backend reads public keys from the project JWKS endpoint. Existing HS256 keys are checked online with Supabase Auth; the signing secret is never stored in this application.
5. Keep the Supabase service-role key only in the backend secret store. The frontend uses the project URL and publishable key; publishable keys do not authorize application data access because public roles have no table grants or RLS policies.

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

Apply `database/migrations/202611230001_audit_logs.sql` followed by `database/migrations/202611230002_auth_rbac.sql` through the Supabase SQL editor or the project's migration workflow. The second migration creates profiles, roles, permission mappings, session revocation records, and the last-Super-Admin safeguards. It intentionally grants no data access to `anon` or `authenticated`; Flask uses its server-only key after authenticating the caller.

Create the first Auth user from the Supabase dashboard or invite flow. Then, in the SQL editor, replace the UUID and profile data with that Auth user's values:

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

Use this bootstrap only for the first administrator. Subsequent users must be invited from User Management. The application prevents removal or suspension of the last active Super Admin.

## User flows

- **Sign in:** Supabase verifies email/password. The browser sends its short-lived access token as `Authorization: Bearer …`; Flask verifies signature, issuer, audience, expiry, subject, active profile, and revocation state before evaluating permissions.
- **Invitation:** an administrator invites an email and selects an allowed role. The invitee follows the email to `/accept-invite`, sets and confirms a password, then signs in. The API does not expose public account creation.
- **Forgot password:** the user selects **Forgot password?**, enters an email, and receives a one-time recovery code. On `/reset-password`, the user enters the email and code; only after Supabase accepts that code does the UI ask for a new password and confirmation. Passwords must be at least 12 characters. The code is single use and expires according to Supabase Auth settings.
- **Logout:** the API records the current session ID as revoked, then Supabase signs out. If the backend cannot persist revocation, the UI reports that the current browser was signed out but immediate API revocation could not be recorded.

## API permissions

`super_admin` receives every seeded permission. `admin` manages operations and ordinary accounts but cannot manage system settings or grant Super Admin. `network_operator` can operate network resources. `viewer` has read-only operational permissions. The API requires the corresponding permission for every protected operational endpoint. Frontend navigation visibility is convenience only; Flask is the authorization boundary.

The user API is under `/api/users` and includes invite/list/detail/profile/status, role assignment, and audit history. `/api/auth/me` returns the authenticated profile and effective roles/permissions. `/api/auth/logout` revokes the current session.

## Troubleshooting and limitations

- `401`: check the Supabase project URL, JWT issuer/audience, system clock, token signing algorithm, user status, and session revocation.
- `403`: check the role-to-permission mapping in `role_permissions` and whether the user's role assignment exists.
- Recovery email missing: confirm SMTP delivery, recovery template `{{ .Token }}`, provider email limits, and that `/reset-password` is allow-listed.
- Changes to database permissions take effect on the next API request. Existing JWTs do not contain application roles.
- The app has not been connected to a real Supabase project as part of repository implementation. Apply migrations and validate Auth email delivery in a non-production project before deployment.
