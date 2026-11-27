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
| `GET /api/auth/me`, `POST /api/auth/onboard-company` | authenticated | profile/role identity and company onboarding |
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
| `POST /api/users/invite` | `users.create` | Company Admin: one assistant (`network_operator` or `viewer`) per inviter/company; `/api/users` is an alias |

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

**Switch monitoring.** In production, switches are checked over TCP/22 because the GNS3 Ethernet switches
do not answer ICMP. Their results are persisted in `monitoring_logs` and available through the
device-filtered monitoring history endpoint.

**n8n.** Events `incident.opened | acknowledged | resolved` are written to `automation_logs` first, then POSTed
on a worker thread - incident handling never waits on n8n and never fails because of it. Each request has a
timeout, `X-NetOps-Event`, `X-NetOps-Delivery` and, when `N8N_WEBHOOK_SECRET` is set,
`X-NetOps-Signature: sha256=<hmac of the raw body>`. At most one event per type per incident (flood guard).
Failed deliveries are retried by the background loop with exponential backoff (`BACKOFF * 2^retries`, capped by
`AUTOMATION_MAX_RETRIES`), or manually via `POST /api/automation/retry/<id>`.

Verify the signature in an n8n **Code** node (the webhook node must keep the raw body):

```js
const crypto = require('crypto');
const expected = 'sha256=' + crypto.createHmac('sha256', $env.NETOPS_WEBHOOK_SECRET)
  .update(rawBodyString).digest('hex');
if (!crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(headerSignature))) throw new Error('bad signature');
```

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
