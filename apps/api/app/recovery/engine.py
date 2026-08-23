"""Pure factual recovery rules; no AI interpretation or message delivery."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

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
    if outstanding == 0:
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
    if disputed:
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


def _audit_once(session: Session, entity_type: str, entity_id: uuid.UUID, event_type: str, payload: dict, occurred_at: datetime) -> None:
    exists = session.scalar(select(AuditEvent.id).where(
        AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id, AuditEvent.event_type == event_type,
    ))
    if exists is None:
        session.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type,
                               actor_type="system", payload=payload, occurred_at=occurred_at))


def synchronize_recovery_states(session: Session, simulation_date: date) -> dict[str, int]:
    """Apply only factual case-state changes and append auditable transition events."""
    cases = session.scalars(select(RecoveryCase).options(
        selectinload(RecoveryCase.customer), selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )).all()
    invoices = session.scalars(select(Invoice)).all()
    promises = session.scalars(select(PromiseToPay).options(
        selectinload(PromiseToPay.invoice).selectinload(Invoice.payments), selectinload(PromiseToPay.source_communication),
    )).all()
    changed = 0
    occurred_at = datetime(simulation_date.year, simulation_date.month, simulation_date.day, tzinfo=UTC)
    for invoice in invoices:
        facts = evaluate_invoice(invoice, simulation_date)
        if facts.state == "OVERDUE":
            _audit_once(session, "Invoice", invoice.id, "INVOICE_OVERDUE_DETECTED", {
                "days_overdue": facts.days_overdue, "outstanding_amount": str(facts.outstanding_amount),
            }, occurred_at)
    for promise in promises:
        facts = evaluate_promise(promise, simulation_date)
        if facts.state == "BROKEN":
            _audit_once(session, "PromiseToPay", promise.id, "PROMISE_BROKEN_DETECTED", {
                "promised_date": str(facts.promised_date), "promised_amount": str(facts.promised_amount),
            }, occurred_at)
    for case in cases:
        evaluation = evaluate_case(case, simulation_date)
        if evaluation.active_dispute:
            _audit_once(session, "RecoveryCase", case.id, "RECOVERY_ACTION_BLOCKED_DISPUTE", {
                "invoice_id": str(case.invoice_id), "reason": "ACTIVE_DISPUTE",
            }, occurred_at)
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
    session.commit()
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
    evaluations = [evaluate_case(case, simulation_date) for case in cases]
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
        "active_cases": sum(item.derived_state == RecoveryState.IN_PROGRESS.value for item in evaluations),
        "escalated_cases": sum(item.derived_state == RecoveryState.ESCALATED.value for item in evaluations),
        "on_hold_cases": sum(item.derived_state == RecoveryState.AWAITING_CUSTOMER.value for item in evaluations),
    }
