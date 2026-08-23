# ReconMate

ReconMate is a closed-loop AI revenue recovery system for B2B receivables. This initial vertical-slice foundation supplies a Next.js frontend, FastAPI backend, PostgreSQL, and an end-to-end health check. Recovery workflow and AI logic are intentionally not implemented yet.

## Repository layout

```text
reconMate/
├── apps/
│   ├── api/                 # FastAPI REST service
│   │   ├── app/             # Routes and configuration
│   │   ├── tests/           # Backend tests
│   │   ├── .env.example
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── web/                 # Next.js App Router application
│       ├── src/app/         # Pages and styles
│       ├── src/components/  # UI components
│       ├── .env.local.example
│       ├── Dockerfile
│       └── package.json
├── compose.yaml             # PostgreSQL + API + frontend stack
└── .env.example             # Compose environment template
```

## Prerequisites

- Node.js 20.9 or newer and npm
- Python 3.11 through 3.14
- Docker Desktop (recommended for PostgreSQL and the full stack)

## Run with Docker Compose

```powershell
Copy-Item .env.example .env
Copy-Item apps/api/.env.example apps/api/.env
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The browser calls the API origin configured by `NEXT_PUBLIC_API_URL` (which defaults to `http://localhost:8000` in the supplied local configuration). Stop the stack with `docker compose down`. Use `docker compose down -v` only if you intentionally want to remove PostgreSQL data.

## Run applications locally

Start PostgreSQL:

```powershell
Copy-Item .env.example .env
docker compose up postgres -d
```

Start the API in one terminal:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Set-Location apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Start the frontend in another terminal:

```powershell
Set-Location apps/web
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

## Checks

```powershell
Set-Location apps/api
.\.venv\Scripts\Activate.ps1
pytest

Set-Location ..\web
npm run lint
npm run typecheck
```

## Database domain model

The API uses SQLAlchemy with PostgreSQL and Alembic. The initial migration defines the core receivables-recovery model:

- `customers` own invoices, promises to pay, communications, and recovery cases.
- `invoices` carry dated original and outstanding balances; `payments` are linked to their invoice.
- `promises_to_pay` belong to a customer and can optionally reference an invoice and the communication from which they were captured.
- `communications` record inbound/outbound channel activity and reserve explicit metadata fields for future AI processing, without making AI calls.
- `recovery_cases` can cover a customer or a specific invoice; `recovery_actions` record their planned, approval-gated, and executed operational steps.
- `audit_events` are append-only-style records for state-history consumers. They intentionally have no mutable timestamp fields; application code should only insert them.
- `simulation_states` stores the named global virtual date (`default`) for the later simulation engine.

The model uses PostgreSQL enums for business states, foreign keys with restrictive deletion for financial ownership, and `SET NULL` for optional contextual references. Amounts and promise confidence also have database-level validation constraints.

Apply migrations after starting PostgreSQL:

```powershell
Set-Location apps/api
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

When using Docker Compose, run the same command in the API container:

```powershell
docker compose exec api alembic upgrade head
```

`GET /health` remains a liveness check. `GET /health/ready` performs a lightweight database query and returns `503` if PostgreSQL is unavailable.

## Synthetic development portfolio

The deterministic seed module creates 56 B2B customers and 296 invoices as of the virtual date **2026-08-01**. It covers healthy, predictably late, deteriorating, promise-breaking, partial-paying, disputed, strategic high-value, and severely overdue behaviours. Payments, promises, communications, recovery cases/actions, simulation state/events, and audit events are generated as a coherent persisted history.

Seed a fresh development database:

```powershell
docker compose exec api python -m app.seed
```

To explicitly replace existing development domain data with the same deterministic world:

```powershell
docker compose exec api python -m app.seed --reset
```

Read-only inspection endpoints are available at `GET /customers`, `GET /customers/{customer_id}`, `GET /invoices`, and `GET /portfolio/summary`.

## Deterministic recovery evaluation

