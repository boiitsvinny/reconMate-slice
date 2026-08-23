"""Focused invariants for the deterministic simulation foundation."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.domain import Customer, Invoice, InvoiceStatus, PromiseStatus, PromiseToPay, RecoveryCase, RecoveryPriority, RecoveryState
from app.recovery.engine import evaluate_case, evaluate_invoice
from app.simulation.service import _event_id


def test_simulation_event_identity_is_repeatable() -> None:
    assert _event_id(9, 0) == _event_id(9, 0)
    assert _event_id(9, 0) != _event_id(10, 0)


def test_payment_fact_changes_recovery_without_operator_action() -> None:
    today = date(2026, 8, 2)
    customer = Customer(id=uuid4(), name="Simulation Test", account_reference="SIM-TEST")
    invoice = Invoice(id=uuid4(), customer=customer, invoice_number="SIM-1", issue_date=date(2026, 7, 1), due_date=date(2026, 7, 31), original_amount=Decimal("100"), outstanding_amount=Decimal("0"), status=InvoiceStatus.PAID)
    case = RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=RecoveryState.IN_PROGRESS, priority=RecoveryPriority.NORMAL)
    assert evaluate_invoice(invoice, today).state == "PAID"
    assert evaluate_case(case, today).derived_state == RecoveryState.RESOLVED.value
    assert case.actions == []


def test_broken_promise_is_a_factual_recovery_condition() -> None:
    today = date(2026, 8, 2)
    customer = Customer(id=uuid4(), name="Promise Test", account_reference="PROMISE-TEST")
    invoice = Invoice(id=uuid4(), customer=customer, invoice_number="SIM-2", issue_date=date(2026, 7, 1), due_date=date(2026, 7, 20), original_amount=Decimal("100"), outstanding_amount=Decimal("100"), status=InvoiceStatus.OVERDUE)
    promise = PromiseToPay(id=uuid4(), customer=customer, invoice=invoice, promised_amount=Decimal("100"), promised_date=date(2026, 8, 1), status=PromiseStatus.BROKEN)
    case = RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=RecoveryState.IN_PROGRESS, priority=RecoveryPriority.HIGH)
    invoice.promises_to_pay = [promise]
    assert evaluate_case(case, today).derived_state == RecoveryState.ESCALATED.value
