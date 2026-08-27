"""Persisted simulation ticks that change facts before recovery is evaluated."""
from __future__ import annotations

import uuid
import random
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.timing import elapsed_ms, log_timing
from app.intelligence.service import persist_analysis
from app.intelligence.provider import MockCommunicationIntelligenceProvider
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
from app.simulation.config import SCENARIO_CONFIG


def _when(state: SimulationState) -> datetime:
    return datetime(state.simulation_date.year, state.simulation_date.month, state.simulation_date.day, 10, tzinfo=UTC)


def _event_id(cycle: int, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/{cycle}/{ordinal}")


def _audit(db: Session, entity_type: str, entity_id: uuid.UUID, event_type: str, payload: dict[str, Any], when: datetime) -> None:
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type, actor_type="simulation", payload=payload, occurred_at=when))


def _case_for(db: Session, invoice: Invoice, when: datetime) -> RecoveryCase:
    case = db.scalar(select(RecoveryCase).where(RecoveryCase.invoice_id == invoice.id, RecoveryCase.closed_at.is_(None)))
    if case is None:
        case = RecoveryCase(id=uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/case/{invoice.id}"), customer_id=invoice.customer_id, invoice=invoice, current_state=RecoveryState.NEW,
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
                            metadata_=metadata, occurred_at=_when(state) + timedelta(minutes=ordinal * 7))
    db.add(event)
    return {"id": str(event.id), "type": event_type, "customer_id": str(event.customer_id) if event.customer_id else None,
            "invoice_id": str(event.invoice_id) if event.invoice_id else None, "case_id": str(event.recovery_case_id) if event.recovery_case_id else None,
            "cycle": event.cycle, "occurred_at": event.occurred_at, "metadata": metadata}


def _communication(db: Session, state: SimulationState, customer: Customer, invoice: Invoice, content: str, ordinal: int) -> Communication:
    message = Communication(id=uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/communication/{state.cycle}/{ordinal}"), customer=customer,
                            direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.PORTAL, content=content, occurred_at=_when(state))
    db.add(message); db.flush()
    # Synthetic simulation remains deterministic and never incurs live-model latency or cost.
    analysis = persist_analysis(message, provider_override=MockCommunicationIntelligenceProvider())
    db.add(analysis)
    return message


@dataclass(frozen=True)
class _IntelligenceSnapshot:
    result: IntelligenceResult
    recommendation: str
    recommendation_title: str


def _capture_intelligence(db: Session) -> dict[tuple[str, str], _IntelligenceSnapshot]:
    """Capture an ephemeral comparison baseline; no intelligence history is persisted."""
    tools = CommandTools(db)
    snapshots: dict[tuple[str, str], _IntelligenceSnapshot] = {}
    for result in tools.get_portfolio_intelligence().customers:
        snapshots[("CUSTOMER", result.entity_id)] = _IntelligenceSnapshot(
            result, result.recommendation.action.value, result.recommendation.title,
        )
    for case in tools.cases():
        result = evaluate_case_intelligence(case, tools.simulation_date)
        recommendation = recommend_case(case, tools.simulation_date)
        snapshots[("RECOVERY_CASE", str(case.id))] = _IntelligenceSnapshot(
            result,
            recommendation.recommended_action.value,
            recommendation.recommended_action.value.replace("_", " ").title(),
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
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        for entity_type, entity_id in [("CUSTOMER", event.get("customer_id")), ("RECOVERY_CASE", event.get("case_id"))]:
            if not entity_id:
                continue
            grouped.setdefault((entity_type, entity_id), []).append(event)
    for (entity_type, entity_id), related_events in grouped.items():
        event = related_events[0]
        if entity_type == "CUSTOMER":
                result = tools.get_customer_intelligence(uuid.UUID(entity_id))
                current_recommendation = result.recommendation.action.value if result else None
                current_title = result.recommendation.title if result else None
                current_explanation = result.recommendation.explanation if result else None
                operator_next_step = None
                workflow_effect = None
        else:
                case = tools.get_case(entity_id)
                result = tools.get_case_intelligence(uuid.UUID(entity_id)) if case else None
                recommendation = recommend_case(case, tools.simulation_date) if case else None
                current_recommendation = recommendation.recommended_action.value if recommendation else None
                current_title = recommendation.recommended_action.value.replace("_", " ").title() if recommendation else None
                current_explanation = recommendation.operator_explanation if recommendation else None
                operator_next_step = recommendation.operator_next_step if recommendation else None
                workflow_effect = recommendation.workflow_effect if recommendation else None
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
                previous_recommendation_title=previous.recommendation_title if previous else None,
                current_recommendation_title=current_title,
                current_recommendation_explanation=current_explanation,
                operator_next_step=operator_next_step,
                workflow_effect=workflow_effect,
        )
        payload = transition.model_dump(mode="json")
        payload["related_events"] = [{"id": item["id"], "type": item["type"], "family": item["metadata"].get("family"), "role": item["metadata"].get("role")} for item in related_events]
        transitions.append(payload)
    return transitions