The recovery engine uses the simulation date to calculate invoice and payment-promise facts without AI interpretation. Invoice facts are `PAID`, `OPEN`, `DUE`, or `OVERDUE`; case states map to the existing lifecycle values `NEW`, `IN_PROGRESS`, `AWAITING_CUSTOMER` (on hold), `PROMISE_MONITORING`, `ESCALATED`, `RESOLVED`, and `CLOSED`.

Run the explicit state synchronisation after seeding to append audit events and apply only factual case transitions:

```powershell
docker compose exec api python -m app.recovery
```

It blocks automated recovery for active disputes, active payment promises, closed/paid cases, and a short action cooldown. Read-only engine endpoints are `GET /recovery/cases`, `GET /recovery/cases/{case_id}`, `GET /recovery/cases/{case_id}/evaluation`, `GET /customers/{customer_id}/recovery-status`, and `GET /recovery/portfolio/summary`.

## Production deployment

Production uses three independently hosted components:

```text
Browser -> Vercel (Next.js) -> Render (FastAPI) -> Supabase (PostgreSQL)
```

### 1. Create the Supabase database

Create a Supabase project and copy its **Session pooler** connection string from the project's **Connect** dialog. Use the session pooler on port `5432` because Render connects to external databases over IPv4. Keep the database password URL-encoded if it contains reserved URL characters. The resulting value has this shape:

```text
postgresql://postgres.your-project-ref:your-url-encoded-password@aws-0-your-region.pooler.supabase.com:5432/postgres
```

Do not add this value to a tracked file. From a local PowerShell terminal, install the backend and apply all existing Alembic migrations to Supabase:

```powershell
Set-Location apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
$env:DATABASE_URL = "<SUPABASE_SESSION_POOLER_DATABASE_URL>"
alembic upgrade head
alembic current
```

Seed the deterministic ReconMate portfolio after the migration succeeds:

```powershell
python -m app.seed
```

The seed command intentionally refuses to overwrite an existing portfolio. Use `python -m app.seed --reset` only when you explicitly want to replace all existing ReconMate domain data. Remove the credential from the current terminal when finished:

```powershell
Remove-Item Env:DATABASE_URL
```

### 2. Deploy the native Python API to Render

The root `render.yaml` defines a free native Python Web Service. It does not use the backend Dockerfile and does not provision a Render database. The equivalent manual Render settings are:

```text
Root Directory: apps/api
Language: Python 3
Build Command: pip install --upgrade pip && pip install .
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health/ready
Instance Type: Free
```

Set these Render environment variables:

```text
APP_ENV=production
DATABASE_URL=<SUPABASE_SESSION_POOLER_DATABASE_URL>
API_CORS_ORIGINS=https://your-project.vercel.app
AI_PROVIDER=mock
SIMULATION_TICK_INTERVAL_SECONDS=15
```

`DATABASE_URL` is server-only and must never be exposed through a `NEXT_PUBLIC_` variable. Render supplies `PORT`; do not set it manually. Multiple allowed browser origins can be supplied as a comma-separated list in `API_CORS_ORIGINS`. Do not use `*` in production.

The free Render service does not provide Shell access or pre-deploy commands, so migrations and seeding are deliberately run from a local terminal against Supabase before the API is deployed. Verify the deployed service at `https://your-render-service.onrender.com/health/ready`.

### 3. Connect the Vercel frontend

Deploy the Next.js application to Vercel with `apps/web` as its Root Directory. Set the Vercel Production environment variable below **before** deploying, using the Render service's HTTPS URL with no trailing slash:

```text
NEXT_PUBLIC_API_URL=https://your-render-service.onrender.com
```

Redeploy the Vercel project after adding or changing this build-time public variable. The frontend never receives the Supabase connection string and continues to access data only through the FastAPI contracts.

## Manual configuration

The checked-in values are development defaults. Before using a shared or production environment, set a suitable `DATABASE_URL`, configure the API's `API_CORS_ORIGINS` with explicit browser origins, and set Vercel's `NEXT_PUBLIC_API_URL` to the reachable API origin. Do not commit `.env` or `.env.local` files.
