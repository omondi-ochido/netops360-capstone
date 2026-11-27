# NetOps360 Backend

Flask API for monitoring, rules, incidents, configuration backups and n8n automation,
persisted in Supabase PostgreSQL.

## Architecture

```
HTTP routes (routes/)  ->  services (services/)  ->  repository (repositories/)  ->  Supabase
                                  |                         \-> InMemoryRepository (tests)
                                  +-> ping (subprocess), Netmiko (SSH), requests (n8n)
```

* **Application factory**: `create_app()` in `app/__init__.py`; services are wired once in `app/extensions.py`.
* **Repository pattern**: services depend on a repository interface. `SupabaseRepository` is used in
  production, `InMemoryRepository` in tests, so the test-suite needs no network, Supabase or GNS3.
  Swapping to direct PostgreSQL later only requires a new repository class.
* **Single Supabase client** per process (`services/supabase_service.py`).

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the values
```

Apply `database/schema.sql` and `database/seed.sql` first (see `database/README.md`).

```bash
python run.py               # http://localhost:5050
```

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | yes | server-side only |
| `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_AUDIENCE` | yes for auth | token issuer defaults to `<SUPABASE_URL>/auth/v1`; audience defaults to `authenticated` |
| `FRONTEND_URL` | no | allow-listed redirect base for Auth invitations; default `http://localhost:5173` |
| `NETOPS_SSH_USERNAME`, `NETOPS_SSH_PASSWORD` | VyOS router backups | never hardcoded or logged |
| `NETOPS_SWITCH_SSH_USERNAME`, `NETOPS_SWITCH_SSH_PASSWORD` | Alpine/Linux Open vSwitch backups; username defaults to `root` | set the password in the backend environment; never hardcoded or logged |
| `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRET` | for automation | empty URL = automation off, no log noise |
| `N8N_BACKUP_API_TOKEN` | for n8n backup workflows | dedicated scoped bearer token for inventory and backup initiation only |
| `CORS_ALLOWED_ORIGINS` | no | comma-separated; default `http://localhost:5173`; `*` is rejected |
| `MONITORING_ENABLED` / `MONITORING_INTERVAL_SECONDS` / `PING_COUNT` / `PING_INTERVAL_SECONDS` / `PING_TIMEOUT_SECONDS` | no | defaults true / 30 / 2 / 0.2 / 1 |
| `PARTIAL_LOSS_STATUS` | no | status for 0% < loss < 100% (`Warning` or `Online`) |
| `AUTOMATION_TIMEOUT_SECONDS` / `_MAX_RETRIES` / `_BACKOFF_SECONDS` | no | 10 / 5 / 30 |
| `BACKUP_SCHEDULE_SECONDS` | no | 0 = scheduled backups off |
| `BACKUP_ON_CRITICAL_INCIDENT` | no | take an `incident_triggered` backup when a critical incident opens on an SSH device |
| `FLASK_DEBUG` | no | **false by default** |

## API

Responses: lists `{"data": [...], "pagination": {limit, offset, count}, "timestamp"}`; single objects
`{"data": {...}, "timestamp"}`; errors `{"error": {"code", "message"}, "timestamp"}`.
**Exception (backward compatibility):** `GET /api/devices` returns `{"devices": [...], "timestamp": "..."}`.

Protected endpoints require a Supabase bearer token and the listed permission. Public data routes are also authenticated.