def _persist_transition_audits(
    db: Session,
    state: SimulationState,
    cycle: int,
    event_count: int,
    transitions: list[dict[str, Any]],
    summary: dict[str, int],
) -> None:
    """Append the already-computed Phase A decision changes for later inspection."""
    when = _when(state) + timedelta(minutes=55)
    db.add(AuditEvent(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/intelligence/{cycle}/summary"),
        entity_type="SimulationState", entity_id=state.id,
        event_type="SIMULATION_INTELLIGENCE_SUMMARY", actor_type="simulation",
        payload={"cycle": cycle, "event_count": event_count, **summary}, occurred_at=when,
    ))
    for ordinal, transition in enumerate(transitions, start=1):
        entity_id = uuid.UUID(transition["entity_id"])
        db.add(AuditEvent(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/intelligence/{cycle}/{transition['entity_type']}/{entity_id}"),
            entity_type=transition["entity_type"], entity_id=entity_id,
            event_type="SIMULATION_INTELLIGENCE_TRANSITION", actor_type="simulation",
            payload={"cycle": cycle, **transition}, occurred_at=when + timedelta(seconds=ordinal),
        ))
    db.commit()


_EVENT_FAMILY = {
    "PARTIAL_PAYMENT": "PAYMENT", "FULL_PAYMENT": "PAYMENT",
    "PROMISE_CREATED": "PROMISE", "PROMISE_BROKEN": "PROMISE",
    "DISPUTE_OPENED": "DISPUTE", "DISPUTE_RESOLVED": "DISPUTE",
    "CUSTOMER_DELAY_RESPONSE": "COMMUNICATION",
}


def _roll_event_plan(rng: random.Random, valid_primary: list[str]) -> tuple[str, int]:
    """Return the reproducible initial roll; state checks still govern each applied secondary."""
    weighted = [kind for kind in SCENARIO_CONFIG.primary_event_population if kind in valid_primary]
    if not weighted:
        raise ValueError("No financially valid primary simulation event is currently available.")
    return rng.choice(weighted), rng.choice(SCENARIO_CONFIG.secondary_count_population)


def _fractional_amount(balance: Decimal, rng: random.Random, minimum: float, maximum: float) -> Decimal:
    fraction = Decimal(str(rng.uniform(minimum, maximum)))
    amount = max(Decimal("0.01"), (balance * fraction).quantize(Decimal("0.01")))
    return min(amount, balance)


def _promise_date(simulation_date, rng: random.Random):
    return simulation_date + timedelta(days=rng.randint(SCENARIO_CONFIG.promise_days_min, SCENARIO_CONFIG.promise_days_max))


