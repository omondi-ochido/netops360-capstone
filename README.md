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

Copy `frontend/.env.example` to `frontend/.env` to configure the API base URL.

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

The starter API health endpoint is available at `http://localhost:5000/api/health`.
