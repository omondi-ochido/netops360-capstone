# Network Monitoring Capstone

Starter workspace for a network monitoring and management project.

## Project structure

- `frontend/` - React interface built with Vite
- `backend/` - Flask API
- `monitoring/` - monitoring integrations and configuration
- `network_management/` - network inventory and management
- `automation/workflows/` - automation workflows
- `database/` - database schema and related assets
- `gns3/` - GNS3 lab files
- `docs/` - project documentation
- `tests/` - automated tests

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Copy `frontend/.env.example` to `frontend/.env` and set the Supabase project URL, publishable key,
and Flask API base URL. Never put the Supabase service-role key in frontend configuration.

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The API health endpoint is available at `http://localhost:5050/api/health`. Configure Supabase
server credentials, JWT issuer/audience, and `CORS_ALLOWED_ORIGINS` in `backend/.env`.

Apply `database/schema.sql`, then the versioned files under `database/migrations/` in filename
order, then `database/seed.sql` for a new project. See [database/README.md](database/README.md).
See [docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md) for the integration summary and
verification limits.
See [docs/IMPLEMENTATION_AUDIT.md](docs/IMPLEMENTATION_AUDIT.md) for the preliminary audit.
See [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) for Supabase Auth, invite, recovery-code, and RBAC setup.
See [docs/AUTH_IMPLEMENTATION_AUDIT.md](docs/AUTH_IMPLEMENTATION_AUDIT.md) for the auth gap review.
