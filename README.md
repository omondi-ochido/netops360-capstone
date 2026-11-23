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

Copy `frontend/.env.example` to `frontend/.env` to configure the API base URL. `VITE_API_KEY`
is only suitable for a trusted local lab because Vite embeds it in the browser bundle.

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The API health endpoint is available at `http://localhost:5050/api/health`. Configure
`CORS_ALLOWED_ORIGINS` and `API_KEY` in `backend/.env`. Production requires an `API_KEY`, but a
shared key must not be shipped to browser users; deploy behind an authenticated proxy or add user
authentication before exposing protected operations publicly.

Apply `database/schema.sql`, then the versioned files under `database/migrations/` in filename
order, then `database/seed.sql` for a new project. See [database/README.md](database/README.md).
See [docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md) for the integration summary and
verification limits.
See [docs/IMPLEMENTATION_AUDIT.md](docs/IMPLEMENTATION_AUDIT.md) for the preliminary audit.