| Method & path | Permission | Notes |
|---|---|---|
| `GET /api/health` | | backend + database + monitoring-loop status; 200 `degraded` if the DB is down |
| `GET /api/devices` | `devices.read` | `?status=`, `?limit=&offset=`, `?refresh=true` |
| `GET /api/devices/<id>` | `devices.read` | `<id>` is a UUID **or** hostname |
| `GET /api/auth/me` | authenticated | returns an onboarding-required identity without creating a profile or role |
| `POST /api/auth/register-company` (`/onboard-company` compatibility alias) | authenticated, unonboarded identity | atomically creates company, profile, Company Admin role, and audit record; duplicate normalized names return 409 |
| `POST /api/devices`, `PATCH /api/devices/<id>` | `devices.create/update` | validated; whitelisted fields |
| `DELETE /api/devices/<id>` | `devices.delete` | soft delete |
| `POST /api/devices/<id>/backup` | `backups.create` | manual Netmiko backup |
| `GET /api/devices/<id>/backups` | `backups.read` | metadata only |
| `GET /api/monitoring/*` | `monitoring.read` | history supports `?device_id=<id>&limit=30`, latest and summary |
| `POST /api/monitoring/run` | `monitoring.manage` | immediate check of monitored devices |
| `GET/POST /api/rules`, `GET/PATCH/DELETE /api/rules/<id>` | `rules.read/create/update/delete` | delete refused (409) if incident history exists |
| `GET /api/incidents*` | `incidents.read` | `status, severity, device_id, rule_id, active=true` |
| `POST /api/incidents/<id>/acknowledge`, `/resolve` | `incidents.acknowledge/resolve` | |
| `GET /api/backups*` | `backups.read` | detail form returns configuration text |
| `GET /api/automation/logs` / retry | `automation.read/execute` | |
| `POST /api/users/invite` | `users.create` | Legacy admin invitation flow; `/api/users` is an alias. New `company_admin` role has no permissions until tenant scoping is deployed. |

### Company registration

`POST /api/auth/register-company` requires a valid Supabase bearer token for an identity with no
existing application profile. The compatibility route `/api/auth/onboard-company` uses the same
atomic registration path. The body must contain exactly:

```json
{"full_name":"A. Founder","company_name":"Example Technologies"}
```

Flask uses the verified token subject and email. Name normalization (trim, collapse whitespace,
case-fold) and duplicate enforcement happen in Postgres. Success returns `201` with the company,
profile, `company_admin` role, and permissions. A duplicate normalized company returns `409` with
code `company_already_registered` and the message: “This company is already registered on NetOps360.
An account for this company already exists. Please sign in or contact your company's administrator
for an invitation.” Authentication alone does not provision a profile or role; `/api/auth/me` instead
returns `onboarding_required` for new email and OAuth identities.

## Behaviour

**Monitoring.** A single daemon thread (started by the app factory, never twice per process) runs a
cycle every `MONITORING_INTERVAL_SECONDS`. Each device is checked when `monitor_interval_seconds` has
elapsed. Pings run in parallel (bounded pool) using `subprocess.run([...], shell=False)` with IPs validated
by `ipaddress`; packet loss and average RTT are parsed from real `ping` output (Linux and macOS; Windows is
reported as unsupported). Status: 0% loss `Online`, 100% `Offline`, partial = `PARTIAL_LOSS_STATUS`,
probe failure `Unknown`, disabled/no-method `Unmonitored`. Every result is stored in `monitoring_logs` and
the device row is updated. Production: run with ONE worker, or set `MONITORING_ENABLED=false` on extras.

**Rule engine.** Enabled rules are loaded from the database and validated on every pass; invalid stored rules
are skipped and logged. A rule is `(metric, operator, threshold)` - data only, nothing is evaluated as code.
A missing metric (e.g. latency of an offline host) is *not evaluable*: it neither opens nor resolves.
`Unknown`/`Unmonitored` results are not evaluated.

**Incident lifecycle.** triggered -> `open` -> (`acknowledged`) -> `resolved`. One active incident per
device+rule, enforced by the DB (`open_incident()` + partial unique index). Repeated bad results only
refresh `last_observed_at`. When a rule stops triggering, only *that* device+rule incident auto-resolves,
with `duration_seconds`. A new incident can open after resolution; history is kept.

**Backups.** Netmiko uses `vyos` for routers (`show configuration commands`, `show interfaces`) and
`linux` for switches (interfaces/bridge configuration, active ports, IP addresses and routes). SHA-256
of the config is stored; `changed` compares against the previous successful backup. Failures (auth, timeout,
empty config) are stored as `failed` rows with a safe message; a `success` row can never hold an empty config.

