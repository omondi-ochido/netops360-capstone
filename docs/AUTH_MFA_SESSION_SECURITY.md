# Authentication MFA, session, and abuse controls

## Implemented in this repository

- The frontend uses the existing Supabase Auth client for TOTP factor enrollment, challenge/verification, and removal. Company Admin, Super Admin, and legacy `admin` role users are directed to the Security page until Flask reports an AAL2 token.
- Flask checks the verified Supabase JWT `aal` claim on permission-protected routes. Sensitive user management operations and revoke-all sessions additionally require an `amr` TOTP verification timestamp from the last five minutes (with a small clock-skew allowance).
- The Security page displays the current session ID indirectly (not the raw access token), assurance level, issue time and expiry. It can revoke the current app session and request global Supabase sign-out. A profile session cutoff provides immediate API rejection for all tokens issued before that cutoff; Flask also keeps its existing revoked-session check.
- Account suspension is checked on each authenticated API request. Session revocation and security events are written to the existing audit log. Passwords, access tokens, TOTP secrets, recovery codes, and configuration contents are not included in event payloads.
- Flask uses a database-backed fixed-window throttle for company registration by source IP and invitations by authenticated inviter. The memory repository has a test implementation. Limits are configurable with `AUTH_REGISTRATION_*` and `AUTH_INVITATION_*` settings.
- Recovery requests now return the same confirmation for all addresses, avoiding a UI account-existence signal. The existing flow uses Supabase recovery OTP verification and 12-character minimum for password changes.

## Controls that require hosted Supabase configuration

1. Enable TOTP MFA and set the project MFA policy to require AAL2 for elevated accounts/operations. Flask checks AAL2 itself, so this must be configured alongside the application policy.
2. Configure email verification, minimum password length (at least 12), recovery OTP expiry, and password-change email notification in Supabase Auth.
3. Enable CAPTCHA and configure its secret/site key for Auth sign-up, sign-in, and recovery if supported by the deployed Supabase setup. The app does not proxy passwords through Flask.
4. Configure Supabase Auth rate limits for password sign-in, sign-up, OTP/recovery, and OAuth. Failed password attempts are handled by Supabase Auth; this repository cannot count them because credential verification occurs directly between the browser and Supabase.
5. Review session timeouts and refresh-token reuse/revocation settings. A browser-local sign-out alone does not revoke other sessions.
6. Apply `database/migrations/202611280002_mfa_sessions_abuse_controls.sql` using the approved Supabase migration process. It has not been applied to a live project as part of this change.
7. Configure reliable server time synchronization because the step-up check evaluates the signed `amr` timestamp.

## Limits and operational notes

- Supabase JS does not expose an active-device/session inventory in this integration. The interface therefore identifies only the current session and offers revoke-all.
- The browser reports that a password update or factor enrollment/removal occurred to the audit endpoint. The endpoint validates authentication and, for factor changes, AAL2; provider-side Auth logs should remain the authoritative evidence of identity-provider changes.
- Rate-limit buckets are keyed by source IP for registration and user ID for invitations. Put Flask behind a trusted proxy with correct `remote_addr` handling; do not trust arbitrary forwarded-IP headers. Add gateway-level IP controls if deployment topology requires them.
- Database migration, hosted Auth configuration, email delivery, and real MFA challenges require live project credentials and were not exercised in local tests.

## Verification performed

Run from repository root:

```sh
cd backend && .venv/bin/pytest -q
cd frontend && npm test && npm run build
```

These checks validate repository-level behavior and compilation only. They do not prove live Supabase configuration, email delivery, or hosted session revocation.
