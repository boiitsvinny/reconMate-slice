"""Persisted simulation ticks that change facts before recovery is evaluated."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.intelligence.service import persist_analysis
from app.intelligence.operational_schemas import IntelligenceResult
from app.intelligence.operational_service import evaluate_case_intelligence
from app.intelligence.transitions import compare_intelligence
from app.commands.tools import CommandTools
from app.models.domain import (
    AuditEvent, Communication, CommunicationChannel, CommunicationDirection, Customer,
    Invoice, InvoiceStatus, Payment, PromiseStatus, PromiseToPay, RecoveryCase,
    RecoveryPriority, RecoveryState, SimulationEvent, SimulationState,
)
from app.recovery.engine import synchronize_recovery_states
from app.recommendations.service import recommend_case
from app.seed.portfolio import seed_database


def _when(state: SimulationState) -> datetime:
    return datetime(state.simulation_date.year, state.simulation_date.month, state.simulation_date.day, 10, tzinfo=UTC)


def _event_id(cycle: int, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/{cycle}/{ordinal}")


def _audit(db: Session, entity_type: str, entity_id: uuid.UUID, event_type: str, payload: dict[str, Any], when: datetime) -> None:
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type, actor_type="simulation", payload=payload, occurred_at=when))


def _case_for(db: Session, invoice: Invoice, when: datetime) -> RecoveryCase:
    case = db.scalar(select(RecoveryCase).where(RecoveryCase.invoice_id == invoice.id, RecoveryCase.closed_at.is_(None)))
    if case is None:
        case = RecoveryCase(customer_id=invoice.customer_id, invoice=invoice, current_state=RecoveryState.NEW,
                            priority=RecoveryPriority.HIGH if invoice.outstanding_amount >= Decimal("150000") else RecoveryPriority.NORMAL,
                            opened_at=when, updated_at=when)
        db.add(case)
        db.flush()
        _audit(db, "RecoveryCase", case.id, "SIMULATION_RECOVERY_EXPOSURE_ENTERED", {"invoice_id": str(invoice.id)}, when)
    return case


def _record(db: Session, state: SimulationState, ordinal: int, event_type: str, *, customer: Customer | None = None, invoice: Invoice | None = None, case: RecoveryCase | None = None, metadata: dict[str, Any]) -> dict[str, Any]:
    event = SimulationEvent(id=_event_id(state.cycle, ordinal), cycle=state.cycle, event_type=event_type,
                            customer_id=customer.id if customer else (invoice.customer_id if invoice else None),
                            invoice_id=invoice.id if invoice else None, recovery_case_id=case.id if case else None,
                            metadata_=metadata, occurred_at=_when(state))
    db.add(event)
    return {"id": str(event.id), "type": event_type, "customer_id": str(event.customer_id) if event.customer_id else None,
            "invoice_id": str(event.invoice_id) if event.invoice_id else None, "case_id": str(event.recovery_case_id) if event.recovery_case_id else None, "metadata": metadata}


def _communication(db: Session, state: SimulationState, customer: Customer, invoice: Invoice, content: str, ordinal: int) -> Communication:
    message = Communication(id=uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/communication/{state.cycle}/{ordinal}"), customer=customer,
                            direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.PORTAL, content=content, occurred_at=_when(state))
    db.add(message); db.flush()
    analysis = persist_analysis(message)
    db.add(analysis)
    return message


@dataclass(frozen=True)
class _IntelligenceSnapshot:
    result: IntelligenceResult
    recommendation: str


def _capture_intelligence(db: Session) -> dict[tuple[str, str], _IntelligenceSnapshot]:
    """Capture an ephemeral comparison baseline; no intelligence history is persisted."""
    tools = CommandTools(db)
    snapshots: dict[tuple[str, str], _IntelligenceSnapshot] = {}
    for result in tools.get_portfolio_intelligence().customers:
        snapshots[("CUSTOMER", result.entity_id)] = _IntelligenceSnapshot(result, result.recommendation.action.value)
    for case in tools.cases():
        result = evaluate_case_intelligence(case, tools.simulation_date)
        snapshots[("RECOVERY_CASE", str(case.id))] = _IntelligenceSnapshot(
            result,
            recommend_case(case, tools.simulation_date).recommended_action.value,
        )
    return snapshots


def _build_transitions(
    db: Session,
    before: dict[tuple[str, str], _IntelligenceSnapshot],
    events: list[dict[str, Any]],
    cycle: int,
) -> list[dict[str, Any]]:
    tools = CommandTools(db)
    transitions = []
    for event in events:
        targets = [("CUSTOMER", event.get("customer_id")), ("RECOVERY_CASE", event.get("case_id"))]
        for entity_type, entity_id in targets:
            if not entity_id:
                continue
            if entity_type == "CUSTOMER":
                result = tools.get_customer_intelligence(uuid.UUID(entity_id))
                current_recommendation = result.recommendation.action.value if result else None
            else:
                case = tools.get_case(entity_id)
                result = tools.get_case_intelligence(uuid.UUID(entity_id)) if case else None
                current_recommendation = recommend_case(case, tools.simulation_date).recommended_action.value if case else None
            if result is None or current_recommendation is None:
                continue
            previous = before.get((entity_type, entity_id))
            transition = compare_intelligence(
                before=previous.result if previous else None,
                after=result,
                previous_recommendation=previous.recommendation if previous else None,
                current_recommendation=current_recommendation,
                cycle=cycle,
                event_id=event["id"],
                event_type=event["type"],
            )
            transitions.append(transition.model_dump(mode="json"))
    return transitions


def run_tick(db: Session) -> dict[str, Any]:
    state = db.scalar(select(SimulationState).where(SimulationState.name == "default").with_for_update())
    if state is None:
        raise ValueError("Synthetic simulation state has not been seeded.")
    before_intelligence = _capture_intelligence(db)
    state.cycle += 1
    state.simulation_date += timedelta(days=1)
    db.flush()
    when, cycle, events = _when(state), state.cycle, []
    invoices = db.scalars(select(Invoice).options(selectinload(Invoice.customer), selectinload(Invoice.payments), selectinload(Invoice.promises_to_pay)).order_by(Invoice.due_date, Invoice.id)).all()
    # Business time, not wall-clock time, determines when an operational invoice
    # crosses into overdue status. Disputed and settled documents retain their facts.
    for invoice in invoices:
        if invoice.outstanding_amount > 0 and invoice.due_date < state.simulation_date and invoice.status in {InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID}:
            previous = invoice.status.value
            invoice.status = InvoiceStatus.OVERDUE
            _audit(db, "Invoice", invoice.id, "SIMULATION_INVOICE_BECAME_OVERDUE", {"previous_status": previous, "due_date": str(invoice.due_date)}, when)
    open_invoices = [item for item in invoices if item.outstanding_amount > 0 and item.status is not InvoiceStatus.DISPUTED]
    active_promises = db.scalars(select(PromiseToPay).options(selectinload(PromiseToPay.invoice), selectinload(PromiseToPay.customer)).where(PromiseToPay.status == PromiseStatus.ACTIVE).order_by(PromiseToPay.promised_date)).all()
    ordinal = 0
    # A deterministic rotating scenario. Each arm validates candidates before mutating.
    scenario = cycle % 6
    if scenario == 1 and open_invoices:
        invoice = open_invoices[0]; previous = invoice.outstanding_amount
        amount = previous if cycle % 12 == 1 else (previous / Decimal("2")).quantize(Decimal("0.01"))
        invoice.outstanding_amount -= amount; invoice.status = InvoiceStatus.PAID if invoice.outstanding_amount == 0 else InvoiceStatus.PARTIALLY_PAID
        payment = Payment(invoice=invoice, amount=amount, payment_date=state.simulation_date, reference=f"SIM-{cycle:04d}"); db.add(payment)
        for promise in invoice.promises_to_pay:
            if promise.status is PromiseStatus.ACTIVE and amount >= promise.promised_amount: promise.status = PromiseStatus.FULFILLED
        case = _case_for(db, invoice, when); _audit(db, "Invoice", invoice.id, "SIMULATION_PAYMENT_RECEIVED", {"previous_outstanding": str(previous), "payment_amount": str(amount), "resulting_outstanding": str(invoice.outstanding_amount)}, when)
        events.append(_record(db, state, ordinal, "FULL_PAYMENT_RECEIVED" if invoice.outstanding_amount == 0 else "PARTIAL_PAYMENT_RECEIVED", invoice=invoice, case=case, metadata={"previous_outstanding": str(previous), "payment_amount": str(amount), "resulting_outstanding": str(invoice.outstanding_amount)}))
    elif scenario == 2 and active_promises:
        promise = active_promises[0]; previous_date = promise.promised_date
        # The event advances the factual deadline into the past before recording
        # the missed promise; it never relies on an interpretation to break one.
        promise.promised_date = state.simulation_date - timedelta(days=1); promise.status = PromiseStatus.BROKEN; case = _case_for(db, promise.invoice, when)
        _audit(db, "PromiseToPay", promise.id, "SIMULATION_PROMISE_BROKEN", {"previous_promised_date": str(previous_date), "promised_date": str(promise.promised_date)}, when)
        events.append(_record(db, state, ordinal, "PROMISE_BROKEN", customer=promise.customer, invoice=promise.invoice, case=case, metadata={"promise_id": str(promise.id), "previous_promised_date": str(previous_date), "promised_date": str(promise.promised_date)}))
    elif scenario == 3 and open_invoices:
        invoice = open_invoices[-1]; case = _case_for(db, invoice, when)
        message = _communication(db, state, invoice.customer, invoice, "We can make a partial transfer next Tuesday; please allow for cash-flow timing.", ordinal)
        promise = PromiseToPay(customer=invoice.customer, invoice=invoice, promised_amount=(invoice.outstanding_amount * Decimal("0.40")).quantize(Decimal("0.01")), promised_date=state.simulation_date + timedelta(days=5), status=PromiseStatus.ACTIVE, source_communication=message, confidence=Decimal("0.6200"))
        db.add(promise); db.flush(); _audit(db, "PromiseToPay", promise.id, "SIMULATION_PROMISE_CREATED", {"invoice_id": str(invoice.id)}, when)
        events.append(_record(db, state, ordinal, "PAYMENT_COMMITMENT_RECEIVED", invoice=invoice, case=case, metadata={"communication_id": str(message.id), "promise_amount": str(promise.promised_amount), "promised_date": str(promise.promised_date)}))
    elif scenario == 4 and open_invoices:
        invoice = open_invoices[cycle % len(open_invoices)]; previous = invoice.status; invoice.status = InvoiceStatus.DISPUTED; case = _case_for(db, invoice, when)
        message = _communication(db, state, invoice.customer, invoice, f"We dispute invoice {invoice.invoice_number} due to a delivery issue; please hold collection.", ordinal)
        _audit(db, "Invoice", invoice.id, "SIMULATION_DISPUTE_OPENED", {"previous_status": previous.value}, when)
        events.append(_record(db, state, ordinal, "DISPUTE_OPENED", invoice=invoice, case=case, metadata={"previous_status": previous.value, "communication_id": str(message.id)}))
    elif scenario == 5:
        disputed = next((item for item in invoices if item.status is InvoiceStatus.DISPUTED), None)
        if disputed:
            disputed.status = InvoiceStatus.OVERDUE if disputed.due_date < state.simulation_date else InvoiceStatus.OPEN; case = _case_for(db, disputed, when)
            _audit(db, "Invoice", disputed.id, "SIMULATION_DISPUTE_RESOLVED", {"resulting_status": disputed.status.value}, when)
            events.append(_record(db, state, ordinal, "DISPUTE_RESOLVED", invoice=disputed, case=case, metadata={"resulting_status": disputed.status.value}))
    if not events and open_invoices:
        invoice = open_invoices[0]; case = _case_for(db, invoice, when)
        previous = invoice.status.value
        if invoice.status is not InvoiceStatus.DISPUTED:
            invoice.status = InvoiceStatus.OVERDUE
        _audit(db, "Invoice", invoice.id, "SIMULATION_INVOICE_BECAME_OVERDUE", {"previous_status": previous, "due_date": str(invoice.due_date)}, when)
        events.append(_record(db, state, ordinal, "INVOICE_BECAME_OVERDUE", invoice=invoice, case=case, metadata={"previous_status": previous, "resulting_status": invoice.status.value, "due_date": str(invoice.due_date), "simulation_date": str(state.simulation_date)}))
    db.flush()
    synchronization = synchronize_recovery_states(db, state.simulation_date)
    # synchronize commits; persist any event records and cycle as the final atomic outcome.
    db.commit()
    transitions = _build_transitions(db, before_intelligence, events, cycle)
    return {"cycle": cycle, "simulation_date": state.simulation_date, "event_count": len(events), "events": events, "intelligence_transitions": transitions, "recovery_synchronization": synchronization}


def reset_simulation(db: Session) -> dict[str, Any]:
    """Atomically restore the complete deterministic portfolio baseline."""
    db.scalar(select(SimulationState).where(SimulationState.name == "default").with_for_update())
    summary = seed_database(db, reset=True)
    # Confirmation plans contain record-specific recommendations from the old
    # operational world and must not survive a baseline replacement.
    from app.commands.service import PLAN_REGISTRY
    PLAN_REGISTRY.clear()
    return {"state": simulation_state(db), "summary": summary}


def simulation_state(db: Session) -> dict[str, Any]:
    state = db.scalar(select(SimulationState).where(SimulationState.name == "default"))
    if state is None: raise ValueError("Synthetic simulation state has not been seeded.")
    return {"name": state.name, "cycle": state.cycle, "simulation_date": state.simulation_date,
            "tick_interval_seconds": get_settings().simulation_tick_interval_seconds}


def recent_events(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.scalars(select(SimulationEvent).order_by(SimulationEvent.occurred_at.desc(), SimulationEvent.cycle.desc()).limit(limit)).all()
    return [{"id": str(item.id), "cycle": item.cycle, "type": item.event_type, "customer_id": str(item.customer_id) if item.customer_id else None, "invoice_id": str(item.invoice_id) if item.invoice_id else None, "case_id": str(item.recovery_case_id) if item.recovery_case_id else None, "metadata": item.metadata_, "occurred_at": item.occurred_at} for item in rows]
