from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models.domain import (
    Communication, CommunicationChannel, CommunicationDirection, Customer, Invoice,
    InvoiceStatus, Payment, PromiseStatus, PromiseToPay, RecoveryPriority, RecoveryState,
    RecoveryCase,
)
from app.recovery.engine import _audit_once, _existing_audit_keys, evaluate_case, evaluate_invoice, evaluate_promise

SIM_DATE = date(2026, 8, 1)


def _customer() -> Customer:
    return Customer(name="Test Customer", account_reference="TEST-001", is_strategic_account=False)


def _invoice(customer: Customer, outstanding: str, due_date: date, status: InvoiceStatus = InvoiceStatus.OPEN) -> Invoice:
    return Invoice(customer=customer, invoice_number="TEST-INV", issue_date=due_date - timedelta(days=30), due_date=due_date,
                   original_amount=Decimal("100.00"), outstanding_amount=Decimal(outstanding), status=status)


def _promise(customer: Customer, invoice: Invoice, promised_date: date, status: PromiseStatus = PromiseStatus.ACTIVE) -> PromiseToPay:
    source = Communication(customer=customer, direction=CommunicationDirection.INBOUND, channel=CommunicationChannel.EMAIL,
                           content="We will settle this shortly.", occurred_at=datetime(2026, 7, 20, tzinfo=UTC))
    return PromiseToPay(customer=customer, invoice=invoice, promised_amount=Decimal("100.00"),
                        promised_date=promised_date, status=status, source_communication=source, confidence=Decimal("0.8"))


def test_invoice_facts_detect_paid_open_due_and_overdue() -> None:
    customer = _customer()
    assert evaluate_invoice(_invoice(customer, "0", SIM_DATE - timedelta(days=10)), SIM_DATE).state == "PAID"
    assert evaluate_invoice(_invoice(customer, "100", SIM_DATE + timedelta(days=1)), SIM_DATE).state == "OPEN"
    assert evaluate_invoice(_invoice(customer, "100", SIM_DATE), SIM_DATE).state == "DUE"
    facts = evaluate_invoice(_invoice(customer, "50", SIM_DATE - timedelta(days=8)), SIM_DATE)
    assert facts.state == "OVERDUE"
    assert facts.days_overdue == 8
    assert facts.partially_paid is True


def test_future_issued_invoice_is_scheduled_and_blocked_from_recovery() -> None:
    customer = _customer()
    invoice = Invoice(
        customer=customer, invoice_number="FUTURE-INV", issue_date=SIM_DATE + timedelta(days=5),
        due_date=SIM_DATE - timedelta(days=1), original_amount=Decimal("100"),
        outstanding_amount=Decimal("100"), status=InvoiceStatus.OVERDUE,
    )
    case = RecoveryCase(customer=customer, invoice=invoice, current_state=RecoveryState.NEW, priority=RecoveryPriority.NORMAL)
    facts = evaluate_invoice(invoice, SIM_DATE)
    evaluation = evaluate_case(case, SIM_DATE)
    assert facts.state == "SCHEDULED" and facts.days_overdue == 0
    assert evaluation.eligibility.allowed is False
    assert "INVOICE_SCHEDULED" in evaluation.eligibility.blocking_reasons


def test_promise_facts_detect_active_broken_and_fulfilled() -> None:
    customer = _customer()
    invoice = _invoice(customer, "100", SIM_DATE - timedelta(days=2))
    active = _promise(customer, invoice, SIM_DATE + timedelta(days=2))
    broken = _promise(customer, invoice, SIM_DATE - timedelta(days=1))
    assert evaluate_promise(active, SIM_DATE).state == "ACTIVE"
    assert evaluate_promise(broken, SIM_DATE).state == "BROKEN"
    paid_invoice = _invoice(customer, "0", SIM_DATE - timedelta(days=2), InvoiceStatus.PAID)
    paid_invoice.payments = [Payment(invoice=paid_invoice, amount=Decimal("100"), payment_date=SIM_DATE - timedelta(days=1), reference="P-1")]
    fulfilled = _promise(customer, paid_invoice, SIM_DATE - timedelta(days=1), PromiseStatus.FULFILLED)
    assert evaluate_promise(fulfilled, SIM_DATE).state == "FULFILLED"


