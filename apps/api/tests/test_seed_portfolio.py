"""Quality invariants for the deterministic Phase B baseline generator."""

import random
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from app.intelligence.operational_service import evaluate_customer_intelligence
from app.models.domain import Customer, Invoice, InvoiceStatus, PromiseStatus
from app.recommendations.schemas import RecommendedAction
from app.recommendations.service import recommend_case
from app.seed.portfolio import (
    ARCHETYPES, BLUEPRINTS, SEED, SIMULATION_DATE, _invoice_count,
    _invoice_for_promise, _invoice_status, _seed_context, _seed_invoices,
)
from app.simulation.service import _available_event_kinds


class RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []

    def add(self, record: object) -> None:
        self.records.append(record)


def _generated_customers() -> list[Customer]:
    session = RecordingSession()
    customers = []
    for index, blueprint in enumerate(BLUEPRINTS, start=1):
        rng = random.Random(SEED + index * 104729)
        customer = Customer(name=blueprint.name, account_reference=f"RM-{index:04d}", segment=blueprint.industry, is_strategic_account=blueprint.strategic)
        invoices = _seed_invoices(session, customer, blueprint, index, rng)  # type: ignore[arg-type]
        _seed_context(session, customer, blueprint, invoices, rng)  # type: ignore[arg-type]
        customers.append(customer)
    return customers


def test_portfolio_has_target_size_names_and_archetype_coverage() -> None:
    distribution = Counter(blueprint.archetype for blueprint in BLUEPRINTS)
    invoice_counts = [_invoice_count(index) for index in range(1, len(BLUEPRINTS) + 1)]
    assert len(BLUEPRINTS) == 84
    assert len({blueprint.name for blueprint in BLUEPRINTS}) == 84
    assert not any("Expansion Account" in blueprint.name for blueprint in BLUEPRINTS)
    assert set(ARCHETYPES) == set(distribution)
    assert len(distribution) == 16
    assert distribution["HEALTHY_LOW_RISK"] == 16
    assert 1 <= min(invoice_counts) < max(invoice_counts) <= 10
    assert len(set(invoice_counts)) >= 7


def test_generator_is_deterministic_and_financially_coherent() -> None:
    first = _generated_customers()
    second = _generated_customers()
    signature = lambda customers: [
        (customer.name, [(invoice.due_date, invoice.original_amount, invoice.outstanding_amount, invoice.status) for invoice in customer.invoices])
        for customer in customers
    ]
    assert signature(first) == signature(second)
    invoices = [invoice for customer in first for invoice in customer.invoices]
    assert all(Decimal("0") <= invoice.outstanding_amount <= invoice.original_amount for invoice in invoices)
    assert all(not (invoice.status is InvoiceStatus.PAID and invoice.outstanding_amount > 0) for invoice in invoices)
    assert all(invoice.outstanding_amount > 0 for invoice in invoices if invoice.status is InvoiceStatus.DISPUTED)
    assert len({(SIMULATION_DATE - invoice.due_date).days for invoice in invoices if invoice.status is InvoiceStatus.OVERDUE}) >= 25
    assert len({invoice.original_amount for invoice in invoices}) >= len(invoices) // 2


def test_promise_dispute_and_resolved_states_are_coherent() -> None:
    customers = _generated_customers()
    promises = [promise for customer in customers for promise in customer.promises_to_pay]
    active = [promise for promise in promises if promise.status is PromiseStatus.ACTIVE]
    disputed = [invoice for customer in customers for invoice in customer.invoices if invoice.status is InvoiceStatus.DISPUTED]
    resolved = [customer for customer, blueprint in zip(customers, BLUEPRINTS, strict=True) if blueprint.archetype == "CLOSED_RESOLVED"]
    assert len(active) >= 20
    assert all(promise.promised_amount > 0 and promise.promised_date >= SIMULATION_DATE and promise.invoice.outstanding_amount > 0 for promise in active)
    assert len(disputed) >= 5
    assert all(invoice.outstanding_amount > 0 for invoice in disputed)
    assert resolved and all(invoice.outstanding_amount == 0 for invoice in resolved[0].invoices)
    assert all(case.closed_at is not None for case in resolved[0].recovery_cases)


def test_existing_scoring_produces_a_real_priority_spread() -> None:
    results = [evaluate_customer_intelligence(customer, SIMULATION_DATE) for customer in _generated_customers()]
    levels = Counter(result.level.value for result in results)
    assert levels.keys() >= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert levels["CRITICAL"] < len(results) // 3
    urgent_fact_shapes = {
        (result.metrics.overdue_invoice_count, result.metrics.max_days_overdue, result.metrics.broken_promise_count,
         result.metrics.active_promise_count, result.metrics.active_dispute_count, result.metrics.days_since_last_payment)
        for result in results if result.level.value in {"HIGH", "CRITICAL"}
    }
    assert len(urgent_fact_shapes) >= 12
    closed = next(result for result, blueprint in zip(results, BLUEPRINTS, strict=True) if blueprint.archetype == "CLOSED_RESOLVED")
    assert closed.level.value == "LOW" and closed.recommendation.action.value == "MONITOR"


