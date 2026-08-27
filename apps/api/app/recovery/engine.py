"""Pure factual recovery rules; no AI interpretation or message delivery."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from time import perf_counter

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, selectinload

from app.core.timing import elapsed_ms, log_timing
from app.models.domain import (
    AuditEvent, Invoice, InvoiceStatus, PromiseStatus, PromiseToPay,
    RecoveryActionStatus, RecoveryActionType, RecoveryCase, RecoveryState,
)

COOLDOWN_DAYS = 1
MAX_AUTOMATED_ACTIONS = 3
AUTOMATED_ACTION_TYPES = (RecoveryActionType.OUTREACH, RecoveryActionType.FOLLOW_UP)


@dataclass(frozen=True)
class InvoiceFacts:
    state: str
    days_overdue: int
    outstanding_amount: Decimal
    recovered_amount: Decimal
    recovered_percentage: Decimal
    partially_paid: bool


@dataclass(frozen=True)
class PromiseFacts:
    id: uuid.UUID
    state: str
    promised_amount: Decimal
    promised_date: date
    invoice_id: uuid.UUID | None


@dataclass(frozen=True)
class RecoveryEligibility:
    allowed: bool
    blocking_reasons: list[str]
    cooldown_active: bool
    recent_automated_actions: int
    approval_required: bool


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: uuid.UUID
    customer_id: uuid.UUID
    invoice_id: uuid.UUID | None
    current_state: str
    derived_state: str
    invoice: InvoiceFacts | None
    promises: list[PromiseFacts]
    active_dispute: bool
    eligibility: RecoveryEligibility
    next_factual_condition: str


def evaluate_invoice(invoice: Invoice, simulation_date: date) -> InvoiceFacts:
    outstanding = invoice.outstanding_amount
    recovered = invoice.original_amount - outstanding
    percentage = Decimal("0") if invoice.original_amount == 0 else (recovered / invoice.original_amount * 100).quantize(Decimal("0.01"))
    if invoice.issue_date > simulation_date:
        state, overdue_days = "SCHEDULED", 0
    elif outstanding == 0:
        state, overdue_days = "PAID", 0
    elif invoice.due_date < simulation_date:
        state, overdue_days = "OVERDUE", (simulation_date - invoice.due_date).days
    elif invoice.due_date == simulation_date:
        state, overdue_days = "DUE", 0
    else:
        state, overdue_days = "OPEN", 0
    return InvoiceFacts(state, overdue_days, outstanding, recovered, percentage, recovered > 0 and outstanding > 0)


def evaluate_promise(promise: PromiseToPay, simulation_date: date) -> PromiseFacts:
    if promise.status is PromiseStatus.CANCELLED:
        state = "CANCELLED"
    else:
        payment_total = Decimal("0")
        if promise.invoice is not None:
            source_date = promise.source_communication.occurred_at.date() if promise.source_communication else date.min
            payment_total = sum((payment.amount for payment in promise.invoice.payments
                                 if source_date <= payment.payment_date <= simulation_date), Decimal("0"))
        if payment_total >= promise.promised_amount:
            state = "FULFILLED"
        elif promise.promised_date < simulation_date:
            state = "BROKEN"
        else:
            state = "ACTIVE"
    return PromiseFacts(promise.id, state, promise.promised_amount, promise.promised_date, promise.invoice_id)


def _desired_case_state(case: RecoveryCase, invoice_facts: InvoiceFacts | None, promises: list[PromiseFacts], disputed: bool) -> RecoveryState:
    if case.current_state is RecoveryState.CLOSED or case.closed_at is not None:
        return RecoveryState.CLOSED
    if invoice_facts is not None and invoice_facts.state == "PAID":
        return RecoveryState.RESOLVED
    if disputed:
        return RecoveryState.AWAITING_CUSTOMER
    if any(promise.state == "ACTIVE" for promise in promises):
        return RecoveryState.PROMISE_MONITORING
    if any(promise.state == "BROKEN" for promise in promises):
        return RecoveryState.ESCALATED if case.priority.value in {"HIGH", "CRITICAL"} else RecoveryState.IN_PROGRESS
    if invoice_facts is not None and invoice_facts.state == "OVERDUE":
        return RecoveryState.IN_PROGRESS
    return case.current_state


def evaluate_case(case: RecoveryCase, simulation_date: date) -> CaseEvaluation:
    invoice_facts = evaluate_invoice(case.invoice, simulation_date) if case.invoice is not None else None
    promises = [evaluate_promise(promise, simulation_date) for promise in (case.invoice.promises_to_pay if case.invoice else [])]
    disputed = case.invoice is not None and case.invoice.status is InvoiceStatus.DISPUTED
    recent_actions = [
        action for action in case.actions
        if action.action_type in AUTOMATED_ACTION_TYPES and action.status is RecoveryActionStatus.EXECUTED
        and action.executed_at is not None and (simulation_date - action.executed_at.date()).days < COOLDOWN_DAYS
    ]
    reasons: list[str] = []
    if disputed:
        reasons.append("ACTIVE_DISPUTE")
    if invoice_facts is not None and invoice_facts.state == "SCHEDULED":
        reasons.append("INVOICE_SCHEDULED")
    if case.current_state is RecoveryState.CLOSED or case.closed_at is not None:
        reasons.append("CASE_CLOSED")
    if invoice_facts is not None and invoice_facts.state == "PAID":
        reasons.append("INVOICE_PAID")
    if any(promise.state == "ACTIVE" for promise in promises):
        reasons.append("ACTIVE_PAYMENT_PROMISE")
    if recent_actions:
        reasons.append("COOLDOWN_ACTIVE")
    if len(recent_actions) >= MAX_AUTOMATED_ACTIONS:
        reasons.append("MAX_RECENT_AUTOMATED_ACTIONS")
    derived_state = _desired_case_state(case, invoice_facts, promises, disputed)
    if invoice_facts and invoice_facts.state == "SCHEDULED":
        attention = "Invoice is scheduled for a future operating date and is outside current recovery scope."
    elif disputed:
        attention = "Dispute is active; automated recovery must remain on hold."
    elif any(promise.state == "ACTIVE" for promise in promises):
        attention = "Await the active payment promise deadline or a matching payment."
    elif any(promise.state == "BROKEN" for promise in promises):
        attention = "A payment promise is broken and requires factual recovery review."
    elif invoice_facts and invoice_facts.state == "OVERDUE":
        attention = "Outstanding invoice is overdue."
    elif invoice_facts and invoice_facts.state == "PAID":
        attention = "Invoice is fully paid; the case can be resolved."
    else:
        attention = "No additional deterministic condition currently requires attention."
    return CaseEvaluation(
        case.id, case.customer_id, case.invoice_id, case.current_state.value, derived_state.value,
        invoice_facts, promises, disputed,
        RecoveryEligibility(not reasons, reasons, bool(recent_actions), len(recent_actions), case.customer.is_strategic_account), attention,
    )


def case_evaluation_dict(evaluation: CaseEvaluation) -> dict:
    """JSON-friendly rendering while preserving factual Decimal values for FastAPI."""
    return asdict(evaluation)


AuditKey = tuple[str, uuid.UUID, str]


def _existing_audit_keys(session: Session, keys: set[AuditKey]) -> set[AuditKey]:
    """Load all matching append-only audit identities in one database round trip."""
    if not keys:
        return set()
    rows = session.execute(select(
        AuditEvent.entity_type, AuditEvent.entity_id, AuditEvent.event_type,
    ).where(tuple_(
        AuditEvent.entity_type, AuditEvent.entity_id, AuditEvent.event_type,
    ).in_(keys))).all()
    return {(entity_type, entity_id, event_type) for entity_type, entity_id, event_type in rows}


def _audit_once(
    session: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    event_type: str,
    payload: dict,
    occurred_at: datetime,
    *,
    existing: set[AuditKey] | None = None,
) -> None:
    key = (entity_type, entity_id, event_type)
    if existing is None:
        already_recorded = session.scalar(select(AuditEvent.id).where(
            AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id, AuditEvent.event_type == event_type,
        )) is not None
    else:
        already_recorded = key in existing
    if already_recorded:
        return
    session.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type,
                           actor_type="system", payload=payload, occurred_at=occurred_at))
    if existing is not None:
        existing.add(key)


def synchronize_recovery_states(session: Session, simulation_date: date, *, commit: bool = True) -> dict[str, int]:
    """Apply only factual case-state changes and append auditable transition events."""
    started_at = perf_counter()
    stage_started = perf_counter()
    cases = session.scalars(select(RecoveryCase).options(
        selectinload(RecoveryCase.customer), selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )).all()
    load_cases_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    invoices = session.scalars(select(Invoice)).all()
    load_invoices_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    promises = session.scalars(select(PromiseToPay).options(
        selectinload(PromiseToPay.invoice).selectinload(Invoice.payments), selectinload(PromiseToPay.source_communication),
    )).all()
    load_promises_ms = elapsed_ms(stage_started)
    changed = 0
    occurred_at = datetime(simulation_date.year, simulation_date.month, simulation_date.day, tzinfo=UTC)
    stage_started = perf_counter()
    invoice_evaluations = [(invoice, evaluate_invoice(invoice, simulation_date)) for invoice in invoices]
    promise_evaluations = [(promise, evaluate_promise(promise, simulation_date)) for promise in promises]
    case_evaluations = [(case, evaluate_case(case, simulation_date)) for case in cases]
    audit_keys: set[AuditKey] = {
        *(('Invoice', invoice.id, 'INVOICE_OVERDUE_DETECTED') for invoice, facts in invoice_evaluations if facts.state == "OVERDUE"),
        *(('PromiseToPay', promise.id, 'PROMISE_BROKEN_DETECTED') for promise, facts in promise_evaluations if facts.state == "BROKEN"),
        *(('RecoveryCase', case.id, 'RECOVERY_ACTION_BLOCKED_DISPUTE') for case, evaluation in case_evaluations if evaluation.active_dispute),
    }
    evaluate_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    existing_audits = _existing_audit_keys(session, audit_keys)
    load_existing_audits_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    for invoice, facts in invoice_evaluations:
        if facts.state == "OVERDUE":
            _audit_once(session, "Invoice", invoice.id, "INVOICE_OVERDUE_DETECTED", {
                "days_overdue": facts.days_overdue, "outstanding_amount": str(facts.outstanding_amount),
            }, occurred_at, existing=existing_audits)
    for promise, facts in promise_evaluations:
        if facts.state == "BROKEN":
            _audit_once(session, "PromiseToPay", promise.id, "PROMISE_BROKEN_DETECTED", {
                "promised_date": str(facts.promised_date), "promised_amount": str(facts.promised_amount),
            }, occurred_at, existing=existing_audits)
    for case, evaluation in case_evaluations:
        if evaluation.active_dispute:
            _audit_once(session, "RecoveryCase", case.id, "RECOVERY_ACTION_BLOCKED_DISPUTE", {
                "invoice_id": str(case.invoice_id), "reason": "ACTIVE_DISPUTE",
            }, occurred_at, existing=existing_audits)
        if evaluation.current_state != evaluation.derived_state:
            previous_state = case.current_state.value
            case.current_state = RecoveryState(evaluation.derived_state)
            case.updated_at = occurred_at
            changed += 1
            session.add(AuditEvent(entity_type="RecoveryCase", entity_id=case.id, event_type="RECOVERY_CASE_STATE_CHANGED",
                               actor_type="system", payload={
                "from_state": previous_state, "to_state": evaluation.derived_state,
                "reason": evaluation.next_factual_condition,
            }, occurred_at=occurred_at))
    if commit:
        session.commit()
    persist_ms = elapsed_ms(stage_started)
    log_timing(
        "recovery_synchronization_timing",
        total_ms=elapsed_ms(started_at),
        load_cases_ms=load_cases_ms,
        load_invoices_ms=load_invoices_ms,
        load_promises_ms=load_promises_ms,
        evaluate_ms=evaluate_ms,
        load_existing_audits_ms=load_existing_audits_ms,
        persist_ms=persist_ms,
        audit_candidates=len(audit_keys),
        existing_audits=len(existing_audits),
        cases_evaluated=len(cases),
        cases_changed=changed,
        committed=commit,
    )
    return {"cases_evaluated": len(cases), "cases_changed": changed}


def recovery_summary(session: Session, simulation_date: date) -> dict[str, int | Decimal]:
    cases = session.scalars(select(RecoveryCase).options(
        selectinload(RecoveryCase.customer), selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )).all()
    invoices = session.scalars(select(Invoice)).all()
    promises = session.scalars(select(PromiseToPay).options(
        selectinload(PromiseToPay.invoice).selectinload(Invoice.payments), selectinload(PromiseToPay.source_communication),
    )).all()
    evaluations = [evaluate_case(case, simulation_date) for case in cases if case.invoice is None or case.invoice.issue_date <= simulation_date]
    invoice_facts = [(invoice, evaluate_invoice(invoice, simulation_date)) for invoice in invoices]
    promise_facts = [evaluate_promise(promise, simulation_date) for promise in promises]
    overdue_exposure = sum((facts.outstanding_amount for _, facts in invoice_facts if facts.state == "OVERDUE"), Decimal("0"))
    disputed_exposure = sum((invoice.outstanding_amount for invoice, _ in invoice_facts if invoice.status == InvoiceStatus.DISPUTED), Decimal("0"))
    active_promise_exposure = sum((promise.promised_amount for promise in promise_facts if promise.state == "ACTIVE"), Decimal("0"))
    broken_promise_exposure = sum((promise.promised_amount for promise in promise_facts if promise.state == "BROKEN"), Decimal("0"))
    return {
        "total_cases": len(evaluations), "overdue_exposure": overdue_exposure, "disputed_exposure": disputed_exposure,
        "active_promise_exposure": active_promise_exposure, "broken_promise_exposure": broken_promise_exposure,
        "cases_eligible_for_recovery": sum(item.eligibility.allowed for item in evaluations),
        "cases_blocked_by_dispute": sum(item.active_dispute for item in evaluations),
        "cases_awaiting_payment": sum(item.derived_state == RecoveryState.PROMISE_MONITORING.value for item in evaluations),
        "cases_requiring_attention": sum(item.next_factual_condition != "No additional deterministic condition currently requires attention." for item in evaluations),
        "open_cases": sum(item.derived_state not in {RecoveryState.RESOLVED.value, RecoveryState.CLOSED.value} for item in evaluations),
        "active_cases": sum(item.derived_state == RecoveryState.IN_PROGRESS.value for item in evaluations),
        "escalated_cases": sum(item.derived_state == RecoveryState.ESCALATED.value for item in evaluations),
        "on_hold_cases": sum(item.derived_state == RecoveryState.AWAITING_CUSTOMER.value for item in evaluations),
    }
