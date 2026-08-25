"""Build the deterministic ReconMate demo portfolio from varied B2B archetypes."""

from __future__ import annotations

import random
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.domain import (
    ApprovalStatus, AuditEvent, Communication, CommunicationChannel,
    CommunicationDirection, Customer, Invoice, InvoiceStatus, Payment,
    PromiseStatus, PromiseToPay, RecoveryAction, RecoveryActionStatus,
    RecoveryActionType, RecoveryCase, RecoveryPriority, RecoveryState,
    SimulationEvent, SimulationState,
)

SIMULATION_DATE = date(2026, 8, 1)
SEED = 20260801


@dataclass(frozen=True)
class ArchetypeSpec:
    invoice_range: tuple[int, int]
    open_range: tuple[int, int]
    amount_range: tuple[int, int]
    overdue_range: tuple[int, int]
    balance_range: tuple[int, int] = (100, 100)
    dispute_count: int = 0
    active_promises: int = 0
    broken_promises: int = 0
    fulfilled_promises: int = 0
    recent_partial_payment: bool = False
    case_state: RecoveryState | None = None
    case_priority: RecoveryPriority = RecoveryPriority.NORMAL
    stale_case: bool = False


@dataclass(frozen=True)
class CustomerBlueprint:
    name: str
    archetype: str
    industry: str
    strategic: bool = False


ARCHETYPES: dict[str, ArchetypeSpec] = {
    "HEALTHY_LOW_RISK": ArchetypeSpec((2, 6), (0, 1), (18000, 115000), (-18, 7), (70, 100), fulfilled_promises=1),
    "TEMPORARILY_LATE": ArchetypeSpec((3, 7), (1, 2), (32000, 165000), (4, 28), (75, 100), active_promises=1, recent_partial_payment=True, case_state=RecoveryState.PROMISE_MONITORING),
    "CHRONIC_LATE": ArchetypeSpec((5, 9), (2, 4), (28000, 135000), (42, 115), broken_promises=1, case_state=RecoveryState.IN_PROGRESS, case_priority=RecoveryPriority.HIGH, stale_case=True),
    "ACTIVE_PROMISE": ArchetypeSpec((2, 6), (1, 3), (45000, 225000), (12, 62), (80, 100), active_promises=1, case_state=RecoveryState.PROMISE_MONITORING),
    "DISPUTE_BLOCKED": ArchetypeSpec((3, 7), (2, 3), (65000, 220000), (31, 105), dispute_count=1, case_state=RecoveryState.AWAITING_CUSTOMER),
    "BROKEN_PROMISE": ArchetypeSpec((3, 7), (1, 3), (40000, 170000), (35, 100), broken_promises=2, case_state=RecoveryState.ESCALATED, case_priority=RecoveryPriority.HIGH, stale_case=True),
    "PARTIAL_PAYMENT": ArchetypeSpec((3, 8), (2, 4), (38000, 245000), (18, 88), (25, 68), recent_partial_payment=True, case_state=RecoveryState.IN_PROGRESS),
    "STRATEGIC_HIGH_VALUE": ArchetypeSpec((4, 8), (2, 4), (210000, 780000), (22, 76), (65, 100), active_promises=1, case_state=RecoveryState.PROMISE_MONITORING, case_priority=RecoveryPriority.HIGH),
    "MIXED_STATE": ArchetypeSpec((6, 10), (3, 6), (65000, 330000), (27, 105), (35, 100), dispute_count=1, active_promises=1, broken_promises=1, recent_partial_payment=True, case_state=RecoveryState.AWAITING_CUSTOMER, case_priority=RecoveryPriority.HIGH),
    "RECOVERING": ArchetypeSpec((4, 8), (2, 4), (75000, 310000), (38, 102), (18, 52), fulfilled_promises=1, recent_partial_payment=True, case_state=RecoveryState.IN_PROGRESS, case_priority=RecoveryPriority.HIGH),
    "DETERIORATING": ArchetypeSpec((3, 7), (2, 4), (55000, 260000), (21, 79), (80, 100), broken_promises=1, case_state=RecoveryState.IN_PROGRESS, case_priority=RecoveryPriority.HIGH),
    "LOW_VALUE_BEHAVIOR_RISK": ArchetypeSpec((3, 6), (1, 3), (12000, 52000), (29, 83), broken_promises=2, case_state=RecoveryState.ESCALATED, case_priority=RecoveryPriority.HIGH, stale_case=True),
    "STALE_NO_RESPONSE": ArchetypeSpec((4, 8), (2, 5), (42000, 180000), (76, 146), case_state=RecoveryState.ESCALATED, case_priority=RecoveryPriority.CRITICAL, stale_case=True),
    "DISPUTE_RESOLVED": ArchetypeSpec((4, 7), (2, 3), (65000, 240000), (39, 97), case_state=RecoveryState.IN_PROGRESS, case_priority=RecoveryPriority.HIGH),
    "HIGH_VALUE_LOW_URGENCY": ArchetypeSpec((3, 5), (1, 2), (420000, 920000), (5, 13), (85, 100), active_promises=1, case_state=RecoveryState.PROMISE_MONITORING, case_priority=RecoveryPriority.HIGH),
    "CLOSED_RESOLVED": ArchetypeSpec((2, 5), (0, 0), (30000, 185000), (0, 0), fulfilled_promises=1, case_state=RecoveryState.CLOSED, case_priority=RecoveryPriority.LOW),
}


