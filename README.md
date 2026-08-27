# ReconMate

**AI-assisted revenue recovery for B2B receivables — with deterministic financial decisioning, human control, and auditable outcomes.**

ReconMate is a revenue-recovery operations system built for **Razorpay Buildathon — Track 03: AI Revenue Recovery**.

It continuously reassesses overdue B2B receivables using invoice state, payment behaviour, promises-to-pay, disputes, communications, and recovery history to answer three questions:

1. **Which accounts actually need intervention?**
2. **What is the safest next recovery action?**
3. **When should the system deliberately do nothing?**

ReconMate is intentionally not an autonomous collections spam bot.

Its core thesis is simple:

> **Revenue recovery requires knowing when to act, when to wait, and being able to prove why.**

---

## Live Demo

**Application:**
https://recon-mate-slice.vercel.app/

**API:**
https://reconmate-api.onrender.com/

The hosted build contains a deterministic synthetic B2B portfolio designed for reproducible evaluation.

---

# What ReconMate Does

ReconMate models receivables recovery as a continuously changing operating system rather than a static overdue-invoice list.

A customer can move through states such as:

**healthy → overdue → promise active → promise broken → recovery prioritized → approval required → workflow completed → recovered / held / escalated**

Every reassessment uses the latest available facts.

### ReconMate can:

* identify overdue and at-risk receivables;
* prioritize recovery cases using deterministic policy;
* distinguish between cases that require action and cases that should be deliberately held;
* monitor active promises-to-pay;
* detect broken promises;
* block recovery while an active dispute exists;
* prepare controlled escalation when facts justify it;
* require operator approval before material recovery actions;
* reject stale or duplicate workflow actions;
* maintain an auditable history of decisions and actions;
* simulate changing portfolio conditions across operating cycles;
* reconcile batch-level recovery evidence without claiming unsupported causal impact.

---

# The Important Part: Intelligent Restraint

Most collection systems reduce the problem to:

> **Overdue → contact customer**

ReconMate does not.

Examples:

### Active payment promise

The customer has committed to pay within an active promise window.

**Decision:** Monitor.
**Do not escalate yet.**

### Active dispute

The outstanding amount is currently disputed.

**Decision:** Hold recovery.
**Do not create conflicting collection pressure.**

### Broken promise

A promised payment date has passed without supporting payment evidence.

**Decision:** Increase recovery priority or prepare escalation.

### Severe overdue exposure

Material balance, high aging, repeated broken promises, and no active blocker.

**Decision:** Prioritize controlled recovery action.

The system treats **not acting** as a valid and sometimes safer recovery decision.

---

# Decision Architecture

ReconMate deliberately separates probabilistic interpretation from financial authority.

```text
Customer / portfolio evidence
            ↓
Communication interpretation
            ↓
Candidate structured facts
            ↓
Validation / confidence boundary
            ↓
Deterministic recovery policy
            ↓
Recommendation + blockers + stopping rules
            ↓
Human approval where required
            ↓
Bounded recovery workflow
            ↓
Outcome + audit evidence
```

## AI interprets. Policy decides.

Model-backed intelligence is useful for interpreting ambiguous or unstructured customer communication.

It is **not** allowed to independently decide:

* whether money has actually been received;
* whether an invoice is paid;
* whether a dispute is resolved;
* whether financial escalation is allowed;
* whether a customer should be contacted;
* whether a recovery workflow may bypass policy.

Financial authority remains deterministic and auditable.

For reproducible evaluation, the hosted sandbox can use deterministic communication interpretation. Model-backed interpretation sits behind a **fail-closed provider boundary**.

If interpretation is unavailable, malformed, ambiguous, or insufficiently grounded, ReconMate does not invent a financial fact.

---

# Recovery Decisioning

The recovery engine evaluates facts including:

* outstanding exposure;
* invoice age;
* days overdue;
* payment behaviour;
* active promises-to-pay;
* broken promises;
* disputes;
* recent recovery activity;
* recovery cooldowns;
* case state;
* previous actions;
* behavioural deterioration.

Each recommendation can expose:

* current recommendation;
* contributing factors;
* score contribution;
* blockers;
* actionability;
* evidence used;
* what changed since the previous evaluation;
* what future fact would change the decision.

