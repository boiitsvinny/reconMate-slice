from datetime import timedelta
from decimal import Decimal

from app.models.domain import Invoice, InvoiceStatus, PromiseStatus
from app.seed.portfolio import BLUEPRINTS, SIMULATION_DATE, _invoice_count, _invoice_for_promise, _invoice_status


def test_portfolio_has_required_archetypes_and_size() -> None:
    archetypes = {blueprint.archetype for blueprint in BLUEPRINTS}
    assert len(BLUEPRINTS) == 56
    assert sum(_invoice_count(index) for index in range(1, len(BLUEPRINTS) + 1)) == 296
    assert {"HEALTHY_RELIABLE", "RELIABLE_LATE", "DETERIORATING", "PROMISE_BREAKER", "PARTIAL_PAYER", "DISPUTED_ACCOUNT", "STRATEGIC_HIGH_VALUE", "SEVERELY_OVERDUE"} <= archetypes


def test_seed_status_timeline_rules() -> None:
    assert _invoice_status("HEALTHY_RELIABLE", 0, SIMULATION_DATE - timedelta(days=1), Decimal("0")) is InvoiceStatus.PAID
    assert _invoice_status("PROMISE_BREAKER", 5, SIMULATION_DATE - timedelta(days=1), Decimal("100")) is InvoiceStatus.OVERDUE
    assert _invoice_status("DISPUTED_ACCOUNT", 4, SIMULATION_DATE - timedelta(days=1), Decimal("100")) is InvoiceStatus.DISPUTED
    assert PromiseStatus.ACTIVE.value == "ACTIVE"


def test_promise_invoice_falls_back_to_newest_positive_balance() -> None:
    paid_invoice = Invoice(outstanding_amount=Decimal("0.00"))
    unpaid_invoice = Invoice(outstanding_amount=Decimal("125.00"))

    assert _invoice_for_promise([paid_invoice, unpaid_invoice], 0) is unpaid_invoice
    assert _invoice_for_promise([paid_invoice], 0) is None
