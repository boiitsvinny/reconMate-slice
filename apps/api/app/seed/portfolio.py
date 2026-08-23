"""Build a reproducible B2B receivables portfolio with coherent histories."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.domain import (
    ApprovalStatus,
    AuditEvent,
    Communication,
    CommunicationChannel,
    CommunicationDirection,
    Customer,
    Invoice,
    InvoiceStatus,
    Payment,
    PromiseStatus,
    PromiseToPay,
    RecoveryAction,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCase,
    RecoveryPriority,
    RecoveryState,
    SimulationState,
)

SIMULATION_DATE = date(2026, 8, 1)
SEED = 20260801
INVOICES_PER_CUSTOMER = 7  # Core archetypes retain their established seven-document history.


@dataclass(frozen=True)
class CustomerBlueprint:
    name: str
    archetype: str
    strategic: bool = False


BLUEPRINTS = [
    CustomerBlueprint("Apex Industrial Supplies", "HEALTHY_RELIABLE"),
    CustomerBlueprint("Northstar Components", "HEALTHY_RELIABLE"),
    CustomerBlueprint("Clearline Packaging", "HEALTHY_RELIABLE"),
    CustomerBlueprint("Harbor Logistics Services", "RELIABLE_LATE"),
    CustomerBlueprint("Meridian Office Systems", "RELIABLE_LATE"),
    CustomerBlueprint("Pioneer Agro Trading", "RELIABLE_LATE"),
    CustomerBlueprint("Vertex Fabrication", "DETERIORATING"),
    CustomerBlueprint("Bluewave Distributors", "DETERIORATING"),
    CustomerBlueprint("Sterling Facilities", "DETERIORATING"),
    CustomerBlueprint("Crestview Retail Group", "PROMISE_BREAKER"),
    CustomerBlueprint("Orchid Electronics", "PROMISE_BREAKER"),
    CustomerBlueprint("Redwood Engineering", "PROMISE_BREAKER"),
    CustomerBlueprint("Atlas Wholesale", "PARTIAL_PAYER"),
    CustomerBlueprint("Beacon Medical Traders", "PARTIAL_PAYER"),
    CustomerBlueprint("Summit Food Services", "PARTIAL_PAYER"),
    CustomerBlueprint("Greenfield Construction", "DISPUTED_ACCOUNT"),
    CustomerBlueprint("Cobalt Technologies", "DISPUTED_ACCOUNT"),
    CustomerBlueprint("Lakeside Hospitality", "DISPUTED_ACCOUNT"),
    CustomerBlueprint("Helios Manufacturing", "STRATEGIC_HIGH_VALUE", True),
    CustomerBlueprint("Prime Infrastructure Partners", "STRATEGIC_HIGH_VALUE", True),
    CustomerBlueprint("Vantage Telecom Networks", "STRATEGIC_HIGH_VALUE", True),
    CustomerBlueprint("Ironclad Mining Equipment", "SEVERELY_OVERDUE"),
    CustomerBlueprint("Frontier Auto Parts", "SEVERELY_OVERDUE"),
    CustomerBlueprint("Delta Commerce House", "SEVERELY_OVERDUE"),
] + [
    CustomerBlueprint(f"Expansion Account {index:02d}", ("HEALTHY_RELIABLE", "RELIABLE_LATE", "DETERIORATING", "PROMISE_BREAKER", "PARTIAL_PAYER", "SEVERELY_OVERDUE", "STRATEGIC_HIGH_VALUE")[index % 7], index % 7 == 6)
    for index in range(1, 33)
]


def _invoice_count(customer_index: int) -> int:
    """Keep the verified base history while expanding to a 296-invoice universe."""
    return INVOICES_PER_CUSTOMER if customer_index <= 24 else 4


def _id(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.synthetic/{label}")


def _at(value: date, hour: int = 10) -> datetime:
    return datetime(value.year, value.month, value.day, hour, tzinfo=UTC)


def _money(value: int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def reset_database(session: Session) -> None:
    """Remove only ReconMate domain records, in FK-safe order."""
    from app.models.domain import CommunicationAnalysis
    for model in (AuditEvent, RecoveryAction, RecoveryCase, PromiseToPay, Payment, CommunicationAnalysis, Communication, Invoice, Customer, SimulationState):
        session.execute(delete(model))
    session.flush()


def _invoice_balance(archetype: str, index: int, amount: Decimal) -> Decimal:
    if archetype == "HEALTHY_RELIABLE":
        return Decimal("0") if index < 6 else amount
    if archetype == "RELIABLE_LATE":
        return Decimal("0") if index < 5 else amount
    if archetype == "DETERIORATING":
        return Decimal("0") if index < 3 else amount * Decimal(index - 2) / Decimal(5)
    if archetype == "PROMISE_BREAKER":
        return Decimal("0") if index < 3 else amount
    if archetype == "PARTIAL_PAYER":
        return Decimal("0") if index < 3 else amount * Decimal("0.45")
    if archetype == "DISPUTED_ACCOUNT":
        return amount if index in (4, 5) else (Decimal("0") if index < 4 else amount * Decimal("0.25"))
    if archetype == "STRATEGIC_HIGH_VALUE":
        return Decimal("0") if index < 3 else amount * Decimal("0.70")
    return Decimal("0") if index < 2 else amount


def _due_date(index: int) -> date:
    # The newest document is still current; all earlier dates are well before the virtual date.
    return SIMULATION_DATE - timedelta(days=190 - index * 35)


def _invoice_status(archetype: str, index: int, due_date: date, outstanding: Decimal) -> InvoiceStatus:
    if archetype == "DISPUTED_ACCOUNT" and index in (4, 5):
        return InvoiceStatus.DISPUTED
    if outstanding == 0:
        return InvoiceStatus.PAID
    if due_date < SIMULATION_DATE:
        return InvoiceStatus.OVERDUE
    return InvoiceStatus.OPEN


def _add_payment(session: Session, invoice: Invoice, paid_amount: Decimal, payment_date: date, number: int) -> None:
    if paid_amount <= 0:
        return
    # Split selected large payments to demonstrate multiple remittance events.
    parts = (paid_amount / 2, paid_amount - (paid_amount / 2)) if paid_amount >= Decimal("100000") else (paid_amount,)
    for offset, amount in enumerate(parts):
        session.add(Payment(
            id=_id(f"payment/{invoice.id}/{number}/{offset}"),
            invoice=invoice,
            amount=amount.quantize(Decimal("0.01")),
            payment_date=min(payment_date + timedelta(days=offset), SIMULATION_DATE - timedelta(days=1)),
            reference=f"PAY-{number:04d}-{offset + 1}",
        ))


def _communication(session: Session, customer: Customer, label: str, when: date, direction: CommunicationDirection, content: str) -> Communication:
    message = Communication(
        id=_id(f"communication/{customer.id}/{label}"),
        customer=customer,
        direction=direction,
        channel=CommunicationChannel.EMAIL if direction is CommunicationDirection.OUTBOUND else CommunicationChannel.PORTAL,
        content=content,
        occurred_at=_at(when),
    )
    session.add(message)
    return message


def _add_case(session: Session, customer: Customer, invoice: Invoice, state: RecoveryState, priority: RecoveryPriority, reason: str, aggressive: bool = True) -> RecoveryCase:
    case = RecoveryCase(
        id=_id(f"case/{customer.id}/{invoice.id}"), customer=customer, invoice=invoice,
        current_state=state, priority=priority, opened_at=_at(min(invoice.due_date + timedelta(days=7), SIMULATION_DATE - timedelta(days=1))),
        updated_at=_at(SIMULATION_DATE - timedelta(days=2)),
    )
    session.add(case)
    session.add(RecoveryAction(
        id=_id(f"action/{case.id}/note"), recovery_case=case, action_type=RecoveryActionType.NOTE,
        status=RecoveryActionStatus.EXECUTED, approval_status=ApprovalStatus.NOT_REQUIRED,
        reason=reason, created_at=case.opened_at, executed_at=case.opened_at,
    ))
    if aggressive:
        session.add(RecoveryAction(
            id=_id(f"action/{case.id}/follow-up"), recovery_case=case, action_type=RecoveryActionType.FOLLOW_UP,
            status=RecoveryActionStatus.PENDING_APPROVAL if customer.is_strategic_account else RecoveryActionStatus.EXECUTED,
            approval_status=ApprovalStatus.PENDING if customer.is_strategic_account else ApprovalStatus.NOT_REQUIRED,
            reason="Outstanding balance remains unresolved as of the virtual date.",
            created_at=_at(SIMULATION_DATE - timedelta(days=1)),
            executed_at=None if customer.is_strategic_account else _at(SIMULATION_DATE - timedelta(days=1)),
        ))
    return case


def seed_database(session: Session, *, reset: bool = False) -> dict[str, int | Decimal]:
    """Persist the deterministic portfolio; require explicit reset when records exist."""
    if session.scalar(select(func.count(Customer.id))) and not reset:
        raise RuntimeError("Database already contains customers. Re-run with --reset to replace development seed data.")
    if reset:
        reset_database(session)

    rng = random.Random(SEED)
    invoices_by_customer: dict[uuid.UUID, list[Invoice]] = {}
    for customer_index, blueprint in enumerate(BLUEPRINTS, start=1):
        customer = Customer(
            id=_id(f"customer/{customer_index}"), name=blueprint.name,
            account_reference=f"RM-{customer_index:04d}", segment=blueprint.archetype,
            is_strategic_account=blueprint.strategic,
        )
        session.add(customer)
        invoices: list[Invoice] = []
        base = 25000 if not blueprint.strategic else 175000
        if blueprint.archetype == "SEVERELY_OVERDUE":
            base = 90000
        for invoice_index in range(_invoice_count(customer_index)):
            amount = _money(base + rng.randrange(0, max(1000, base // 2)))
            due = _due_date(invoice_index)
            outstanding = _invoice_balance(blueprint.archetype, invoice_index, amount).quantize(Decimal("0.01"))
            invoice = Invoice(
                id=_id(f"invoice/{customer_index}/{invoice_index}"), customer=customer,
                invoice_number=f"INV-{customer_index:03d}-{invoice_index + 1:02d}",
                issue_date=due - timedelta(days=30), due_date=due, original_amount=amount,
                outstanding_amount=outstanding,
                status=_invoice_status(blueprint.archetype, invoice_index, due, outstanding),
            )
            session.add(invoice)
            invoices.append(invoice)
            paid = amount - outstanding
            if paid:
                delay = -2 if blueprint.archetype == "HEALTHY_RELIABLE" else 12
                if blueprint.archetype == "DETERIORATING":
                    delay = invoice_index * 6
                _add_payment(session, invoice, paid, due + timedelta(days=delay), customer_index * 10 + invoice_index)
        invoices_by_customer[customer.id] = invoices

        _communication(session, customer, "reminder", SIMULATION_DATE - timedelta(days=35), CommunicationDirection.OUTBOUND,
                       "Please confirm the expected settlement date for the outstanding invoices on your account.")
        if blueprint.archetype == "HEALTHY_RELIABLE":
            source = _communication(session, customer, "confirmation", invoices[3].due_date - timedelta(days=6), CommunicationDirection.INBOUND,
                                    "Payment has been scheduled in the normal weekly run; please allow a couple of business days.")
            session.add(PromiseToPay(id=_id(f"promise/{customer.id}/fulfilled"), customer=customer, invoice=invoices[3],
                                     promised_amount=invoices[3].original_amount, promised_date=invoices[3].due_date - timedelta(days=3),
                                     status=PromiseStatus.FULFILLED, source_communication=source, confidence=Decimal("0.9400")))
        elif blueprint.archetype == "RELIABLE_LATE":
            _communication(session, customer, "late-pattern", SIMULATION_DATE - timedelta(days=10), CommunicationDirection.INBOUND,
                           "We settle after our month-end reconciliation. This has been processed and should reflect shortly.")
        elif blueprint.archetype == "DETERIORATING":
            _communication(session, customer, "cash-pressure", SIMULATION_DATE - timedelta(days=8), CommunicationDirection.INBOUND,
                           "Cash receipts are delayed this month. We are reviewing what can be released first.")
        elif blueprint.archetype == "PARTIAL_PAYER":
            source = _communication(session, customer, "partial-payment", SIMULATION_DATE - timedelta(days=6), CommunicationDirection.INBOUND,
                                    "We have processed part of the amount. The balance will be cleared next week.")
            session.add(PromiseToPay(id=_id(f"promise/{customer.id}/active"), customer=customer, invoice=invoices[-1],
                                     promised_amount=invoices[-1].outstanding_amount, promised_date=SIMULATION_DATE + timedelta(days=6),
                                     status=PromiseStatus.ACTIVE, source_communication=source, confidence=Decimal("0.7200")))
            _add_case(session, customer, invoices[-1], RecoveryState.PROMISE_MONITORING, RecoveryPriority.NORMAL, "Monitoring active partial-payment commitment.")
        elif blueprint.archetype == "PROMISE_BREAKER":
            old_source = _communication(session, customer, "broken-commitment", SIMULATION_DATE - timedelta(days=45), CommunicationDirection.INBOUND,
                                        "We will clear ₹2 lakh by Friday.")
            session.add(PromiseToPay(id=_id(f"promise/{customer.id}/broken"), customer=customer, invoice=invoices[-2],
                                     promised_amount=invoices[-2].outstanding_amount, promised_date=SIMULATION_DATE - timedelta(days=35),
                                     status=PromiseStatus.BROKEN, source_communication=old_source, confidence=Decimal("0.6800")))
            active_source = _communication(session, customer, "new-commitment", SIMULATION_DATE - timedelta(days=3), CommunicationDirection.INBOUND,
                                           "The earlier release did not happen. We can make a partial transfer next Tuesday.")
            session.add(PromiseToPay(id=_id(f"promise/{customer.id}/active"), customer=customer, invoice=invoices[-1],
                                     promised_amount=(invoices[-1].outstanding_amount * Decimal("0.50")).quantize(Decimal("0.01")),
                                     promised_date=SIMULATION_DATE + timedelta(days=4), status=PromiseStatus.ACTIVE,
                                     source_communication=active_source, confidence=Decimal("0.4500")))
            _add_case(session, customer, invoices[-1], RecoveryState.IN_PROGRESS, RecoveryPriority.HIGH, "Prior payment commitment was missed.")
        elif blueprint.archetype == "DISPUTED_ACCOUNT":
            source = _communication(session, customer, "dispute", SIMULATION_DATE - timedelta(days=15), CommunicationDirection.INBOUND,
                                    f"There seems to be an issue with invoice {invoices[4].invoice_number}. Please hold off on further follow-ups while quantities are checked.")
            _add_case(session, customer, invoices[4], RecoveryState.AWAITING_CUSTOMER, RecoveryPriority.NORMAL, "Invoice dispute received; collection activity is on hold.", aggressive=False)
        elif blueprint.archetype == "STRATEGIC_HIGH_VALUE":
            source = _communication(session, customer, "strategic-commitment", SIMULATION_DATE - timedelta(days=4), CommunicationDirection.INBOUND,
                                    "We are aligning the release with the project milestone. Please give us until the middle of next week.")
            session.add(PromiseToPay(id=_id(f"promise/{customer.id}/active"), customer=customer, invoice=invoices[-1],
                                     promised_amount=(invoices[-1].outstanding_amount * Decimal("0.60")).quantize(Decimal("0.01")),
                                     promised_date=SIMULATION_DATE + timedelta(days=10), status=PromiseStatus.ACTIVE,
                                     source_communication=source, confidence=Decimal("0.6100")))
            _add_case(session, customer, invoices[-1], RecoveryState.PROMISE_MONITORING, RecoveryPriority.HIGH, "Strategic-account commitment awaiting approval-led follow-up.")
        elif blueprint.archetype == "SEVERELY_OVERDUE":
            source = _communication(session, customer, "broken-commitment", SIMULATION_DATE - timedelta(days=50), CommunicationDirection.INBOUND,
                                    "We cannot clear everything immediately. We expected funding last week but it has not arrived.")
            session.add(PromiseToPay(id=_id(f"promise/{customer.id}/broken"), customer=customer, invoice=invoices[-2],
                                     promised_amount=invoices[-2].outstanding_amount, promised_date=SIMULATION_DATE - timedelta(days=30),
                                     status=PromiseStatus.BROKEN, source_communication=source, confidence=Decimal("0.3500")))
            _add_case(session, customer, invoices[-1], RecoveryState.ESCALATED, RecoveryPriority.CRITICAL, "Multiple large invoices are severely overdue and commitment was broken.")

    session.add(SimulationState(id=_id("simulation/default"), name="default", simulation_date=SIMULATION_DATE))
    session.flush()
    for customer_id, invoices in invoices_by_customer.items():
        outstanding = sum((invoice.outstanding_amount for invoice in invoices), Decimal("0"))
        if outstanding:
            session.add(AuditEvent(id=_id(f"audit/{customer_id}"), entity_type="Customer", entity_id=customer_id,
                                   event_type="SYNTHETIC_PORTFOLIO_SEEDED", actor_type="system",
                                   payload={"outstanding_amount": str(outstanding), "simulation_date": str(SIMULATION_DATE)}, occurred_at=_at(SIMULATION_DATE)))
    session.flush()
    validate_portfolio(session)
    session.commit()
    return portfolio_summary(session)


def validate_portfolio(session: Session) -> None:
    """Assert the seed world's important cross-record accounting and timeline invariants."""
    customers = session.scalar(select(func.count(Customer.id))) or 0
    invoices = session.scalars(select(Invoice)).all()
    assert customers == len(BLUEPRINTS), "unexpected synthetic customer count"
    assert len(invoices) == sum(_invoice_count(index) for index in range(1, len(BLUEPRINTS) + 1)), "unexpected synthetic invoice count"
    for invoice in invoices:
        paid = sum((payment.amount for payment in invoice.payments), Decimal("0"))
        assert Decimal("0") <= invoice.outstanding_amount <= invoice.original_amount
        assert paid == invoice.original_amount - invoice.outstanding_amount, f"balance mismatch for {invoice.invoice_number}"
        assert not (invoice.status is InvoiceStatus.PAID and invoice.outstanding_amount > 0)
    for promise in session.scalars(select(PromiseToPay)):
        if promise.status is PromiseStatus.ACTIVE:
            assert promise.promised_date >= SIMULATION_DATE
        if promise.status is PromiseStatus.BROKEN:
            assert promise.promised_date < SIMULATION_DATE
        if promise.status is PromiseStatus.FULFILLED:
            assert promise.invoice is not None
            assert sum((payment.amount for payment in promise.invoice.payments), Decimal("0")) >= promise.promised_amount
    disputed_cases = session.scalars(select(RecoveryCase).join(Invoice).where(Invoice.status == InvoiceStatus.DISPUTED)).all()
    assert disputed_cases, "the synthetic portfolio must include disputed recovery cases"
    for case in disputed_cases:
        assert case.current_state is RecoveryState.AWAITING_CUSTOMER
        assert all(action.action_type is RecoveryActionType.NOTE for action in case.actions)
    assert session.scalar(select(func.count(PromiseToPay.id)).where(PromiseToPay.status == PromiseStatus.BROKEN)) > 0


def portfolio_summary(session: Session) -> dict[str, int | Decimal]:
    invoices = session.scalars(select(Invoice)).all()
    return {
        "customers": session.scalar(select(func.count(Customer.id))) or 0,
        "invoices": len(invoices),
        "open_invoices": sum(invoice.outstanding_amount > 0 for invoice in invoices),
        "overdue_invoices": sum(invoice.status is InvoiceStatus.OVERDUE for invoice in invoices),
        "outstanding_amount": sum((invoice.outstanding_amount for invoice in invoices), Decimal("0")),
        "overdue_amount": sum((invoice.outstanding_amount for invoice in invoices if invoice.status is InvoiceStatus.OVERDUE), Decimal("0")),
        "payments": session.scalar(select(func.count(Payment.id))) or 0,
        "promises": session.scalar(select(func.count(PromiseToPay.id))) or 0,
        "broken_promises": session.scalar(select(func.count(PromiseToPay.id)).where(PromiseToPay.status == PromiseStatus.BROKEN)) or 0,
        "active_disputes": sum(invoice.status is InvoiceStatus.DISPUTED for invoice in invoices),
        "recovery_cases": session.scalar(select(func.count(RecoveryCase.id))) or 0,
    }