This keeps recovery logic inspectable instead of hiding it behind an unexplained AI score.

---

# Human Control & Workflow Safety

ReconMate treats recovery actions as controlled financial operations.

Depending on the case, workflows can require explicit operator approval before execution.

The workflow layer is designed around:

* approval gates;
* stale-recommendation checks;
* duplicate-action prevention;
* re-evaluation before execution;
* action cooldowns;
* stopping rules;
* dispute blockers;
* active-promise blockers;
* audit history.

A recommendation that was safe earlier cannot simply be executed after the underlying facts have materially changed.

---

# Batch Recovery Proof

ReconMate includes a **Batch Recovery Proof** designed to make recovery reporting inspectable rather than promotional.

It reconciles a defined overdue cohort across:

```text
Starting overdue exposure
        =
Observed post-due recovery
        +
Remaining overdue exposure
```

The report also surfaces:

* recovered and remaining exposure;
* partial and complete recovery;
* blocked cases;
* deliberate holds;
* unresolved exceptions;
* approval state;
* stopping-rule outcomes;
* payment provenance;
* recovery-case history;
* policy baseline comparisons.

## Measurement boundary

ReconMate reports **observed post-due recovery** from persisted payment records. **No causal attribution is claimed.**

The synthetic sandbox demonstrates recovery operations and reconciliation mechanics. It does not present simulated portfolio outcomes as production merchant revenue or claim unsupported causal attribution.

---

# Demo Simulation

The application includes a persisted virtual operating environment.

The deterministic development portfolio contains:

* **56 B2B customers**
* **296 invoices**
* payments;
* promises-to-pay;
* customer communications;
* disputes;
* recovery cases;
* recovery actions;
* audit events;
* simulation history.

Customer behaviours include:

* healthy payers;
* predictably late customers;
* deteriorating accounts;
* broken promises;
* partial payments;
* disputes;
* strategic high-value customers;
* severely overdue accounts.

Advancing the operating cycle changes portfolio facts and forces ReconMate to reassess affected recovery decisions.

---

# 5-Minute Judge Path

For the fastest evaluation:

### 1. Home

Open the portfolio overview.

Inspect:

* outstanding exposure;
* active recovery cases;
* changed decisions;
* recovery queue;
* deliberate holds.

### 2. Open a recovery case

Inspect:

* why the account is prioritized or held;
* source facts;
* blockers;
* score contributions;
* previous vs. current decision;
* what would change the recommendation.

### 3. Review the recommended workflow

Observe:

* actionability;
* approval requirement;
* stopping rules;
* duplicate / stale-action protection;
* recorded workflow outcome.

### 4. Advance the operating cycle

Use the simulation controls to introduce new portfolio facts.

Watch ReconMate reassess affected accounts and change recommendations when evidence changes.

### 5. Reports

Open **Batch Recovery Proof**.

Inspect:

* starting exposure;
* observed post-due payments;
* remaining exposure;
* holds and exceptions;
* reconciliation;
* audit provenance.

### 6. Analyze / History

Use the deeper decision-analysis and historical views to inspect why decisions changed over time.

---

# Product Surfaces

### Home

Operational portfolio overview and recovery queue.

### Reports

Batch Recovery Proof and portfolio-level outcome evidence.

### Analyze

Decision inspection and recovery reasoning.

### History

Invoice and portfolio history across the simulated operating environment.

---

# Tech Stack

## Frontend

* Next.js
* React
* TypeScript
* App Router

## Backend

* FastAPI
* Python
* SQLAlchemy
* Alembic

## Data

* PostgreSQL
* Supabase in production

## Deployment

```text
Browser
   ↓
Vercel — Next.js frontend
   ↓
Render — FastAPI backend
   ↓
Supabase — PostgreSQL
```

## Intelligence

* deterministic recovery policy;
* deterministic evaluation and stopping rules;
* model-backed communication interpretation through a provider boundary;
* Google Gemini provider support;
* confidence validation and fail-closed handling.

---

# Repository Structure

```text
reconMate/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   ├── tests/
│   │   ├── .env.example
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── web/
│       ├── src/app/
│       ├── src/components/
│       ├── .env.local.example
│       ├── Dockerfile
│       └── package.json
│
├── compose.yaml
├── render.yaml
├── .env.example
├── LICENSE
└── README.md
```