def _group(archetype: str, names: tuple[str, ...], industries: tuple[str, ...], *, strategic: bool = False) -> list[CustomerBlueprint]:
    return [CustomerBlueprint(name, archetype, industries[index % len(industries)], strategic) for index, name in enumerate(names)]


BLUEPRINTS = [
    *_group("HEALTHY_LOW_RISK", (
        "Apex Industrial Supplies", "Northstar Components", "Clearline Packaging", "Meridian Learning Systems",
        "Willowbrook Health Traders", "Sunward Office Products", "Copperleaf Media Works", "Bluehaven Retail Services",
        "Oakline Food Distribution", "Verity Cloud Solutions", "Harborview Hospitality", "Cedarstone Equipment",
        "Lumen Educational Resources", "Silverfern Wholesale", "Marigold Facility Services", "Kestrel Print Studios",
    ), ("Manufacturing", "Distribution", "Education", "Healthcare", "SaaS", "Hospitality")),
    *_group("TEMPORARILY_LATE", (
        "Harbor Logistics Services", "Pioneer Agro Trading", "Nimblegrid Software", "Crescent Medical Supply",
        "Westbridge Campus Services", "Amberlane Retail Network", "Trident Cold Chain", "Brightpath Business Media", "Mosaic Hotel Products",
    ), ("Logistics", "Agriculture", "SaaS", "Healthcare", "Education", "Retail")),
    *_group("CHRONIC_LATE", (
        "Ironclad Mining Equipment", "Frontier Auto Parts", "Redwood Engineering", "Stonegate Civil Works",
        "Metroline Trade Depot", "Evercrest Furnishings", "Granitefield Processors", "Orchard Route Distributors",
    ), ("Heavy equipment", "Automotive", "Engineering", "Infrastructure", "Wholesale")),
    *_group("ACTIVE_PROMISE", (
        "Beacon Medical Traders", "Summit Food Services", "Violetpeak Technologies", "Rainier School Supplies",
        "Coralbay Hospitality Goods", "Windward Textile House", "Orbitline Enterprise Services",
    ), ("Healthcare", "Food services", "SaaS", "Education", "Hospitality", "Textiles")),
    *_group("DISPUTE_BLOCKED", (
        "Greenfield Construction", "Cobalt Technologies", "Lakeside Hospitality", "Emberworks Manufacturing",
        "Parklane Retail Fixtures", "Riverbend Clinical Systems",
    ), ("Construction", "Technology", "Hospitality", "Manufacturing", "Retail", "Healthcare")),
    *_group("BROKEN_PROMISE", (
        "Crestview Retail Group", "Orchid Electronics", "Delta Commerce House", "Foxglove Distribution",
        "Keystone Fleet Services", "Bellwether Learning Labs",
    ), ("Retail", "Electronics", "Wholesale", "Distribution", "Logistics", "Education")),
    *_group("PARTIAL_PAYMENT", (
        "Atlas Wholesale", "Bluewave Distributors", "Sterling Facilities", "Quarryside Tools",
        "Solstice Event Services", "Meadowlink Pharmacy Supply",
    ), ("Wholesale", "Distribution", "Facilities", "Manufacturing", "Events", "Healthcare")),
    *_group("STRATEGIC_HIGH_VALUE", (
        "Helios Manufacturing", "Prime Infrastructure Partners", "Vantage Telecom Networks", "Aurelian Data Systems", "Monarch Transit Engineering",
    ), ("Manufacturing", "Infrastructure", "Telecommunications", "Enterprise technology", "Transport"), strategic=True),
    *_group("MIXED_STATE", (
        "Vertex Fabrication", "Juniper Commerce Network", "Saffron Healthcare Group", "Tidalwave Logistics", "Foundrylane Enterprise Services",
    ), ("Fabrication", "Retail", "Healthcare", "Logistics", "Enterprise services")),
    *_group("RECOVERING", (
        "Horizon Building Materials", "Cloudspire Software", "Mapleline Distribution", "Aurora Hospitality Systems",
    ), ("Construction", "SaaS", "Distribution", "Hospitality")),
    *_group("DETERIORATING", (
        "Garnet Auto Systems", "Seabrook Media Network", "Cypress Medical Devices", "Ridgeway Consumer Goods",
    ), ("Automotive", "Media", "Healthcare", "Consumer goods")),
    *_group("LOW_VALUE_BEHAVIOR_RISK", ("Pebblecart Supplies", "Littlewing Studio Services", "Mintleaf Office Mart"), ("Retail", "Media", "Office supplies")),
    *_group("STALE_NO_RESPONSE", ("Blackridge Machinery", "Oldtown Regional Distributors"), ("Machinery", "Distribution")),
    *_group("DISPUTE_RESOLVED", ("Newbridge Safety Equipment",), ("Industrial safety",)),
    *_group("HIGH_VALUE_LOW_URGENCY", ("Polaris Infrastructure Advisory",), ("Infrastructure services",), strategic=True),
    *_group("CLOSED_RESOLVED", ("Elmshore Business Furnishings",), ("Commercial interiors",)),
]


