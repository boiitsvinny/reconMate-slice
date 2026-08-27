"""Focused invariants for the deterministic simulation foundation."""
from datetime import UTC, date, datetime
from decimal import Decimal
import json
import logging
import random
from types import SimpleNamespace
from uuid import uuid4

from app.models.domain import Customer, Invoice, InvoiceStatus, PromiseStatus, PromiseToPay, RecoveryCase, RecoveryPriority, RecoveryState
from app.core.timing import log_timing
from app.recovery.engine import evaluate_case, evaluate_invoice
from app.seed.portfolio import reset_database
from app.simulation import service as simulation_service
from app.simulation.config import SCENARIO_CONFIG
from app.simulation.service import _available_event_kinds, _event_id, _fractional_amount, _promise_date, _roll_event_plan


def test_simulation_event_identity_is_repeatable() -> None:
    assert _event_id(9, 0) == _event_id(9, 0)
    assert _event_id(9, 0) != _event_id(10, 0)


def test_structured_timing_log_contains_only_supplied_operational_fields(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        log_timing("simulation_tick_timing", cycle=4, total_ms=321, events_generated=2)
    payload = json.loads(caplog.records[-1].message)
    assert payload == {
        "event": "simulation_tick_timing", "cycle": 4,
        "total_ms": 321, "events_generated": 2,
    }


def test_seeded_event_roll_is_reproducible_and_bounded() -> None:
    valid = ["PARTIAL_PAYMENT", "FULL_PAYMENT", "PROMISE_CREATED", "DISPUTE_OPENED", "CUSTOMER_DELAY_RESPONSE"]
    assert _roll_event_plan(random.Random(431), valid) == _roll_event_plan(random.Random(431), valid)
    rolls = [_roll_event_plan(random.Random(seed), valid) for seed in range(200)]
    assert all(primary in valid and 0 <= secondary <= 4 for primary, secondary in rolls)
    counts = [secondary for _, secondary in rolls]
    assert counts.count(1) + counts.count(2) > counts.count(3) + counts.count(4)
    assert 0 in counts and 4 in counts


def test_event_candidates_protect_settled_and_disputed_invoices() -> None:
    customer = Customer(id=uuid4(), name="Candidate Test", account_reference="SIM-CANDIDATE")
    paid = Invoice(id=uuid4(), customer=customer, invoice_number="PAID-1", issue_date=date(2026, 7, 1), due_date=date(2026, 7, 20), original_amount=Decimal("100"), outstanding_amount=Decimal("0"), status=InvoiceStatus.PAID)
    disputed = Invoice(id=uuid4(), customer=customer, invoice_number="DSP-1", issue_date=date(2026, 7, 1), due_date=date(2026, 7, 20), original_amount=Decimal("100"), outstanding_amount=Decimal("100"), status=InvoiceStatus.DISPUTED)
    assert _available_event_kinds([paid], [], set()) == []
    assert _available_event_kinds([disputed], [], set()) == ["DISPUTE_RESOLVED"]


def test_generated_monetary_and_promise_date_bounds() -> None:
    balance = Decimal("1000")
    amounts = [_fractional_amount(balance, random.Random(seed), SCENARIO_CONFIG.payment_fraction_min, SCENARIO_CONFIG.payment_fraction_max) for seed in range(30)]
    assert all(Decimal("0") < amount <= balance for amount in amounts)
    dates = [_promise_date(date(2026, 8, 1), random.Random(seed)) for seed in range(30)]
    assert all(SCENARIO_CONFIG.promise_days_min <= (value - date(2026, 8, 1)).days <= SCENARIO_CONFIG.promise_days_max for value in dates)


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


def test_material_transition_evidence_is_persisted_append_only() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.records = []
            self.commits = 0

        def add(self, record) -> None:
            self.records.append(record)

        def commit(self) -> None:
            self.commits += 1

    db = RecordingSession()
    entity_id = uuid4()
    state = SimpleNamespace(id=uuid4(), simulation_date=date(2026, 8, 2))
    transition = {
        "entity_type": "CUSTOMER", "entity_id": str(entity_id), "entity_name": "Evidence Account",
        "previous_score": 74, "current_score": 83, "previous_recommendation": "MONITOR",
        "current_recommendation": "PRIORITIZE", "classifications": ["RECOMMENDATION_CHANGED"],
        "material": True,
    }
    simulation_service._persist_transition_audits(  # type: ignore[arg-type]
        db, state, 4, 3, [transition],
        {"customers_affected": 2, "material_customers": 1, "recommendations_changed": 1, "recommendations_unchanged": 0},
    )
    assert [record.event_type for record in db.records] == ["SIMULATION_INTELLIGENCE_SUMMARY", "SIMULATION_INTELLIGENCE_TRANSITION"]
    assert db.records[0].payload["event_count"] == 3
    assert db.records[1].payload["previous_score"] == 74
    assert db.records[1].payload["current_recommendation"] == "PRIORITIZE"
    assert db.commits == 1


def test_tick_defers_recovery_commit_until_transition_evidence_is_persisted(monkeypatch) -> None:
    calls: list[str] = []
    state = SimpleNamespace(id=uuid4(), name="default", cycle=3, simulation_date=date(2026, 8, 4))

    class Rows(list):
        def all(self):
            return self

    class FakeSession:
        def scalar(self, _statement):
            return state

        def scalars(self, _statement):
            return Rows()

        def flush(self):
            calls.append("flush")

    monkeypatch.setattr(simulation_service, "_capture_intelligence", lambda _db, _context, _date: {})
    monkeypatch.setattr(simulation_service, "_available_event_kinds", lambda *_args: ["PARTIAL_PAYMENT"])
    monkeypatch.setattr(simulation_service, "_roll_event_plan", lambda *_args: ("PARTIAL_PAYMENT", 0))
    monkeypatch.setattr(simulation_service, "_apply_generated_event", lambda *_args: {
        "id": str(uuid4()), "type": "PARTIAL_PAYMENT", "customer_id": None,
        "invoice_id": None, "case_id": None, "metadata": {"family": "PAYMENT"},
        "cycle": state.cycle, "occurred_at": datetime(2026, 8, 5, tzinfo=UTC),
    })
    monkeypatch.setattr(simulation_service, "synchronize_recovery_states", lambda _db, _date, *, commit, **_kwargs: calls.append(f"sync_commit:{commit}") or {"cases_evaluated": 0, "cases_changed": 0})
    monkeypatch.setattr(simulation_service, "_build_transitions", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(simulation_service, "_dashboard_snapshot", lambda *_args: {})
    monkeypatch.setattr(simulation_service, "_persist_transition_audits", lambda *_args: calls.append("transition_commit"))

    result = simulation_service.run_tick(FakeSession(), seed=99)  # type: ignore[arg-type]
    assert result["cycle"] == 4
    assert "sync_commit:False" in calls
    assert calls[-1] == "transition_commit"


def test_cycle_dashboard_snapshot_reuses_current_factual_graph() -> None:
    customer = Customer(id=uuid4(), name="Snapshot Test", account_reference="SNAPSHOT-1")
    invoice = Invoice(
        id=uuid4(), customer=customer, invoice_number="SNAP-1",
        issue_date=date(2026, 7, 1), due_date=date(2026, 7, 20),
        original_amount=Decimal("1000"), outstanding_amount=Decimal("700"),
        status=InvoiceStatus.OVERDUE,
    )
    RecoveryCase(
        id=uuid4(), customer=customer, invoice=invoice,
        current_state=RecoveryState.IN_PROGRESS, priority=RecoveryPriority.NORMAL,
    )
    context = simulation_service._context_from_customers([customer])
    intelligence = simulation_service.evaluate_portfolio_intelligence([customer], date(2026, 8, 5))

    snapshot = simulation_service._dashboard_snapshot(context, date(2026, 8, 5), intelligence)

    assert snapshot["portfolio"]["total_outstanding_amount"] == Decimal("700")
    assert snapshot["portfolio"]["total_recovered_amount"] == Decimal("300")
    assert snapshot["recovery"]["overdue_exposure"] == Decimal("700")
    assert snapshot["intelligence"]["customers"][0]["entity_id"] == str(customer.id)


def test_latest_intelligence_cycle_returns_persisted_decision_evidence() -> None:
    customer_id = uuid4()
    transition = SimpleNamespace(
        event_type="SIMULATION_INTELLIGENCE_TRANSITION",
        payload={"cycle": 7, "entity_type": "CUSTOMER", "entity_id": str(customer_id), "material": True},
    )
    summary = SimpleNamespace(
        event_type="SIMULATION_INTELLIGENCE_SUMMARY",
        payload={"cycle": 7, "customers_affected": 1, "material_customers": 1, "recommendations_changed": 1, "recommendations_unchanged": 0, "blockers_added": 2, "blockers_removed": 1},
    )
    events = [SimpleNamespace(customer_id=customer_id), SimpleNamespace(customer_id=customer_id)]

    class Rows(list):
        def all(self):
            return self

    class EvidenceSession:
        def __init__(self) -> None:
            self.results = iter((Rows(events), Rows([summary, transition])))

        def scalar(self, _statement):
            return 7

        def scalars(self, _statement):
            return next(self.results)

    result = simulation_service.latest_intelligence_cycle(EvidenceSession())  # type: ignore[arg-type]
    assert result == {
        "cycle": 7, "event_count": 2, "customers_affected": 1,
        "material_customers": 1, "recommendations_changed": 1,
        "recommendations_unchanged": 0, "blockers_added": 2,
        "blockers_removed": 1, "transitions": [transition.payload],
    }


def test_simulation_reset_reseeds_and_clears_command_plans(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSession:
        def scalar(self, _statement):
            calls.append("locked")
            return object()

    monkeypatch.setattr(simulation_service, "seed_database", lambda _db, reset: calls.append(f"seed:{reset}") or {"customers": 84})
    monkeypatch.setattr(simulation_service, "simulation_state", lambda _db: {"cycle": 0, "simulation_date": "2026-08-01"})
    monkeypatch.setattr("app.commands.service.PLAN_REGISTRY.clear", lambda: calls.append("plans-cleared"))

    result = simulation_service.reset_simulation(FakeSession())  # type: ignore[arg-type]
    assert result["state"]["cycle"] == 0
    assert calls == ["locked", "seed:True", "plans-cleared"]