def _pick(rng: random.Random, candidates: list[Any], preferred_customer_id: uuid.UUID | None = None):
    if preferred_customer_id is not None and rng.random() < SCENARIO_CONFIG.same_account_probability:
        related = [item for item in candidates if getattr(item, "customer_id", None) == preferred_customer_id]
        if related:
            candidates = related
    return rng.choice(candidates)


def _available_event_kinds(invoices: list[Invoice], promises: list[PromiseToPay], used: set[tuple[str, str]]) -> list[str]:
    payable = [item for item in invoices if item.outstanding_amount > 0 and item.status is not InvoiceStatus.DISPUTED]
    disputed = [item for item in invoices if item.outstanding_amount > 0 and item.status is InvoiceStatus.DISPUTED]
    active = [item for item in promises if item.status is PromiseStatus.ACTIVE and item.invoice is not None and item.invoice.outstanding_amount > 0]
    without_active_promise = [item for item in payable if not any(p.status is PromiseStatus.ACTIVE for p in item.promises_to_pay)]
    kinds = []
    if any(("PARTIAL_PAYMENT", str(item.id)) not in used and item.outstanding_amount > Decimal("0.01") for item in payable): kinds.append("PARTIAL_PAYMENT")
    if any(("FULL_PAYMENT", str(item.id)) not in used for item in payable): kinds.append("FULL_PAYMENT")
    if any(("PROMISE_CREATED", str(item.id)) not in used for item in without_active_promise): kinds.append("PROMISE_CREATED")
    if any(("PROMISE_BROKEN", str(item.id)) not in used for item in active): kinds.append("PROMISE_BROKEN")
    if any(("DISPUTE_OPENED", str(item.id)) not in used for item in payable): kinds.append("DISPUTE_OPENED")
    if any(("DISPUTE_RESOLVED", str(item.id)) not in used for item in disputed): kinds.append("DISPUTE_RESOLVED")
    if any(("CUSTOMER_DELAY_RESPONSE", str(item.id)) not in used for item in payable): kinds.append("CUSTOMER_DELAY_RESPONSE")
    return kinds