def _invoice_count(customer_index: int) -> int:
    blueprint = BLUEPRINTS[customer_index - 1]
    low, high = ARCHETYPES[blueprint.archetype].invoice_range
    return random.Random(SEED + customer_index * 7919).randint(low, high)


def _id(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"reconmate.synthetic/{label}")


def _at(value: date, hour: int = 10) -> datetime:
    return datetime(value.year, value.month, value.day, hour, tzinfo=UTC)


def _money(value: int | Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def reset_database(session: Session) -> None:
    from app.models.domain import CommunicationAnalysis
    for model in (SimulationEvent, AuditEvent, RecoveryAction, RecoveryCase, PromiseToPay, Payment, CommunicationAnalysis, Communication, Invoice, Customer, SimulationState):
        session.execute(delete(model))
    session.flush()


def _invoice_status(archetype: str, index: int, due_date: date, outstanding: Decimal) -> InvoiceStatus:
    del archetype, index
    if outstanding == 0:
        return InvoiceStatus.PAID
    if due_date < SIMULATION_DATE:
        return InvoiceStatus.OVERDUE
    return InvoiceStatus.OPEN


def _add_payment(session: Session, invoice: Invoice, paid_amount: Decimal, payment_date: date, number: int) -> None:
    if paid_amount <= 0:
        return
    if paid_amount >= Decimal("175000"):
        first = (paid_amount / 2).quantize(Decimal("0.01"))
        parts = (first, paid_amount - first)
    else:
        parts = (paid_amount,)
    for offset, amount in enumerate(parts):
        session.add(Payment(
            id=_id(f"payment/{invoice.id}/{number}/{offset}"), invoice=invoice,
            amount=amount.quantize(Decimal("0.01")), payment_date=min(payment_date + timedelta(days=offset), SIMULATION_DATE - timedelta(days=1)),
            reference=f"PAY-{number:05d}-{offset + 1}",
        ))


def _communication(session: Session, customer: Customer, label: str, when: date, direction: CommunicationDirection, content: str) -> Communication:
    message = Communication(
        id=_id(f"communication/{customer.id}/{label}"), customer=customer, direction=direction,
        channel=CommunicationChannel.EMAIL if direction is CommunicationDirection.OUTBOUND else CommunicationChannel.PORTAL,
        content=content, occurred_at=_at(when),
    )
    session.add(message)
    return message


def _invoice_for_promise(invoices: list[Invoice], preferred_index: int) -> Invoice | None:
    preferred = invoices[preferred_index]
    if preferred.outstanding_amount > 0:
        return preferred
    return next((invoice for invoice in reversed(invoices) if invoice.outstanding_amount > 0), None)


def _add_promise(session: Session, *, label: str, customer: Customer, invoice: Invoice, promised_amount: Decimal, promised_date: date, status: PromiseStatus, source_communication: Communication, confidence: Decimal) -> PromiseToPay | None:
    amount = promised_amount.quantize(Decimal("0.01"))
    if amount <= 0:
        return None
    promise = PromiseToPay(
        id=_id(f"promise/{customer.id}/{label}"), customer=customer, invoice=invoice,
        promised_amount=amount, promised_date=promised_date, status=status,
        source_communication=source_communication, confidence=confidence,
    )
    session.add(promise)
    return promise


def _add_case(session: Session, customer: Customer, invoice: Invoice, state: RecoveryState, priority: RecoveryPriority, reason: str, *, aggressive: bool = True, stale: bool = False) -> RecoveryCase:
    activity_date = SIMULATION_DATE - timedelta(days=34 if stale else 2)
    opened = min(invoice.due_date + timedelta(days=7), activity_date)
    closed_at = _at(SIMULATION_DATE - timedelta(days=4)) if state in {RecoveryState.RESOLVED, RecoveryState.CLOSED} else None
    case = RecoveryCase(
        id=_id(f"case/{customer.id}/{invoice.id}"), customer=customer, invoice=invoice,
        current_state=state, priority=priority, opened_at=_at(opened), updated_at=_at(activity_date), closed_at=closed_at,
    )
    session.add(case)
    session.add(RecoveryAction(
        id=_id(f"action/{case.id}/note"), recovery_case=case, action_type=RecoveryActionType.NOTE,
        status=RecoveryActionStatus.EXECUTED, approval_status=ApprovalStatus.NOT_REQUIRED,
        reason=reason, created_at=_at(activity_date), executed_at=_at(activity_date),
    ))
    if aggressive and state not in {RecoveryState.RESOLVED, RecoveryState.CLOSED}:
        approval_required = customer.is_strategic_account
        session.add(RecoveryAction(
            id=_id(f"action/{case.id}/follow-up"), recovery_case=case, action_type=RecoveryActionType.FOLLOW_UP,
            status=RecoveryActionStatus.PENDING_APPROVAL if approval_required else RecoveryActionStatus.EXECUTED,
            approval_status=ApprovalStatus.PENDING if approval_required else ApprovalStatus.NOT_REQUIRED,
            reason="Current receivable facts require controlled operator review.", created_at=_at(activity_date),
            executed_at=None if approval_required else _at(activity_date),
        ))
    return case


def _invoice_amount(rng: random.Random, low: int, high: int) -> Decimal:
    return _money(rng.randint(low, high) + Decimal(rng.randint(1, 99)) / 100)


def _seed_invoices(session: Session, customer: Customer, blueprint: CustomerBlueprint, customer_index: int, rng: random.Random) -> list[Invoice]:
    spec = ARCHETYPES[blueprint.archetype]
    count = _invoice_count(customer_index)
    open_count = rng.randint(*spec.open_range)
    paid_count = count - open_count
    invoices: list[Invoice] = []
    for invoice_index in range(count):
        amount = _invoice_amount(rng, *spec.amount_range)
        is_open = invoice_index >= paid_count
        if is_open:
            age = rng.randint(*spec.overdue_range)
            due = SIMULATION_DATE - timedelta(days=age)
            # Keep one untouched receivable for factual broken-promise history;
            # later partial payments on other invoices must not fulfil it retroactively.
            fraction = Decimal("1") if spec.broken_promises and invoice_index == paid_count else Decimal(rng.randint(*spec.balance_range)) / Decimal("100")
            outstanding = (amount * fraction).quantize(Decimal("0.01"))
        else:
            due = SIMULATION_DATE - timedelta(days=rng.randint(24, 260))
            outstanding = Decimal("0.00")
        invoice = Invoice(
            id=_id(f"invoice/{customer_index}/{invoice_index}"), customer=customer,
            invoice_number=f"INV-{customer_index:03d}-{invoice_index + 1:02d}", issue_date=due - timedelta(days=rng.choice((15, 21, 30, 45))),
            due_date=due, original_amount=amount, outstanding_amount=outstanding,
            status=_invoice_status(blueprint.archetype, invoice_index, due, outstanding),
        )
        session.add(invoice)
        invoices.append(invoice)
        paid = amount - outstanding
        if paid > 0:
            payment_date = SIMULATION_DATE - timedelta(days=rng.randint(2, 12)) if is_open and spec.recent_partial_payment else due + timedelta(days=rng.randint(-4, 24))
            _add_payment(session, invoice, paid, payment_date, customer_index * 20 + invoice_index)
    outstanding = [invoice for invoice in invoices if invoice.outstanding_amount > 0]
    account_number = int(customer.account_reference.removeprefix("RM-"))
    dispute_count = spec.dispute_count
    if blueprint.archetype == "MIXED_STATE" and account_number in {66, 68}:
        dispute_count = 0
    if dispute_count:
        for invoice in outstanding[-dispute_count:]:
            invoice.status = InvoiceStatus.DISPUTED
    return invoices


def _seed_context(session: Session, customer: Customer, blueprint: CustomerBlueprint, invoices: list[Invoice], rng: random.Random) -> None:
    spec = ARCHETYPES[blueprint.archetype]
    outbound_age = rng.randint(8, 48) if not spec.stale_case else rng.randint(50, 82)
    _communication(session, customer, "operator-review", SIMULATION_DATE - timedelta(days=outbound_age), CommunicationDirection.OUTBOUND,
                   "Please confirm the settlement status and any invoice-specific blockers on the open balance.")
    unpaid = [invoice for invoice in invoices if invoice.outstanding_amount > 0]
    paid = [invoice for invoice in invoices if invoice.outstanding_amount == 0]

    if blueprint.archetype == "STALE_NO_RESPONSE":
        _communication(session, customer, "second-follow-up", SIMULATION_DATE - timedelta(days=38), CommunicationDirection.OUTBOUND, "This is a second request for a response on the long-outstanding balance.")
    elif blueprint.archetype == "DISPUTE_RESOLVED":
        _communication(session, customer, "resolution", SIMULATION_DATE - timedelta(days=5), CommunicationDirection.INBOUND, "The quantity review is complete and the invoice can return to the normal settlement process.")
    elif blueprint.archetype in {"PARTIAL_PAYMENT", "RECOVERING"}:
        _communication(session, customer, "recent-remittance", SIMULATION_DATE - timedelta(days=rng.randint(2, 8)), CommunicationDirection.INBOUND, "A partial remittance has been released; the residual balance remains under internal review.")
    elif blueprint.archetype == "DETERIORATING":
        _communication(session, customer, "cash-pressure", SIMULATION_DATE - timedelta(days=16), CommunicationDirection.INBOUND, "The previously expected release has slipped because customer receipts arrived later than planned.")
    elif blueprint.archetype in {"DISPUTE_BLOCKED", "MIXED_STATE"} and any(invoice.status is InvoiceStatus.DISPUTED for invoice in unpaid):
        disputed = next(invoice for invoice in reversed(unpaid) if invoice.status is InvoiceStatus.DISPUTED)
        _communication(session, customer, "dispute", SIMULATION_DATE - timedelta(days=rng.randint(7, 24)), CommunicationDirection.INBOUND, f"Invoice {disputed.invoice_number} is under a documented service or quantity review; undisputed invoices remain separate.")
    elif blueprint.archetype in {"ACTIVE_PROMISE", "TEMPORARILY_LATE", "STRATEGIC_HIGH_VALUE", "HIGH_VALUE_LOW_URGENCY"}:
        _communication(session, customer, "timing", SIMULATION_DATE - timedelta(days=rng.randint(2, 9)), CommunicationDirection.INBOUND, "The payment is included in an approved near-term release run; please monitor the committed date.")

    promise_invoice = _invoice_for_promise(invoices, -1) if unpaid else None
    broken_invoice = unpaid[0] if unpaid else None
    account_number = int(customer.account_reference.removeprefix("RM-"))
    broken_count = spec.broken_promises
    if blueprint.archetype == "BROKEN_PROMISE" and account_number % 2:
        broken_count = 1
    if blueprint.archetype == "MIXED_STATE" and account_number == 67:
        broken_count = 0
    for number in range(broken_count):
        if broken_invoice is None:
            break
        source = _communication(session, customer, f"broken-source-{number}", SIMULATION_DATE - timedelta(days=48 + number * 17), CommunicationDirection.INBOUND, "We expected to release a payment by the agreed date, but that commitment was not met.")
        _add_promise(session, label=f"broken-{number}", customer=customer, invoice=broken_invoice,
                     promised_amount=broken_invoice.outstanding_amount * Decimal("0.35"), promised_date=SIMULATION_DATE - timedelta(days=18 + number * 19),
                     status=PromiseStatus.BROKEN, source_communication=source, confidence=Decimal("0.5200") - Decimal(number) * Decimal("0.0800"))
    active_count = spec.active_promises
    if blueprint.archetype == "MIXED_STATE" and account_number in {65, 68}:
        active_count = 0
    for number in range(active_count):
        if promise_invoice is None:
            break
        source = _communication(session, customer, f"active-source-{number}", SIMULATION_DATE - timedelta(days=rng.randint(1, 7)), CommunicationDirection.INBOUND, "A controlled payment release is approved for the recorded commitment date.")
        _add_promise(session, label=f"active-{number}", customer=customer, invoice=promise_invoice,
                     promised_amount=promise_invoice.outstanding_amount * Decimal(str(rng.choice(("0.35", "0.50", "0.65", "0.80")))),
                     promised_date=SIMULATION_DATE + timedelta(days=rng.randint(3, 14)), status=PromiseStatus.ACTIVE,
                     source_communication=source, confidence=Decimal(str(rng.choice(("0.6100", "0.7200", "0.8400", "0.9100")))))
    for number in range(spec.fulfilled_promises):
        if not paid:
            break
        invoice = paid[-1]
        source = _communication(session, customer, f"fulfilled-source-{number}", invoice.due_date - timedelta(days=6), CommunicationDirection.INBOUND, "The invoice was scheduled and settled against the recorded commitment.")
        _add_promise(session, label=f"fulfilled-{number}", customer=customer, invoice=invoice, promised_amount=invoice.original_amount,
                     promised_date=invoice.due_date + timedelta(days=2), status=PromiseStatus.FULFILLED, source_communication=source, confidence=Decimal("0.9300"))

    case_invoice = promise_invoice or (invoices[-1] if invoices else None)
    if spec.case_state is not None and case_invoice is not None:
        case_state = spec.case_state
        if blueprint.archetype == "MIXED_STATE" and not any(invoice.status is InvoiceStatus.DISPUTED for invoice in unpaid):
            case_state = RecoveryState.PROMISE_MONITORING if active_count else RecoveryState.IN_PROGRESS
        reason = {
            "DISPUTE_BLOCKED": "A documented invoice dispute blocks collection on the affected receivable.",
            "MIXED_STATE": "The account combines disputed, promised, partially paid, and overdue exposure.",
            "RECOVERING": "Recent payment evidence reduced exposure; the residual recovery plan remains open.",
            "DETERIORATING": "Payment timing weakened and the recorded commitment was missed.",
            "CLOSED_RESOLVED": "The historical recovery case closed after full settlement.",
        }.get(blueprint.archetype, "The current account facts require an operator-owned recovery workflow.")
        _add_case(session, customer, case_invoice, case_state, spec.case_priority, reason,
                  aggressive=case_state is not RecoveryState.AWAITING_CUSTOMER, stale=spec.stale_case)


def seed_database(session: Session, *, reset: bool = False) -> dict[str, int | Decimal]:
    """Persist the one canonical, deterministic Phase B baseline portfolio."""
    if session.scalar(select(func.count(Customer.id))) and not reset:
        raise RuntimeError("Database already contains customers. Re-run with --reset to replace development seed data.")
    if reset:
        reset_database(session)
    invoices_by_customer: dict[uuid.UUID, list[Invoice]] = {}
    for customer_index, blueprint in enumerate(BLUEPRINTS, start=1):
        rng = random.Random(SEED + customer_index * 104729)
        customer = Customer(id=_id(f"customer/{customer_index}"), name=blueprint.name, account_reference=f"RM-{customer_index:04d}", segment=blueprint.industry, is_strategic_account=blueprint.strategic)
        session.add(customer)
        invoices = _seed_invoices(session, customer, blueprint, customer_index, rng)
        invoices_by_customer[customer.id] = invoices
        _seed_context(session, customer, blueprint, invoices, rng)
    session.add(SimulationState(id=_id("simulation/default"), name="default", simulation_date=SIMULATION_DATE))
    session.flush()
    for customer_id, invoices in invoices_by_customer.items():
        outstanding = sum((invoice.outstanding_amount for invoice in invoices), Decimal("0"))
        session.add(AuditEvent(id=_id(f"audit/{customer_id}"), entity_type="Customer", entity_id=customer_id,
                               event_type="SYNTHETIC_PORTFOLIO_SEEDED", actor_type="system",
                               payload={"outstanding_amount": str(outstanding), "simulation_date": str(SIMULATION_DATE)}, occurred_at=_at(SIMULATION_DATE)))
    session.flush()
    validate_portfolio(session)
    session.commit()
    return portfolio_summary(session)


def validate_portfolio(session: Session) -> None:
    """Assert financial, timeline, blocker, and diversity invariants."""
    customers = session.scalar(select(func.count(Customer.id))) or 0
    invoices = session.scalars(select(Invoice)).all()
    assert customers == len(BLUEPRINTS) and 80 <= customers <= 90
    assert len(invoices) == sum(_invoice_count(index) for index in range(1, len(BLUEPRINTS) + 1))
    assert len({blueprint.name for blueprint in BLUEPRINTS}) == len(BLUEPRINTS)
    assert len(Counter(blueprint.archetype for blueprint in BLUEPRINTS)) >= 15
    for invoice in invoices:
        paid = sum((payment.amount for payment in invoice.payments), Decimal("0"))
        assert Decimal("0") <= invoice.outstanding_amount <= invoice.original_amount
        assert paid == invoice.original_amount - invoice.outstanding_amount, f"balance mismatch for {invoice.invoice_number}"
        assert not (invoice.status is InvoiceStatus.PAID and invoice.outstanding_amount > 0)
        if invoice.status is InvoiceStatus.DISPUTED:
            assert invoice.outstanding_amount > 0
    for promise in session.scalars(select(PromiseToPay)):
        assert promise.promised_amount > 0 and promise.invoice is not None
        if promise.status is PromiseStatus.ACTIVE:
            assert promise.promised_date >= SIMULATION_DATE and promise.invoice.outstanding_amount > 0
        elif promise.status is PromiseStatus.BROKEN:
            assert promise.promised_date < SIMULATION_DATE
        elif promise.status is PromiseStatus.FULFILLED:
            assert sum((payment.amount for payment in promise.invoice.payments), Decimal("0")) >= promise.promised_amount
    disputed_cases = session.scalars(select(RecoveryCase).join(Invoice).where(Invoice.status == InvoiceStatus.DISPUTED)).all()
    assert len(disputed_cases) >= 5
    for case in disputed_cases:
        assert case.current_state is RecoveryState.AWAITING_CUSTOMER
        assert all(action.action_type is RecoveryActionType.NOTE for action in case.actions)
    overdue_ages = {(SIMULATION_DATE - invoice.due_date).days for invoice in invoices if invoice.status is InvoiceStatus.OVERDUE}
    assert len(overdue_ages) >= 25
    assert len({invoice.original_amount for invoice in invoices}) >= len(invoices) // 2
    assert session.scalar(select(func.count(PromiseToPay.id)).where(PromiseToPay.status == PromiseStatus.BROKEN)) >= 10


def portfolio_summary(session: Session) -> dict[str, int | Decimal]:
    invoices = session.scalars(select(Invoice)).all()
    return {
        "customers": session.scalar(select(func.count(Customer.id))) or 0,
        "invoices": len(invoices), "open_invoices": sum(invoice.outstanding_amount > 0 for invoice in invoices),
        "overdue_invoices": sum(invoice.status is InvoiceStatus.OVERDUE for invoice in invoices),
        "outstanding_amount": sum((invoice.outstanding_amount for invoice in invoices), Decimal("0")),
        "overdue_amount": sum((invoice.outstanding_amount for invoice in invoices if invoice.status is InvoiceStatus.OVERDUE), Decimal("0")),
        "payments": session.scalar(select(func.count(Payment.id))) or 0,
        "promises": session.scalar(select(func.count(PromiseToPay.id))) or 0,
        "broken_promises": session.scalar(select(func.count(PromiseToPay.id)).where(PromiseToPay.status == PromiseStatus.BROKEN)) or 0,
        "active_disputes": sum(invoice.status is InvoiceStatus.DISPUTED for invoice in invoices),
        "recovery_cases": session.scalar(select(func.count(RecoveryCase.id))) or 0,
    }