def test_portfolio_has_believable_current_and_aged_receivables() -> None:
    customers = _generated_customers()
    invoices = [invoice for customer in customers for invoice in customer.invoices]
    open_invoices = [invoice for invoice in invoices if invoice.outstanding_amount > 0]
    current = [invoice for invoice in open_invoices if invoice.due_date >= SIMULATION_DATE]
    overdue = [invoice for invoice in open_invoices if invoice.due_date < SIMULATION_DATE]
    total_outstanding = sum((invoice.outstanding_amount for invoice in open_invoices), Decimal("0"))
    overdue_exposure = sum((invoice.outstanding_amount for invoice in overdue), Decimal("0"))
    healthy_current_accounts = [
        customer for customer, blueprint in zip(customers, BLUEPRINTS, strict=True)
        if blueprint.archetype == "HEALTHY_LOW_RISK"
        and any(invoice.outstanding_amount > 0 and invoice.due_date >= SIMULATION_DATE for invoice in customer.invoices)
    ]
    aging_buckets = Counter(
        "1-30" if (SIMULATION_DATE - invoice.due_date).days <= 30
        else "31-60" if (SIMULATION_DATE - invoice.due_date).days <= 60
        else "61-90" if (SIMULATION_DATE - invoice.due_date).days <= 90
        else "90+"
        for invoice in overdue
    )
    assert len(current) >= 50
    assert len(healthy_current_accounts) >= 8
    assert Decimal("0.45") <= overdue_exposure / total_outstanding <= Decimal("0.80")
    assert set(aging_buckets) == {"1-30", "31-60", "61-90", "90+"}
    assert min(aging_buckets.values()) >= 10


def test_high_and_critical_accounts_are_a_meaningful_minority() -> None:
    results = [evaluate_customer_intelligence(customer, SIMULATION_DATE) for customer in _generated_customers()]
    urgent = sum(result.level.value in {"HIGH", "CRITICAL"} for result in results)
    assert len(results) // 5 <= urgent < len(results) // 2
    recommendations = Counter(result.recommendation.action.value for result in results)
    assert recommendations.keys() >= {"MONITOR", "FOLLOW_UP", "ESCALATE", "REVIEW_DISPUTE", "WAIT_FOR_PROMISE", "PRIORITIZE_RECOVERY"}


def test_ironclad_is_a_deterministic_provider_demo_qualifier() -> None:
    customer = next(customer for customer in _generated_customers() if customer.account_reference == "RM-0026")
    qualifying = [
        case for case in customer.recovery_cases
        if (recommendation := recommend_case(case, SIMULATION_DATE)).recommended_action
        in {RecommendedAction.SEND_PAYMENT_REMINDER, RecommendedAction.REQUEST_PAYMENT_DATE}
        and not recommendation.blockers
    ]
    assert len(qualifying) == 1
    assert qualifying[0].invoice.outstanding_amount > 0
    assert qualifying[0].invoice.due_date < SIMULATION_DATE


def test_phase_a_has_safe_targets_across_every_supported_event_type() -> None:
    customers = _generated_customers()
    invoices = [invoice for customer in customers for invoice in customer.invoices]
    promises = [promise for customer in customers for promise in customer.promises_to_pay]
    assert set(_available_event_kinds(invoices, promises, set())) == {
        "PARTIAL_PAYMENT", "FULL_PAYMENT", "PROMISE_CREATED", "PROMISE_BROKEN",
        "DISPUTE_OPENED", "DISPUTE_RESOLVED", "CUSTOMER_DELAY_RESPONSE",
    }


def test_seed_status_timeline_rules() -> None:
    assert _invoice_status("HEALTHY_LOW_RISK", 0, SIMULATION_DATE - timedelta(days=1), Decimal("0")) is InvoiceStatus.PAID
    assert _invoice_status("BROKEN_PROMISE", 5, SIMULATION_DATE - timedelta(days=1), Decimal("100")) is InvoiceStatus.OVERDUE
    assert _invoice_status("DISPUTE_BLOCKED", 4, SIMULATION_DATE + timedelta(days=2), Decimal("100")) is InvoiceStatus.OPEN


def test_promise_invoice_falls_back_to_newest_positive_balance() -> None:
    paid_invoice = Invoice(outstanding_amount=Decimal("0.00"))
    unpaid_invoice = Invoice(outstanding_amount=Decimal("125.00"))
    assert _invoice_for_promise([paid_invoice, unpaid_invoice], 0) is unpaid_invoice
    assert _invoice_for_promise([paid_invoice], 0) is None
