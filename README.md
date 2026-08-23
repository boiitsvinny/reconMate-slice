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

Open [http://localhost:3000](http://localhost:3000). The page calls `http://localhost:8000/health` and displays its status. Stop the stack with `docker compose down`. Use `docker compose down -v` only if you intentionally want to remove PostgreSQL data.

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

The deterministic seed module creates 24 named B2B customers and 168 invoices as of the virtual date **2026-08-01**. It covers healthy, predictably late, deteriorating, promise-breaking, partial-paying, disputed, strategic high-value, and severely overdue behaviours. Payments, promises, communications, recovery cases/actions, and audit events are generated as a coherent persisted history.

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

## Manual configuration

The checked-in values are development defaults. Before using a shared or production environment, set a strong `POSTGRES_PASSWORD`, set the suitable `DATABASE_URL`, and configure `NEXT_PUBLIC_API_BASE_URL` to the reachable API origin. Do not commit `.env` or `.env.local` files.