**n8n scheduled and incident backups.** Import `../automation/workflows/scheduled-config-backup.json`,
keep its timezone at Africa/Nairobi, and publish it. It defaults to daily 02:00; edit its Schedule Trigger
for a weekly schedule. `GET /api/devices` returns `{"data":[...],"pagination":...}` and accepts
`limit`/`offset` (maximum 200); the workflow paginates in batches of 200 and selects active routers and
switches. Its POST contract is `{"backup_type":"scheduled"}` or
`{"backup_type":"incident_triggered","incident_id":"<uuid>"}`. Flask alone opens SSH, calculates
checksums, persists configurations and change metadata. Requests with `N8N_BACKUP_API_TOKEN` receive
metadata only, never configuration text; that token is accepted only for device inventory and backup
initiation. Each device call creates an `n8n-config-backup` row in `automation_logs` with the n8n
execution ID and final outcome.

Set `NETOPS_FLASK_BASE_URL` and `NETOPS_BACKUP_API_TOKEN` in n8n; the latter must match Flask's
`N8N_BACKUP_API_TOKEN`. For event-driven backups, set `NETOPS_BACKUP_EVENT_ENABLED=true`,
`NETOPS_BACKUP_WORKFLOW_URL` to the companion webhook URL, and the same high-entropy
`NETOPS_BACKUP_EVENT_TOKEN` in both workflows. Set `NETOPS_BACKUP_ON_CRITICAL=true` for critical
router/switch incidents; selected warnings are opt-in with `NETOPS_BACKUP_ON_WARNING=true`. The
incident-alerting workflow forwards only newly opened selected incidents. Flask's own critical backup
hook is disabled when the n8n API token is configured, so n8n owns those event runs. Without that token,
the existing `BACKUP_ON_CRITICAL_INCIDENT` Flask fallback remains available. Keep
`BACKUP_SCHEDULE_SECONDS=0` to avoid overlapping Flask and n8n schedules.

Set `NETOPS_BACKUP_SUMMARY_CHANNEL` to `telegram`, `email`, or `none`. Telegram needs
`NETOPS_TELEGRAM_BOT_TOKEN` and `NETOPS_TELEGRAM_CHAT_ID`; email needs `NETOPS_BACKUP_SUMMARY_FROM`,
`NETOPS_BACKUP_SUMMARY_TO`, and an n8n SMTP credential named `NetOps360 SMTP`. Summaries contain counts
and per-device metadata only, not configuration text. To prevent overlapping production executions,
configure `N8N_CONCURRENCY_PRODUCTION_LIMIT=1` on the n8n instance. Requests use a 120-second timeout
and scheduled POSTs have at most three attempts, five seconds apart. Flask reuses the same execution log
for retries, returns a prior success instead of taking another snapshot, and caps retries at two after the
initial attempt. Incident-triggered backups are deduplicated by incident and are not automatically retried;
review their failed backup row before manually retrying.

**Switch monitoring.** In production, switches are checked over TCP/22 because the GNS3 Ethernet switches
do not answer ICMP. Their results are persisted in `monitoring_logs` and available through the
device-filtered monitoring history endpoint.

**n8n incident alerting.** The importable workflow is `../automation/workflows/incident-alerting.json`.
It formats open, acknowledged and recovery alerts and routes to one configured channel: Telegram, Discord,
Slack, email, or `none`. Critical alerts are labeled high priority; warning alerts use standard priority.
Informational and acknowledgment messages are opt-in through n8n environment variables.

1. In n8n, import the workflow JSON and activate it. Set `NETOPS_ALERT_CHANNEL` to `discord` (default),
   `telegram`, `slack`, `email`, or `none`.
2. Set `N8N_WEBHOOK_URL` in Flask to the production URL shown by the n8n Webhook node,
   normally `https://<n8n-host>/webhook/netops-incident`.
