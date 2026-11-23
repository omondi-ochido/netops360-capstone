# NetOps360 Database

Supabase PostgreSQL schema for NetOps360: six tables, two atomic incident functions, RLS locked down to the backend.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Initial six-table schema, constraints, indexes, triggers, incident RPCs and RLS. Bootstrap for new installs. |
| `migrations/202611230001_audit_logs.sql` | Adds migration version tracking and safe audit records without changing existing records. |
| `seed.sql` | 9 Main Site devices and 3 default rules. Idempotent (`ON CONFLICT DO NOTHING`). |

## Supabase setup

1. Create a project at <https://supabase.com>.
2. For a new project, open **SQL Editor** and run `schema.sql`, then each numbered file under
   `migrations/` in filename order, then `seed.sql`. For an existing project, inspect the actual
   schema and run only migrations whose version is absent from `schema_migrations`.
3. **Project Settings -> API**: copy the **Project URL** and the **service_role** key into `backend/.env`
   (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`).
4. The `service_role` key bypasses RLS. It must live only in the backend `.env`. **Never** send it to the
   React app and never commit it.

Local alternative: any PostgreSQL 14+ works for the schema (`psql -f schema.sql -f seed.sql`). The RLS/role
grants block only runs when the Supabase roles (`anon`, `service_role`) exist.

## Migration process

`schema.sql` is the initial bootstrap, not an upgrade mechanism. Add every future additive migration
as an ordered SQL file and record its version in `schema_migrations` in the same transaction as the
change. Review the target database before applying: the project may already contain schema changes
not represented here. Keep a database backup and apply migrations through the deployment operator's
approved SQL path. Verify the version row and affected objects after applying. The audit migration is
transactional and additive; its rollback drops only `audit_logs` and removes its own version row.
Do not remove `schema_migrations` while other versions are recorded. No live Supabase migration was
run as part of local development; credentials and the Supabase CLI were unavailable.

## Tables

| Table | Purpose | Notable rules |
|---|---|---|
| `devices` | Inventory + latest state | `inet` IP must be a single host; hostname format; unique hostname (case-insensitive) and IP; `monitoring_method='none'` cannot be enabled; soft delete via `is_active` |
| `monitoring_logs` | Append-only check history | loss 0-100, latency >= 0, `received <= sent`; indexed `(device_id, checked_at DESC)` |
| `rules` | Declarative alert rules | `threshold` is JSONB; per-metric validation enforced by a `CHECK` (device_status: string + eq/neq; latency: number >= 0; packet_loss: 0-100); no expressions are ever executed |
| `incidents` | Lifecycle open -> acknowledged -> resolved | **partial unique index** allows one active incident per device+rule; `resolved` <=> `resolved_at` set |
| `config_backups` | Config snapshots | a `success` row cannot have empty config or a missing SHA-256 checksum |
| `automation_logs` | n8n delivery tracking | status pending/running/success/failed, `retry_count`, request/response JSONB |

### Layer 2 switches
The three GNS3 Ethernet switches have no IP stack, so they are seeded `monitoring_enabled=false`,
`monitoring_method='none'`, `current_status='Unmonitored'`. They are never reported Online.

### Relationships and deletion
`monitoring_logs`, `incidents`, `config_backups` and `automation_logs` reference `devices` with
`ON DELETE RESTRICT`; `incidents` also restricts deleting a rule. The API therefore soft-deletes devices
(`is_active=false`) and asks you to disable (not delete) rules that have history.

## Incident functions (called via `supabase.rpc`)

* `open_incident(device, rule, title, description, severity, metric, value)` returns `(incident, created)`.
  Inserts, or - if an active incident exists - only refreshes `last_observed_at`. `created=true` happens once,
  so `incident.opened` is sent exactly once.
* `resolve_incident(id, value, reason)` returns `(incident, changed)`. Computes `duration_seconds`; a no-op on
  an already resolved incident.

## Security

RLS is **enabled on every table with no policies**, so the public `anon` key can read and write nothing.
Only the backend (service-role key) has access. The RPC functions are revoked from `anon`/`authenticated`.
`audit_logs` and `schema_migrations` are also RLS enabled with no public policies. Only `service_role`
has the table privileges required by backend audit inserts. The audit actor is nullable until real
authenticated identities are introduced; request correlation IDs are captured separately.
Configuration backups contain sensitive device config - treat the database and key accordingly.

## Retention (not automated)
`monitoring_logs` grows with every check (about 17k rows/day for 6 devices at 30 s). Consider a periodic
`DELETE FROM monitoring_logs WHERE checked_at < now() - interval '90 days'` (pg_cron) when you need it.

## Verified
Schema run twice, seed run twice, all constraints, both functions, the duplicate index, and delete
protection were exercised against PostgreSQL 16 while building this.