---

# Run Locally

## Prerequisites

* Node.js 20.9+
* npm
* Python 3.11–3.14
* Docker Desktop recommended

---

## Full stack with Docker Compose

```powershell
Copy-Item .env.example .env
Copy-Item apps/api/.env.example apps/api/.env

docker compose up --build
```

Open:

```text
http://localhost:3000
```

Stop the environment:

```powershell
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete PostgreSQL data.

---

# Run Applications Separately

## Start PostgreSQL

```powershell
Copy-Item .env.example .env
docker compose up postgres -d
```

## Start API

```powershell
Copy-Item apps/api/.env.example apps/api/.env

Set-Location apps/api

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

uvicorn app.main:app --reload --port 8000
```

## Start frontend

In another terminal:

```powershell
Set-Location apps/web

Copy-Item .env.local.example .env.local

npm install
npm run dev
```

---

# Database Setup

Apply migrations:

```powershell
Set-Location apps/api
.\.venv\Scripts\Activate.ps1

alembic upgrade head
```

With Docker:

```powershell
docker compose exec api alembic upgrade head
```

---

# Seed the Demo Portfolio

Create the deterministic development portfolio:

```powershell
docker compose exec api python -m app.seed
```

Reset it explicitly:

```powershell
docker compose exec api python -m app.seed --reset
```

The reset command intentionally replaces existing development-domain data.

---

# Recovery Evaluation

Run factual recovery-state synchronization:

```powershell
docker compose exec api python -m app.recovery
```

The engine calculates receivable and promise state using the active simulation date and applies only factual case transitions.

Automated recovery is blocked for conditions including:

* active disputes;
* active promises;
* paid or closed cases;
* applicable recovery cooldowns.

---

# Checks

## Backend

```powershell
Set-Location apps/api
.\.venv\Scripts\Activate.ps1

pytest
```

## Frontend

```powershell
Set-Location apps/web

npm run lint
npm run typecheck
```

---

# Health Endpoints

Basic API liveness:

```text
GET /health
```

Database readiness:

```text
GET /health/ready
```

`/health/ready` performs a lightweight database check and returns `503` when PostgreSQL is unavailable.

---

# Core Read APIs

Examples include:

```text
GET /customers
GET /customers/{customer_id}

GET /invoices

GET /portfolio/summary

GET /recovery/cases
GET /recovery/cases/{case_id}
GET /recovery/cases/{case_id}/evaluation

GET /customers/{customer_id}/recovery-status
GET /recovery/portfolio/summary
```

The product contains additional APIs for simulation, workflow, intelligence, evidence, and reporting flows used by the live application.

---

# Production Deployment

The hosted architecture is:

```text
Vercel
   ↓
Render
   ↓
Supabase
```

The frontend receives only the public FastAPI origin.

Database credentials and AI-provider credentials remain server-side.

Production deployments use explicit CORS configuration rather than wildcard origins.

Pending Alembic migrations are applied before the backend begins serving the newer API version.

---

# Environment Notes

Do not commit:

```text
.env
.env.local
```

Sensitive values such as the database connection string and model-provider API keys must remain server-side.

The frontend should receive only values intentionally exposed through `NEXT_PUBLIC_*`.

---

# Scope

ReconMate is currently a **Buildathon evaluation sandbox**, not a production collections deployment.

The project demonstrates:

* continuously reassessed B2B recovery decisions;
* deterministic financial policy;
* controlled recovery workflows;
* AI-assisted communication interpretation boundaries;
* operator approval;
* recovery safety;
* auditability;
* simulation;
* batch-level recovery evidence.

External customer communication and production money movement are outside the claims made by the current sandbox unless explicitly represented as simulated.

---

# Why ReconMate

Revenue recovery should not mean contacting every overdue customer more aggressively.

A useful system needs to understand:

> **Who needs action?**

> **Who should be left alone?**

> **What changed?**

> **Why is this action safe?**

> **When must the workflow stop?**

> **What actually happened afterward?**

ReconMate is built around those questions.

---

## License

See [`LICENSE`](./LICENSE) for repository licensing terms.