def test_dispute_blocks_recovery_and_cases_follow_factual_states() -> None:
    customer = _customer()
    disputed_invoice = _invoice(customer, "100", SIM_DATE - timedelta(days=10), InvoiceStatus.DISPUTED)
    disputed_case = RecoveryCase(customer=customer, invoice=disputed_invoice, current_state=RecoveryState.IN_PROGRESS,
                                 priority=RecoveryPriority.NORMAL)
    disputed = evaluate_case(disputed_case, SIM_DATE)
    assert disputed.active_dispute is True
    assert disputed.eligibility.allowed is False
    assert "ACTIVE_DISPUTE" in disputed.eligibility.blocking_reasons
    assert disputed.derived_state == RecoveryState.AWAITING_CUSTOMER.value

    paid_case = RecoveryCase(customer=customer, invoice=_invoice(customer, "0", SIM_DATE - timedelta(days=5), InvoiceStatus.PAID),
                             current_state=RecoveryState.IN_PROGRESS, priority=RecoveryPriority.NORMAL)
    assert evaluate_case(paid_case, SIM_DATE).derived_state == RecoveryState.RESOLVED.value

    overdue_invoice = _invoice(customer, "100", SIM_DATE - timedelta(days=5), InvoiceStatus.OVERDUE)
    eligible_case = RecoveryCase(customer=customer, invoice=overdue_invoice, current_state=RecoveryState.NEW,
                                 priority=RecoveryPriority.NORMAL)
    assert evaluate_case(eligible_case, SIM_DATE).eligibility.allowed is True

    active_invoice = _invoice(customer, "100", SIM_DATE - timedelta(days=5), InvoiceStatus.OVERDUE)
    active_promise = _promise(customer, active_invoice, SIM_DATE + timedelta(days=2))
    active_invoice.promises_to_pay.append(active_promise)
    active_case = RecoveryCase(customer=customer, invoice=active_invoice, current_state=RecoveryState.IN_PROGRESS,
                               priority=RecoveryPriority.NORMAL)
    active_evaluation = evaluate_case(active_case, SIM_DATE)
    assert active_evaluation.derived_state == RecoveryState.PROMISE_MONITORING.value
    assert "ACTIVE_PAYMENT_PROMISE" in active_evaluation.eligibility.blocking_reasons

    broken_invoice = _invoice(customer, "100", SIM_DATE - timedelta(days=5), InvoiceStatus.OVERDUE)
    broken_promise = _promise(customer, broken_invoice, SIM_DATE - timedelta(days=1))
    broken_invoice.promises_to_pay.append(broken_promise)
    broken_case = RecoveryCase(customer=customer, invoice=broken_invoice, current_state=RecoveryState.IN_PROGRESS,
                               priority=RecoveryPriority.HIGH)
    assert evaluate_case(broken_case, SIM_DATE).derived_state == RecoveryState.ESCALATED.value


def test_audit_event_is_created_once() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.events = []

        def scalar(self, _query):
            return None

        def add(self, event):
            self.events.append(event)

    session = FakeSession()
    _audit_once(session, "Invoice", __import__("uuid").uuid4(), "INVOICE_OVERDUE_DETECTED", {"days_overdue": 1}, datetime(2026, 8, 1, tzinfo=UTC))
    assert len(session.events) == 1
    assert session.events[0].event_type == "INVOICE_OVERDUE_DETECTED"


def test_existing_audit_identities_are_loaded_in_one_bulk_query() -> None:
    invoice_id = __import__("uuid").uuid4()
    promise_id = __import__("uuid").uuid4()
    requested = {
        ("Invoice", invoice_id, "INVOICE_OVERDUE_DETECTED"),
        ("PromiseToPay", promise_id, "PROMISE_BROKEN_DETECTED"),
    }

    class FakeSession:
        def __init__(self) -> None:
            self.execute_calls = 0

        def execute(self, _query):
            self.execute_calls += 1
            class Rows(list):
                def all(self):
                    return self

            return Rows([("Invoice", invoice_id, "INVOICE_OVERDUE_DETECTED")])

    session = FakeSession()
    existing = _existing_audit_keys(session, requested)  # type: ignore[arg-type]
    assert existing == {("Invoice", invoice_id, "INVOICE_OVERDUE_DETECTED")}
    assert session.execute_calls == 1


def test_preloaded_audit_identity_avoids_duplicate_lookup_and_insert() -> None:
    entity_id = __import__("uuid").uuid4()
    key = ("Invoice", entity_id, "INVOICE_OVERDUE_DETECTED")

    class FakeSession:
        def __init__(self) -> None:
            self.events = []

        def scalar(self, _query):
            raise AssertionError("preloaded audit checks must not issue a per-record SELECT")

        def add(self, event):
            self.events.append(event)

    session = FakeSession()
    _audit_once(
        session, key[0], key[1], key[2], {"days_overdue": 1},
        datetime(2026, 8, 1, tzinfo=UTC), existing={key},  # type: ignore[arg-type]
    )
    assert session.events == []
