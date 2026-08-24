"""Focused invariants for the deterministic simulation foundation."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.domain import Customer, Invoice, InvoiceStatus, PromiseStatus, PromiseToPay, RecoveryCase, RecoveryPriority, RecoveryState
from app.recovery.engine import evaluate_case, evaluate_invoice
from app.seed.portfolio import reset_database
from app.simulation import service as simulation_service
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


def test_seed_reset_deletes_simulation_events_with_domain_records() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.tables: list[str] = []

        def execute(self, statement) -> None:
            self.tables.append(statement.table.name)

        def flush(self) -> None:
            pass

    session = RecordingSession()
    reset_database(session)  # type: ignore[arg-type]
    assert session.tables[0] == "simulation_events"
    assert "simulation_states" in session.tables


def test_simulation_reset_reseeds_and_clears_command_plans(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSession:
        def scalar(self, _statement):
            calls.append("locked")
            return object()

    monkeypatch.setattr(simulation_service, "seed_database", lambda _db, reset: calls.append(f"seed:{reset}") or {"customers": 56})
    monkeypatch.setattr(simulation_service, "simulation_state", lambda _db: {"cycle": 0, "simulation_date": "2026-08-01"})
    monkeypatch.setattr("app.commands.service.PLAN_REGISTRY.clear", lambda: calls.append("plans-cleared"))

    result = simulation_service.reset_simulation(FakeSession())  # type: ignore[arg-type]
    assert result["state"]["cycle"] == 0
    assert calls == ["locked", "seed:True", "plans-cleared"]
