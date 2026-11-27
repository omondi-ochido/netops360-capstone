# Company Admins, Invitations, and Tenant Authorization

## Existing roles

The repository already defines `super_admin`, legacy `admin`, `company_admin`,
`network_operator`, and `viewer`. This work retains those role names. New
companies receive `company_admin` through the atomic company registration
function. Company Admins can invite `network_operator` or `viewer` accounts;
they cannot assign `company_admin`, `admin`, or `super_admin`.

Company Admin permissions include company user management, company audit
history, and read access to company operational records. Operator write access
comes from the `network_operator` role. `system.manage` remains platform-level.

## Invitation flow

`POST /api/users/invite` accepts `email`, `full_name`, optional `phone_number`,
and `role_id`. It does not accept a company ID. Flask derives company ID from
the authenticated Company Admin profile, validates the allowed role, sends a
Supabase Auth invitation, then calls the service-role-only
`provision_company_invitation` database function. That function atomically
creates a pending profile, role assignment, and invitation record with a
24-hour expiry.

The invitee follows the Supabase link, chooses a password, and the frontend
calls `POST /api/users/accept-invitation` with an empty body. The backend takes
the user ID from the verified access token. The acceptance function checks the
pending invitation, expiry, company association, email, and stored role before
activating the account. Invitation company and role cannot be overridden by
request fields.

## Tenant enforcement

The Flask Supabase repository applies the authenticated profile's `company_id`
to reads, updates, deletes, inserts, and upserts for profiles, devices,
monitoring logs, rules, incidents, configuration backups, automation logs, and
audit records. A user with `system.manage` is handled as a platform operator.
Operational child rows derive company ownership from their device when created
by trusted background jobs. Supabase `anon` and `authenticated` roles have no
table grants for these records; the service-role key remains backend-only.

The migration adds nullable `company_id` columns to existing operational
tables. Existing records are deliberately left unassigned: company names and
hostnames alone are not reliable evidence for transferring operational data.
Until each legacy record is reviewed and backfilled, it remains invisible to
company-scoped users. Non-platform accounts with no company association are
also denied tenant API access until their membership is reviewed. The legacy
`admin` role is preserved; review each such account and explicitly associate
it with a company or move a verified platform administrator to `super_admin`
before rollout. Use reviewed ownership mapping before setting any
`company_id`.

## API authorization

| Endpoint | Company Admin behavior |
|---|---|
| `GET /api/users` | Lists users from the authenticated company only |
| `POST /api/users/invite` | Invites a user into that company with an allowed role |
| `GET/PATCH /api/users/<id>` | Reads or updates same-company eligible users |
| `PATCH /api/users/<id>/status` | Suspends or reactivates same-company active users |
| `POST/DELETE /api/users/<id>/roles` | Assigns/removes only permitted roles for same-company users |
| `GET /api/company/audit-logs` | Returns audit events associated with the authenticated company |
| `POST /api/users/accept-invitation` | Activates only the authenticated invitee's unexpired invitation |

Company Admins cannot manage their own account through the user-management
API, another Company Admin, or accounts outside their company. Pending invitees
must accept their invitation rather than being activated by an administrator.

## Applying and checking the migration

Apply `database/migrations/202611280001_company_user_invitations.sql` after the
company registration migration. The Supabase CLI is not installed in the
current workspace, and no connected project was used, so the SQL has not been
applied to a live database. Validate it on a local/staging Supabase instance
before production rollout, then run the repository's database tests and
Supabase advisors.

After applying it:

1. Review current profiles and operational records; create an explicit mapping
   from legacy rows to company IDs.
2. Backfill only rows whose owner is verified. Do not infer ownership by
   case-insensitive company-name matching alone.
3. Set Supabase Auth invitation-link expiry to no more than 24 hours so it
   matches `company_invitations.expires_at`.
4. Verify browser clients use only the Supabase publishable key and backend
   environment uses the service-role key.
5. Test two companies with their own Auth users and direct Data API requests;
   the browser roles should receive no direct table access.

## Verification performed locally

Backend: `153 passed, 5 skipped` using the in-memory repository. The tests cover
two-company user isolation, invitation creation/acceptance/expiry, role
boundaries, self-promotion prevention, suspension/reactivation, and company
audit history. Frontend Node tests and the Vite production build also pass.

These checks do not exercise the SQL migration, Supabase Auth email delivery,
or production RLS configuration. Those remain staging verification tasks.
