# Authentication implementation test report

Run on 2026-11-23 from the repository worktree.

## Automated checks

| Check | Result |
|---|---|
| `backend/.venv/bin/pytest -q backend/tests` | Passed: 131 passed, 5 skipped |
| `cd frontend && npm test` | Passed: 2 test suites; exercises bearer-token forwarding, refresh/retry behavior, error handling, email recovery OTP type/order, and Google/GitHub/Microsoft OAuth provider routing |
| `cd frontend && npm run build` | Passed: Vite production build completed |
| `git diff --check` | Passed: no whitespace errors |

The five skipped backend tests are integration checks that require a configured Supabase project. The local automated suite uses the in-memory repository and does not make network calls to Supabase.

## Coverage added

- API rejects missing bearer credentials and rejects the former `X-API-Key` mechanism.
- Read and write permission decisions follow the assigned role; suspended users and revoked sessions are denied.
- `/api/auth/me` returns the verified user's profile and permissions; logout revokes that session.
- Frontend API calls attach the Supabase access token and retry once after token refresh.
- Recovery request targets `/reset-password`; code verification uses Supabase `type: "recovery"`; password update occurs after code verification in the page flow.
- Social sign-in dispatches Google, GitHub, and Azure (Microsoft) through Supabase OAuth and returns to the app origin.

## Not verified locally

- Applying either migration to a live Supabase project, including SQL execution under its exact Postgres version and extensions.
- Supabase Auth dashboard settings, SMTP email delivery, invite links, recovery template rendering, and allowed redirect URLs.
- Live OAuth provider credentials, callback allowlists, and each provider's consent/sign-in behavior.
- End-to-end password reset with a real mailbox and Supabase project.

Configure and validate those items in a non-production Supabase project by following [AUTH_SETUP.md](AUTH_SETUP.md) before deployment.

## Company registration follow-up (2026-11-28)

After the secure company-registration work, the backend suite reports **148 passed, 5 skipped**;
the skipped tests require live Supabase credentials. Both frontend test files pass and the Vite
production build succeeds. Added coverage checks that unaffiliated authenticated identities
remain unprovisioned, one normalized company claim creates the Company Admin and atomic audit entry,
duplicates return 409, thread-raced claims create one company, and registration failures leave no
partial in-memory rows. Frontend auth tests verify that company details survive the OAuth/email callback
flow and company name is not sent as authorization metadata.

The local concurrency test exercises the in-memory repository lock. The PostgreSQL advisory lock,
unique constraint, new migration, Supabase Auth callback settings, and RPC transaction have not been
executed against a live project. New Company Admin permissions intentionally remain empty until
company-scoped API access and RLS are implemented.
