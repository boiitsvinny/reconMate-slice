# ReconMate

### AI-assisted B2B revenue recovery with deterministic financial decisioning, human control, and auditable outcomes.

**Razorpay Buildathon — Track 03: AI Revenue Recovery**

🌐 **Live Demo:** https://recon-mate-slice.vercel.app/

---

## Problem

B2B revenue recovery is not simply:

> Invoice overdue → send reminder.

Real recovery teams deal with active disputes, payment promises, broken promises, partial payments, stale actions, duplicate recovery attempts, changing financial facts, and limited operator attention.

The real question is:

> **Who should we act on right now, who should we wait on, and why?**

ReconMate is built around that decision.

---

## What ReconMate Does

ReconMate continuously evaluates a B2B receivables portfolio and helps operators decide:

- which accounts require recovery action;
- which accounts should be monitored;
- which accounts must not be contacted;
- when escalation is justified;
- what evidence supports each decision.

Examples:

```text
Active promise
→ WAIT / MONITOR

Active dispute
→ HOLD OUTREACH

Broken promise
→ INCREASE RECOVERY PRIORITY

High overdue exposure + no blocker
→ CONTROLLED RECOVERY

Paid / closed
→ NO ACTION REQUIRED
```

High risk alone does not mean permission to act.

---

## Command Center

Operators can query the portfolio using natural language.

Examples:

```text
gimme 6 risky clients

late accounts over 8L

broken promises but no disputes

who owes us the most?

payments from this cycle

show invoices older than 45 days

how many accounts are blocked?

compare Mintleaf with Prime
```

ReconMate converts these requests into structured deterministic queries using:

- entity;
- filters;
- exclusions;
- sorting;
- limits;
- operation type.

Supported results include:

- customer rankings;
- counts;
- exact customer lookups;
- invoice records;
- payment records;
- comparisons;
- latest-cycle changes;
- recovery-action plans.

Unsupported requests fail safely instead of falling back to unrelated results.

---

## AI Architecture

ReconMate separates **AI interpretation** from **financial authority**.

```text
Customer communication
        ↓
Interpretation
        ↓
Candidate evidence
        ↓
Validation
        ↓
Deterministic recovery policy
        ↓
Recommendation + blockers
        ↓
Human-controlled workflow
        ↓
Auditable outcome
```

### AI interprets. Policy decides.

Model-backed interpretation can help understand unstructured customer communication.

It cannot independently decide that:

- a payment was received;
- an invoice is paid;
- a dispute is resolved;
- recovery outreach is allowed;
- financial state should change.

Those decisions remain deterministic and auditable.

For reproducible evaluation, the hosted sandbox can use deterministic communication interpretation. Model-backed interpretation sits behind a fail-closed provider boundary.

---

## Recovery Safety

ReconMate includes safeguards for:

- active disputes;
- active payment promises;
- paid or closed cases;
- operator approvals;
- stale recommendations;
- duplicate actions;
- duplicate provider events;
- recovery cooldowns;
- current-fact revalidation.

A recommendation that was valid earlier cannot simply be executed after the underlying facts change.

---

## Payment Reminder Eligibility

ReconMate does not treat every overdue customer as a valid reminder target.

Reminder candidates are separated into states such as:

```text
ELIGIBLE NOW

DEFERRED — ACTIVE PROMISE

BLOCKED — DISPUTE

HUMAN REVIEW / ESCALATION

UNAVAILABLE
```

Blocked or deferred accounts are not treated as sendable reminder candidates.

---

## Payment / Recovery Lifecycle

Where applicable, ReconMate exposes the existing lifecycle:

```text
Recovery decision
      ↓
Operator approval
      ↓
Payment request
      ↓
Provider event
      ↓
Payment persisted
      ↓
Outstanding updated
      ↓
Decision reassessed
```

Important distinctions:

```text
Internal workflow ≠ customer contact

Payment request ≠ payment received

Observed payment ≠ proof ReconMate caused the payment
```

---

## Batch Recovery Proof

ReconMate provides a portfolio-level reconciliation:

```text
Starting overdue exposure
        =
Observed post-due recovery
        +
Remaining overdue exposure
```

The report includes:

- observed recovery;
- remaining exposure;
- recovered and partially recovered accounts;
- disputes;
- promise holds;
- unresolved exceptions;
- payment evidence;
- workflow outcomes.

### Measurement Boundary

ReconMate explicitly distinguishes:

> **Observed recovery**

from:

> **Recovery causally attributable to ReconMate**

The hosted portfolio is synthetic and reproducible for Buildathon evaluation.

ReconMate does not claim synthetic payments were caused by the system.

---

## Main Product Surfaces

### Home

Portfolio exposure, actionable recovery work, deliberate holds, recent decision changes, and prioritized cases.

### Analyze

Natural-language portfolio querying, filtering, comparison, exact entity lookup, and decision explanation.

### Reports

Batch Recovery Proof, reconciliation, holds, exceptions, and payment evidence.

### History

Persisted invoice and financial-operational records.

### Operator Case Workspace

Current financial state, recovery decision, blocker, actionability, communications, workflow, provider lifecycle, and audit history.

---

## Tech Stack

### Frontend

- Next.js
- React
- TypeScript
- TanStack Query

### Backend

- FastAPI
- Python
- SQLAlchemy
- Alembic

### Data

- PostgreSQL
- Supabase

### Intelligence

- Deterministic recovery policy
- Structured natural-language portfolio queries
- Bounded communication interpretation
- Gemini provider support
- Fail-closed validation

### Infrastructure

- Vercel
- Render
- Supabase

---

## Architecture

```text
Next.js / React
      ↓
    Vercel
      ↓
    FastAPI
      ↓
 ┌────┼─────────────┐
 ↓    ↓             ↓
Policy Engine   AI Boundary   Simulation
 └────┼─────────────┘
      ↓
 PostgreSQL / Supabase
```

---

## Run Locally

### Docker

```powershell
Copy-Item .env.example .env
Copy-Item apps/api/.env.example apps/api/.env

docker compose up --build
```

Open:

```text
http://localhost:3000
```

---

## Backend Tests

```powershell
Set-Location apps/api

pytest
```

---

## Frontend Validation

```powershell
Set-Location apps/web

npm run lint
npm run typecheck
npm run build
```

---

## Design Principles

ReconMate follows five rules:

1. **Financial truth stays deterministic.**
2. **High risk does not override stopping rules.**
3. **Material recovery actions remain human-controlled.**
4. **Stale or duplicate actions must not execute.**
5. **Observed payments must not be falsely attributed to the system.**

---

## Track 03 — AI Revenue Recovery

ReconMate focuses on:

```text
Revenue at risk
      ↓
Changing evidence
      ↓
Recovery decision
      ↓
Stopping rules
      ↓
Controlled intervention
      ↓
Observed financial evidence
      ↓
Reassessment
```

The goal is not simply to automate collections.

It is to make revenue recovery:

**safer, explainable, controlled, and measurable.**

---

## License

See [LICENSE](./LICENSE).