3. Set the same high-entropy `N8N_WEBHOOK_SECRET` in Flask and n8n as `NETOPS_WEBHOOK_SECRET`.
   n8n Code nodes need the Node `crypto` builtin permitted (`NODE_FUNCTION_ALLOW_BUILTIN=crypto`)
   and environment access enabled (`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`).
4. Set `NETOPS_FLASK_CALLBACK_URL` to the reachable Flask URL plus `/api/automation/callback`.
5. Configure only the chosen integration: `NETOPS_DISCORD_WEBHOOK_URL`; Telegram's
   `NETOPS_TELEGRAM_BOT_TOKEN` and `NETOPS_TELEGRAM_CHAT_ID`; Slack's `NETOPS_SLACK_WEBHOOK_URL`; or
   `NETOPS_ALERT_FROM` and `NETOPS_ALERT_TO` plus an n8n SMTP credential named `NetOps360 SMTP`.
   Keep these values in the n8n environment/credential store, never in the workflow JSON.
6. Optionally set `NETOPS_NOTIFY_INFO=true` and `NETOPS_NOTIFY_ACKNOWLEDGED=true`.

Flask signs the exact outbound JSON bytes in `X-NetOps-Signature: sha256=<hex>`. n8n reports its
execution ID and actual channel result to the callback with the same HMAC scheme. A webhook HTTP 2xx
means only that n8n accepted the event, so the log remains `running` until a signed callback marks it
`success` or `failed`. Callback replays for the same terminal result are idempotent; conflicting results
are rejected. Provider calls have a 10-second timeout; n8n HTTP nodes use bounded retries, and Flask
retries failed/pending webhook deliveries with exponential backoff (`AUTOMATION_BACKOFF_SECONDS *
2^retry_count`) up to `AUTOMATION_MAX_RETRIES`. Duplicate incident events are suppressed per event type.

The workflow is **not operational until a channel credential is configured and an actual test alert
has succeeded**. This repository environment has no live n8n or notification credentials, so no external
delivery is claimed as tested. For local verification, use `pytest` under `backend`; for an integration
check, trigger a test incident and confirm both the channel message and the matching completed row in
`GET /api/automation/logs`.

## Testing

```bash
cd backend
pytest                    # local in-memory suite, no network / Supabase / GNS3 needed
pytest -m integration     # needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (otherwise skipped)
```

## Security notes

* Debug off by default; CORS restricted to configured origins; request bodies whitelisted and validated;
  UUIDs/IPs validated; no SQL is built from input (query builder + RPC with bound parameters).
* Errors returned to clients are generic; details go to the server log, which never contains secrets.
* Supabase Auth verifies credentials and recovery codes. Flask checks bearer JWT signatures, issuer,
  audience, expiry, active profile, revoked session, and database permissions.
* Company accounts can self-register; later staff accounts are invited. Application roles are held in `profiles`, `roles`, `permissions`,
  `user_roles`, and `role_permissions`; do not put role claims in browser-controlled payloads.
* `GET /api/health` is public for health checks. Resource APIs require a bearer token.
* See [../docs/AUTH_SETUP.md](../docs/AUTH_SETUP.md) for Auth settings, migration order, first-admin
  bootstrap, and email OTP password recovery setup.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Configuration error: SUPABASE_URL is required` | `.env` missing/not in `backend/`; copy `.env.example` |
| `/api/health` -> `database: unavailable` | wrong URL/key, project paused, or schema not applied |
| All devices `Unknown` with "ping executable not found" | install `iputils-ping` (Linux) |
| Devices never refresh | `MONITORING_ENABLED=false`, or running under a reloader: use `python run.py` |
| Backup `502 authentication_failed` / `connection_timeout` | check the applicable `NETOPS_SSH_*` or `NETOPS_SWITCH_SSH_*` credentials and route from the backend host to the management network |
| Webhook rows stuck `failed` | check `N8N_WEBHOOK_URL`; retries stop after `AUTOMATION_MAX_RETRIES` - use the retry endpoint |