def _apply_generated_event(db: Session, state: SimulationState, rng: random.Random, seed: int, kind: str, role: str, ordinal: int, invoices: list[Invoice], promises: list[PromiseToPay], used: set[tuple[str, str]], preferred_customer_id: uuid.UUID | None) -> dict[str, Any]:
    payable = [item for item in invoices if item.outstanding_amount > 0 and item.status is not InvoiceStatus.DISPUTED and (kind, str(item.id)) not in used]
    disputed = [item for item in invoices if item.outstanding_amount > 0 and item.status is InvoiceStatus.DISPUTED and (kind, str(item.id)) not in used]
    when = _when(state)
    metadata: dict[str, Any] = {"family": _EVENT_FAMILY[kind], "role": role, "seed": seed}
    invoice: Invoice
    event_type: str

    if kind in {"PARTIAL_PAYMENT", "FULL_PAYMENT"}:
        invoice = _pick(rng, payable, preferred_customer_id)
        previous = invoice.outstanding_amount
        if kind == "FULL_PAYMENT": amount = previous
        else:
            amount = _fractional_amount(previous, rng, SCENARIO_CONFIG.payment_fraction_min, SCENARIO_CONFIG.payment_fraction_max)
            if amount >= previous: amount = max(Decimal("0.01"), previous - Decimal("0.01"))
        invoice.outstanding_amount -= amount
        invoice.status = InvoiceStatus.PAID if invoice.outstanding_amount == 0 else InvoiceStatus.PARTIALLY_PAID
        db.add(Payment(invoice=invoice, amount=amount, payment_date=state.simulation_date, reference=f"SIM-{state.cycle:04d}-{ordinal}"))
        for promise in invoice.promises_to_pay:
            if promise.status is PromiseStatus.ACTIVE and amount >= promise.promised_amount: promise.status = PromiseStatus.FULFILLED
        event_type = "FULL_PAYMENT_RECEIVED" if invoice.outstanding_amount == 0 else "PARTIAL_PAYMENT_RECEIVED"
        metadata.update(previous_outstanding=str(previous), payment_amount=str(amount), resulting_outstanding=str(invoice.outstanding_amount))
        _audit(db, "Invoice", invoice.id, "SIMULATION_PAYMENT_RECEIVED", metadata, when)
    elif kind == "PROMISE_CREATED":
        candidates = [item for item in payable if not any(p.status is PromiseStatus.ACTIVE for p in item.promises_to_pay)]
        invoice = _pick(rng, candidates, preferred_customer_id)
        amount = _fractional_amount(invoice.outstanding_amount, rng, SCENARIO_CONFIG.promise_fraction_min, SCENARIO_CONFIG.promise_fraction_max)
        promised_date = _promise_date(state.simulation_date, rng)
        message = _communication(db, state, invoice.customer, invoice, f"We expect to pay INR {amount} by {promised_date}; please note the revised cash-flow timing.", ordinal)
        promise = PromiseToPay(id=uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.simulation/promise/{state.cycle}/{ordinal}"), customer=invoice.customer, invoice=invoice, promised_amount=amount, promised_date=promised_date, status=PromiseStatus.ACTIVE, source_communication=message, confidence=Decimal("0.7600"))
        db.add(promise); db.flush(); promises.append(promise)
        event_type = "PAYMENT_COMMITMENT_RECEIVED"
        metadata.update(communication_id=str(message.id), promise_id=str(promise.id), promise_amount=str(amount), promised_date=str(promised_date))
        _audit(db, "PromiseToPay", promise.id, "SIMULATION_PROMISE_CREATED", metadata, when)
        used.add(("PROMISE_BROKEN", str(promise.id)))
    elif kind == "PROMISE_BROKEN":
        active = [item for item in promises if item.status is PromiseStatus.ACTIVE and item.invoice is not None and item.invoice.outstanding_amount > 0 and (kind, str(item.id)) not in used]
        promise = _pick(rng, active, preferred_customer_id)
        invoice = promise.invoice
        previous_date = promise.promised_date; promise.promised_date = state.simulation_date - timedelta(days=1); promise.status = PromiseStatus.BROKEN
        event_type = "PROMISE_BROKEN"
        metadata.update(promise_id=str(promise.id), previous_promised_date=str(previous_date), promised_date=str(promise.promised_date))
        _audit(db, "PromiseToPay", promise.id, "SIMULATION_PROMISE_BROKEN", metadata, when)
        used.add((kind, str(promise.id)))
    elif kind == "DISPUTE_OPENED":
        invoice = _pick(rng, payable, preferred_customer_id); previous = invoice.status; invoice.status = InvoiceStatus.DISPUTED
        message = _communication(db, state, invoice.customer, invoice, f"We dispute invoice {invoice.invoice_number}; please hold recovery while the delivery discrepancy is reviewed.", ordinal)
        event_type = "DISPUTE_OPENED"; metadata.update(previous_status=previous.value, communication_id=str(message.id))
        _audit(db, "Invoice", invoice.id, "SIMULATION_DISPUTE_OPENED", metadata, when)
        used.add(("DISPUTE_RESOLVED", str(invoice.id)))
    elif kind == "DISPUTE_RESOLVED":
        invoice = _pick(rng, disputed, preferred_customer_id); invoice.status = InvoiceStatus.OVERDUE if invoice.due_date < state.simulation_date else InvoiceStatus.OPEN
        event_type = "DISPUTE_RESOLVED"; metadata.update(resulting_status=invoice.status.value)
        _audit(db, "Invoice", invoice.id, "SIMULATION_DISPUTE_RESOLVED", metadata, when)
        used.add(("DISPUTE_OPENED", str(invoice.id)))
    else:
        invoice = _pick(rng, payable, preferred_customer_id)
        message = _communication(db, state, invoice.customer, invoice, "Payment is delayed while we complete an internal cash-flow review; we will provide a confirmed date when available.", ordinal)
        event_type = "CUSTOMER_DELAY_REASON_RECEIVED"; metadata.update(communication_id=str(message.id), signal="PAYMENT_DELAY")
        _audit(db, "Communication", message.id, "SIMULATION_CUSTOMER_RESPONSE", metadata, when)

    used.add((kind, str(invoice.id)))
    case = _case_for(db, invoice, when)
    return _record(db, state, ordinal, event_type, invoice=invoice, case=case, metadata=metadata)


def run_tick(db: Session, *, seed: int | None = None, judge: bool = False) -> dict[str, Any]:
    started_at = perf_counter()
    stage_started = perf_counter()
    state = db.scalar(select(SimulationState).where(SimulationState.name == "default").with_for_update())
    state_lock_ms = elapsed_ms(stage_started)
    if state is None:
        raise ValueError("Synthetic simulation state has not been seeded.")
    stage_started = perf_counter()
    before_intelligence = _capture_intelligence(db)
    capture_before_intelligence_ms = elapsed_ms(stage_started)
    previous_cycle, previous_simulation_date = state.cycle, state.simulation_date
    selected_seed = SCENARIO_CONFIG.judge_seed if judge else seed if seed is not None else secrets.randbits(63)
    rng = random.Random(selected_seed)
    stage_started = perf_counter()
    state.cycle += 1
    state.simulation_date += timedelta(days=1)
    db.flush()
    advance_cycle_ms = elapsed_ms(stage_started)
    when, cycle, events = _when(state), state.cycle, []
    stage_started = perf_counter()
    invoices = db.scalars(select(Invoice).options(selectinload(Invoice.customer), selectinload(Invoice.payments), selectinload(Invoice.promises_to_pay)).order_by(Invoice.due_date, Invoice.id)).all()
    active_promises = db.scalars(select(PromiseToPay).options(selectinload(PromiseToPay.invoice), selectinload(PromiseToPay.customer)).where(PromiseToPay.status == PromiseStatus.ACTIVE).order_by(PromiseToPay.promised_date)).all()
    load_operational_facts_ms = elapsed_ms(stage_started)
    # Business time, not wall-clock time, determines when an operational invoice
    # crosses into overdue status. Disputed and settled documents retain their facts.
    stage_started = perf_counter()
    for invoice in invoices:
        if invoice.outstanding_amount > 0 and invoice.due_date < state.simulation_date and invoice.status in {InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID}:
            previous = invoice.status.value
            invoice.status = InvoiceStatus.OVERDUE
            _audit(db, "Invoice", invoice.id, "SIMULATION_INVOICE_BECAME_OVERDUE", {"previous_status": previous, "due_date": str(invoice.due_date)}, when)
    apply_overdue_rules_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    used: set[tuple[str, str]] = set()
    valid = _available_event_kinds(invoices, active_promises, used)
    primary_kind, secondary_target = _roll_event_plan(rng, valid)
    primary = _apply_generated_event(db, state, rng, selected_seed, primary_kind, "PRIMARY", 0, invoices, active_promises, used, None)
    events.append(primary)
    preferred_customer_id = uuid.UUID(primary["customer_id"]) if primary.get("customer_id") else None
    for ordinal in range(1, secondary_target + 1):
        valid = _available_event_kinds(invoices, active_promises, used)
        if not valid: break
        kind = rng.choice(valid)
        events.append(_apply_generated_event(db, state, rng, selected_seed, kind, "SECONDARY", ordinal, invoices, active_promises, used, preferred_customer_id))
    generate_events_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    db.flush()
    persist_generated_facts_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    synchronization = synchronize_recovery_states(db, state.simulation_date, commit=False)
    recovery_synchronization_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    transitions = _build_transitions(db, before_intelligence, events, cycle)
    build_transitions_ms = elapsed_ms(stage_started)
    customer_transitions = [item for item in transitions if item["entity_type"] == "CUSTOMER"]
    families = sorted({item["metadata"]["family"] for item in events})
    summary = {"customers_affected": len({item["customer_id"] for item in events if item.get("customer_id")}), "material_customers": sum(bool(item["material"]) for item in customer_transitions), "recommendations_changed": sum("RECOMMENDATION_CHANGED" in item["classifications"] for item in customer_transitions), "recommendations_unchanged": sum("RECOMMENDATION_CHANGED" not in item["classifications"] for item in customer_transitions), "blockers_added": sum("NEW_BLOCKER" in item["classifications"] for item in customer_transitions), "blockers_removed": sum("BLOCKER_RESOLVED" in item["classifications"] for item in customer_transitions)}
    stage_started = perf_counter()
    _persist_transition_audits(db, state, cycle, len(events), transitions, summary)
    persist_transition_audits_ms = elapsed_ms(stage_started)
    log_timing(
        "simulation_tick_timing",
        cycle=cycle,
        total_ms=elapsed_ms(started_at),
        state_lock_ms=state_lock_ms,
        capture_before_intelligence_ms=capture_before_intelligence_ms,
        advance_cycle_ms=advance_cycle_ms,
        load_operational_facts_ms=load_operational_facts_ms,
        apply_overdue_rules_ms=apply_overdue_rules_ms,
        generate_events_ms=generate_events_ms,
        persist_generated_facts_ms=persist_generated_facts_ms,
        recovery_synchronization_ms=recovery_synchronization_ms,
        build_transitions_ms=build_transitions_ms,
        persist_transition_audits_ms=persist_transition_audits_ms,
        invoices_loaded=len(invoices),
        active_promises_loaded=len(active_promises),
        events_generated=len(events),
        transitions_built=len(transitions),
    )
    return {"previous_cycle": previous_cycle, "previous_simulation_date": previous_simulation_date, "cycle": cycle, "simulation_date": state.simulation_date, "event_count": len(events), "events": events, "intelligence_transitions": transitions, "recovery_synchronization": synchronization, "generation": {"seed": selected_seed, "mode": "JUDGE" if judge else "NORMAL", "primary_event_id": primary["id"], "secondary_event_count": len(events) - 1, "families": families}, "change_summary": summary}


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


def latest_intelligence_cycle(db: Session) -> dict[str, Any] | None:
    """Expose the latest persisted before/after evidence without recalculating it."""
    latest_cycle = db.scalar(select(SimulationEvent.cycle).order_by(SimulationEvent.cycle.desc()).limit(1))
    if latest_cycle is None:
        return None
    events = db.scalars(select(SimulationEvent).where(SimulationEvent.cycle == latest_cycle)).all()
    audits = db.scalars(select(AuditEvent).where(
        AuditEvent.event_type.in_({"SIMULATION_INTELLIGENCE_SUMMARY", "SIMULATION_INTELLIGENCE_TRANSITION"})
    ).order_by(AuditEvent.occurred_at)).all()
    relevant = [item for item in audits if (item.payload or {}).get("cycle") == latest_cycle]
    summary = next(((item.payload or {}) for item in relevant if item.event_type == "SIMULATION_INTELLIGENCE_SUMMARY"), {})
    transitions = [(item.payload or {}) for item in relevant if item.event_type == "SIMULATION_INTELLIGENCE_TRANSITION"]
    return {
        "cycle": latest_cycle,
        "event_count": len(events),
        "customers_affected": int(summary.get("customers_affected", len({event.customer_id for event in events if event.customer_id}))),
        "material_customers": int(summary.get("material_customers", 0)),
        "recommendations_changed": int(summary.get("recommendations_changed", 0)),
        "recommendations_unchanged": int(summary.get("recommendations_unchanged", 0)),
        "blockers_added": int(summary.get("blockers_added", 0)),
        "blockers_removed": int(summary.get("blockers_removed", 0)),
        "transitions": transitions,
    }
