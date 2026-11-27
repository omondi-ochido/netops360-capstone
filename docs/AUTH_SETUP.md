# NetOps360 authentication setup

NetOps360 uses Supabase Auth for credentials and email recovery, and verifies access tokens in Flask. Application roles and permissions are stored in Postgres and checked by the API on every protected request. Company accounts can be created through the public sign-up form; additional users are invited by administrators.

## Configure Supabase

1. In Supabase Auth, allow email and password sign-in, enable public sign-ups, and set the minimum password length to 12 characters. Configure a working SMTP sender before signing up, inviting users, or sending recovery codes.
2. In the Auth URL configuration, add each deployed frontend origin and the exact callback paths `/accept-invite`, `/reset-password`, and `/auth/callback`. For local development, allow `http://localhost:5173/accept-invite`, `http://localhost:5173/reset-password`, and `http://localhost:5173/auth/callback`.
3. In the password recovery email template, show the one-time code using `{{ .Token }}`. The user enters that code in NetOps360. Do not replace the code flow with a password reset link. The invitation email should direct the invited user to `/accept-invite`.
4. Use an asymmetric JWT signing key (ES256 or RS256) where the project supports it. The backend reads public keys from the project JWKS endpoint. Existing HS256 keys are checked online with Supabase Auth; the signing secret is never stored in this application.
5. Keep the Supabase service-role key only in the backend secret store. The frontend uses the project URL and publishable key; publishable keys do not authorize application data access because public roles have no table grants or RLS policies.

### Social sign-in providers

The login and company sign-up pages support Google, GitHub, and Microsoft. Enable and configure each provider in Supabase Auth; Microsoft uses the `azure` provider and requests the `email` scope. Register Supabase's `/auth/v1/callback` URL with each OAuth provider and allow the frontend `/auth/callback` URL as the app redirect. New social identities receive no profile or role until they submit the required company onboarding form to Flask. Company name in OAuth/user metadata is never used for company ownership. Existing identities with a profile sign in normally. See [Supabase social sign-in](https://supabase.com/docs/guides/auth/social-sign-in), [Azure provider setup](https://supabase.com/docs/guides/auth/social-sign-in/auth-azure), and [identity linking](https://supabase.com/docs/guides/auth/auth-identity-linking).

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
VITE_SUPABASE_MICROSOFT_ENABLED=false
```

Set `VITE_SUPABASE_MICROSOFT_ENABLED=true` only when the Azure/Microsoft provider is enabled and
configured in the Supabase Auth project.

Never use a `VITE_` variable for a service-role key. `AUTH_TEST_BYPASS` is restricted to test configurations and must not be enabled in a deployed environment.

## Apply schema and bootstrap the first Super Admin

Apply all migrations under `database/migrations/` in filename order through the approved database migration workflow, including `20261127205958_secure_company_registration.sql`. Inspect the target schema and migration history first. This migration adds a `companies` entity and a unique normalized-name constraint. It does not merge existing profiles or operational rows.

Public company registration never assigns Super Admin. The SQL below is an operator-only bootstrap for a separately authorized global Super Admin; replace the UUID and profile data with that existing Auth user's values:

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

The first successful registration for a normalized company name creates one Company Admin through a transaction-scoped RPC. Simultaneous duplicate claims serialize on the normalized name and the unique constraint is the final guard. A repeated company name returns HTTP 409. New identities without an application profile can access only identity/onboarding/logout routes until onboarding completes. The `company_admin` role intentionally has no permissions yet: tenant-scoped APIs and RLS have not been implemented, and granting the legacy global `admin` permissions would expose cross-company data. Do not enable multi-company production use until those scopes are deployed and tested. Existing Super Admins retain their roles; no existing users/data are merged or backfilled automatically.

## User flows

- **Sign in:** Supabase verifies email/password. The browser sends its short-lived access token as `Authorization: Bearer …`; Flask verifies signature, issuer, audience, expiry, subject, active profile, and revocation state before evaluating permissions.
- **Company sign-up:** the user enters a full name, work email, 12-character-minimum password, and company name, or starts Google/GitHub/Microsoft OAuth from the same sign-up page. After authentication, the browser submits full name and company name to `POST /api/auth/register-company`. Flask uses the verified JWT subject/email; the database transaction creates the company, profile, Company Admin role, and audit entry. Company name is not trusted from Auth metadata. OAuth users who start from Login are also sent to the onboarding form if no application profile exists.
- **Invitation:** an administrator invites an email and selects an allowed role. The invitee follows the email to `/accept-invite`, sets and confirms a password, then signs in. The existing legacy `admin` invitation flow remains; the new `company_admin` role cannot use administrative APIs until tenant-scoped permissions are deployed.
- **Forgot password:** the user selects **Forgot password?**, enters an email, and receives a one-time recovery code. On `/reset-password`, the user enters the email and code; only after Supabase accepts that code does the UI ask for a new password and confirmation. Passwords must be at least 12 characters. The code is single use and expires according to Supabase Auth settings.
- **Logout:** the API records the current session ID as revoked, then Supabase signs out. If the backend cannot persist revocation, the UI reports that the current browser was signed out but immediate API revocation could not be recorded.

## API permissions

`super_admin` receives every seeded permission. `admin` is the legacy global administrator role. `company_admin` is assigned only by company registration and currently has no permissions until tenant-scoped API access is implemented. `network_operator` can operate network resources. `viewer` has read-only operational permissions. The API requires the corresponding permission for every protected operational endpoint. Frontend navigation visibility is convenience only; Flask is the authorization boundary.

The user API is under `/api/users` and includes invite/list/detail/profile/status, role assignment, and audit history. `/api/auth/me` reports `onboarding_required` without creating a profile or granting a role. `POST /api/auth/register-company` performs company registration; `/api/auth/onboard-company` remains a compatibility alias with the same atomic behavior. `/api/auth/logout` revokes a provisioned profile's current session.

## Troubleshooting and limitations

- `401`: check the Supabase project URL, JWT issuer/audience, system clock, token signing algorithm, user status, and session revocation.
- `403`: check the role-to-permission mapping in `role_permissions` and whether the user's role assignment exists.
- Recovery email missing: confirm SMTP delivery, recovery template `{{ .Token }}`, provider email limits, and that `/reset-password` is allow-listed.
- Changes to database permissions take effect on the next API request. Existing JWTs do not contain application roles.
- The app has not been connected to a real Supabase project as part of repository implementation. Apply migrations and validate Auth email delivery in a non-production project before deployment.
- The database registration RPC and unique constraint have not been applied or tested against a live Supabase project. Existing users/company names need an operator-reviewed migration map. New Company Admins are not yet authorized for company data until tenant-scoped API/RLS work is completed.
