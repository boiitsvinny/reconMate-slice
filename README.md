# ReconMate

### AI-assisted B2B revenue recovery with deterministic financial decisioning, human control, and auditable outcomes.

**Razorpay Buildathon — Track 03: AI Revenue Recovery**

🌐 **Live Demo:** https://recon-mate-slice.vercel.app/

---

## The Problem

B2B revenue recovery is not simply:

> Invoice overdue → send reminder.

Real recovery teams deal with active disputes, payment promises, broken promises, partial payments, stale actions, duplicate recovery attempts, changing financial facts, and limited operator attention.

The real question is:

> **Who should we act on right now, who should we wait on, and why?**

ReconMate is built around that decision.

---

## What ReconMate Does

ReconMate continuously evaluates a B2B receivables portfolio and helps operators determine:

- which accounts need recovery action;
- which accounts should be monitored;
- which accounts must not be contacted;
- when escalation is justified;
- what changed since the previous decision;
- and what evidence supports every recommendation.

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

Operators can query the live portfolio using natural language.

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

Depending on the request, results can be returned as:

- customer rankings;
- counts;
- exact customer lookups;
- invoice records;
- payment records;
- comparisons;
- latest-cycle changes;
- controlled recovery plans.

Unsupported or out-of-domain requests fail safely instead of silently falling back to unrelated results.

---

## AI Architecture

ReconMate intentionally separates **AI interpretation** from **financial authority**.

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
- recovery outreach is permitted;
- or financial state should change.

Those decisions remain deterministic and auditable.

For reproducible Buildathon evaluation, the hosted sandbox can use deterministic communication interpretation. Model-backed interpretation exists behind a fail-closed provider boundary, and the active interpretation runtime is exposed in the product.

---

## Recovery Safety

ReconMate includes safeguards for:

- active disputes;
- active payment promises;
- paid or closed cases;
- operator approval requirements;
- stale recommendations;
- duplicate actions;
- duplicate provider events;
- recovery cooldowns;
- current-fact revalidation.

A recommendation that was valid earlier cannot simply be executed after the underlying facts change.

---

## Payment Reminder Eligibility

ReconMate does not treat every overdue account as a valid reminder target.

Reminder candidates are separated into operational states such as:

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

Where applicable, ReconMate exposes the existing recovery lifecycle:

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

Provider events are validated before financial state changes, and duplicate events are protected against repeated mutation.

---

## Batch Recovery Proof

ReconMate includes a portfolio-level recovery reconciliation:

```text
Starting overdue exposure
        =
Observed post-due recovery
        +
Remaining overdue exposure
```

The report exposes:

- observed post-due recovery;
- remaining overdue exposure;
- fully and partially recovered accounts;
- deliberate holds;
- disputes;
- promise-monitoring cases;
- unresolved exceptions;
- workflow outcomes;
- payment-level evidence.

### Measurement Boundary

ReconMate explicitly distinguishes:

> **Observed recovery**

from:

> **Recovery causally attributable to ReconMate**

The hosted portfolio is synthetic and reproducible for Buildathon evaluation.

ReconMate does not claim that synthetic payments were caused by the system.

---

## Persisted Operating Simulation

ReconMate includes a deterministic virtual operating environment containing persisted:

- customers;
- invoices;
- payments;
- promises-to-pay;
- disputes;
- communications;
- recovery cases;
- workflow actions;
- audit events.

The current portfolio size and operating state are shown directly in the live application rather than being hardcoded here.

Advancing the operating cycle can introduce changes such as:

- payments;
- broken promises;
- customer delay responses;
- dispute changes;
- exposure changes;
- recommendation changes.

Affected accounts are then reassessed against the latest persisted facts.

---

## Main Product Surfaces

### Home

Portfolio exposure, actionable recovery work, deliberate holds, recent decision changes, simulation controls, and prioritized cases.

### Analyze

Natural-language portfolio querying, filtering, ranking, counts, invoice/payment lookup, comparison, and decision explanation.

### Reports

Batch Recovery Proof, financial reconciliation, holds, exceptions, workflow outcomes, and payment evidence.

### History

Persisted invoice and financial-operational records with search, filtering, sorting, and case drill-down.

### Operator Case Workspace

Current financial state, recovery decision, actionability, blockers, communication evidence, workflow controls, payment/provider lifecycle, and persisted audit history.

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
- Structured natural-language portfolio querying
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

### Backend Tests

```powershell
Set-Location apps/api
pytest
```

### Frontend Validation

```powershell
Set-Location apps/web

npm run lint
npm run typecheck
npm run build
```

---

## Design Principles

ReconMate follows five core rules:

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

Copyright © 2026 boiitsvinny. All rights reserved.

This repository is publicly available for evaluation, demonstration, and portfolio purposes only.

See [LICENSE](./LICENSE) for full terms.
