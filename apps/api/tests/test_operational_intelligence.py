from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.intelligence.operational_schemas import PriorityLevel, RecommendationAction, SignalType
from app.intelligence.operational_service import (
    evaluate_case_intelligence,
    evaluate_customer_intelligence,
    priority_level,
)
from app.models.domain import (
    Customer,
    Invoice,
    InvoiceStatus,
    PromiseStatus,
    PromiseToPay,
    RecoveryCase,
    RecoveryPriority,
    RecoveryState,
)


SIMULATION_DATE = date(2026, 8, 1)


def _customer(name: str = "Intelligence Test") -> Customer:
    return Customer(id=uuid4(), name=name, account_reference=f"INT-{uuid4()}")


def _invoice(
    customer: Customer,
    *,
    outstanding: str,
    days_overdue: int,
    status: InvoiceStatus = InvoiceStatus.OVERDUE,
) -> Invoice:
    amount = max(Decimal(outstanding), Decimal("1000"))
    return Invoice(
        id=uuid4(),
        customer=customer,
        invoice_number=f"INV-{uuid4()}",
        issue_date=SIMULATION_DATE - timedelta(days=days_overdue + 30),
        due_date=SIMULATION_DATE - timedelta(days=days_overdue),
        original_amount=amount,
        outstanding_amount=Decimal(outstanding),
        status=status,
    )


def _promise(customer: Customer, invoice: Invoice, *, days_late: int = 5) -> PromiseToPay:
    return PromiseToPay(
        id=uuid4(),
        customer=customer,
        invoice=invoice,
        promised_amount=min(invoice.outstanding_amount, Decimal("1000")),
        promised_date=SIMULATION_DATE - timedelta(days=days_late),
        status=PromiseStatus.BROKEN,
    )


def test_high_overdue_exposure_increases_priority() -> None:
    low = _customer("Low exposure")
    _invoice(low, outstanding="10000", days_overdue=10)
    high = _customer("High exposure")
    _invoice(high, outstanding="300000", days_overdue=10)

    low_result = evaluate_customer_intelligence(low, SIMULATION_DATE)
    high_result = evaluate_customer_intelligence(high, SIMULATION_DATE)

    assert high_result.score > low_result.score
    assert SignalType.HIGH_VALUE_OVERDUE in {signal.type for signal in high_result.signals}


def test_long_overdue_invoices_increase_priority() -> None:
    recent = _customer("Recently overdue")
    _invoice(recent, outstanding="10000", days_overdue=10)
    long_overdue = _customer("Long overdue")
    _invoice(long_overdue, outstanding="10000", days_overdue=125)

    recent_result = evaluate_customer_intelligence(recent, SIMULATION_DATE)
    long_result = evaluate_customer_intelligence(long_overdue, SIMULATION_DATE)

    assert long_result.score > recent_result.score
    factor = next(item for item in long_result.factors if item.type is SignalType.LONG_OVERDUE)
    assert "125 days overdue" in factor.explanation


def test_multiple_broken_promises_have_stronger_impact() -> None:
    one = _customer("One broken promise")
    one_invoice = _invoice(one, outstanding="10000", days_overdue=10)
    _promise(one, one_invoice)
    multiple = _customer("Multiple broken promises")
    multiple_invoice = _invoice(multiple, outstanding="10000", days_overdue=10)
    _promise(multiple, multiple_invoice)
    _promise(multiple, multiple_invoice, days_late=15)

    one_result = evaluate_customer_intelligence(one, SIMULATION_DATE)
    multiple_result = evaluate_customer_intelligence(multiple, SIMULATION_DATE)

    assert multiple_result.score > one_result.score
    assert SignalType.BROKEN_PROMISE in {signal.type for signal in one_result.signals}
    assert SignalType.MULTIPLE_BROKEN_PROMISES in {signal.type for signal in multiple_result.signals}


def test_active_dispute_changes_recommendation_without_executing_action() -> None:
    customer = _customer("Disputed account")
    invoice = _invoice(customer, outstanding="50000", days_overdue=45, status=InvoiceStatus.DISPUTED)
    RecoveryCase(
        id=uuid4(),
        customer=customer,
        invoice=invoice,
        current_state=RecoveryState.AWAITING_CUSTOMER,
        priority=RecoveryPriority.NORMAL,
        opened_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 31, tzinfo=UTC),
    )

    result = evaluate_customer_intelligence(customer, SIMULATION_DATE)

    assert SignalType.ACTIVE_DISPUTE in {signal.type for signal in result.signals}
    assert result.recommendation.action is RecommendationAction.REVIEW_DISPUTE
    assert result.recommendation.operator_confirmation_required is True
    assert invoice.status is InvoiceStatus.DISPUTED


def test_case_intelligence_uses_case_scope_and_current_customer_promise_history() -> None:
    customer = _customer("Case account")
    invoice = _invoice(customer, outstanding="25000", days_overdue=40)
    promise = _promise(customer, invoice)
    case = RecoveryCase(
        id=uuid4(),
        customer=customer,
        invoice=invoice,
        current_state=RecoveryState.IN_PROGRESS,
        priority=RecoveryPriority.HIGH,
        opened_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 31, tzinfo=UTC),
    )

    result = evaluate_case_intelligence(case, SIMULATION_DATE)

    assert result.entity_type == "RECOVERY_CASE"
    assert result.entity_id == str(case.id)
    assert result.metrics.broken_promise_count == 1
    assert result.metrics.overdue_exposure == invoice.outstanding_amount
    assert SignalType.BROKEN_PROMISE in {signal.type for signal in result.signals}
    assert promise.status is PromiseStatus.BROKEN


def test_scores_are_bounded_and_priority_thresholds_are_stable() -> None:
    assert priority_level(0) is PriorityLevel.LOW
    assert priority_level(19) is PriorityLevel.LOW
    assert priority_level(20) is PriorityLevel.MEDIUM
    assert priority_level(45) is PriorityLevel.HIGH
    assert priority_level(79) is PriorityLevel.HIGH
    assert priority_level(80) is PriorityLevel.CRITICAL
    assert priority_level(100) is PriorityLevel.CRITICAL

    customer = _customer("Maximum risk")
    for _ in range(7):
        invoice = _invoice(customer, outstanding="500000", days_overdue=180)
        _promise(customer, invoice)
        _promise(customer, invoice, days_late=30)
    result = evaluate_customer_intelligence(customer, SIMULATION_DATE)
    assert 0 <= result.score <= 100
    assert result.score == 100


def test_factors_and_recommendations_follow_actual_conditions() -> None:
    healthy = _customer("Healthy")
    _invoice(healthy, outstanding="1000", days_overdue=-10, status=InvoiceStatus.OPEN)
    healthy_result = evaluate_customer_intelligence(healthy, SIMULATION_DATE)
    assert healthy_result.score == 0
    assert healthy_result.factors == []
    assert healthy_result.recommendation.action is RecommendationAction.MONITOR

    overdue = _customer("Needs follow-up")
    _invoice(overdue, outstanding="10000", days_overdue=5)
    overdue_result = evaluate_customer_intelligence(overdue, SIMULATION_DATE)
    assert overdue_result.recommendation.action is RecommendationAction.FOLLOW_UP
    assert overdue_result.metrics.overdue_exposure == Decimal("10000")
    assert all(factor.contributing_value is not None for factor in overdue_result.factors)
