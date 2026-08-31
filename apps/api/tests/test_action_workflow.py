from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.domain import (
    Customer, Invoice, InvoiceStatus, PromiseStatus, PromiseToPay, RecoveryAction,
    RecoveryActionStatus, RecoveryActionType, RecoveryCase, RecoveryPriority, RecoveryState,
)
from app.recommendations.schemas import RecommendedAction
from app.workflow.service import approve_action, create_action, execute_action, hold_action, reject_action

SIM_DATE = date(2026, 8, 1)


class FakeSession:
    def __init__(self): self.added = []
    def add(self, item): self.added.append(item)
    def scalar(self, _query): return None
    def get(self, model, identity): return next((item for item in self.added if isinstance(item, model) and item.id == identity), None)
    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None: item.id = uuid4()
            if isinstance(item, RecoveryAction) and item.recovery_case_id is None: item.recovery_case_id = item.recovery_case.id
    def commit(self): pass
    def refresh(self, _item): pass


def _case(*, strategic=False, invoice_status=InvoiceStatus.OVERDUE, outstanding="500", closed=False):
    customer = Customer(id=uuid4(), name="Workflow Test", account_reference=f"WF-{uuid4()}", is_strategic_account=strategic)
    invoice = Invoice(id=uuid4(), customer=customer, invoice_number="WF-1", issue_date=SIM_DATE - timedelta(days=40), due_date=SIM_DATE - timedelta(days=10), original_amount=Decimal("500"), outstanding_amount=Decimal(outstanding), status=invoice_status)
    return RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=RecoveryState.CLOSED if closed else RecoveryState.IN_PROGRESS, priority=RecoveryPriority.NORMAL)


def _active_promise(case):
    case.invoice.promises_to_pay = [PromiseToPay(id=uuid4(), customer=case.customer, invoice=case.invoice, promised_amount=Decimal("100"), promised_date=SIM_DATE + timedelta(days=3), status=PromiseStatus.ACTIVE)]


def _create(case, expected=None): return create_action(FakeSession(), case, SIM_DATE, expected)


def test_recommendation_becomes_persisted_action_with_snapshot_and_audit() -> None:
    db = FakeSession(); action = create_action(db, _case(), SIM_DATE, RecommendedAction.SEND_PAYMENT_REMINDER)
    assert action.status is RecoveryActionStatus.RECOMMENDED
    assert action.recommendation_context["recommended_action"] == "SEND_PAYMENT_REMINDER"
    assert any(getattr(event, "event_type", None) == "RECOVERY_ACTION_RECOMMENDED" for event in db.added)


def test_command_confirmation_identity_returns_original_workflow_action() -> None:
    db = FakeSession(); case = _case(); identity = uuid4()
    first = create_action(db, case, SIM_DATE, RecommendedAction.SEND_PAYMENT_REMINDER, idempotency_id=identity)
    repeated = create_action(db, case, SIM_DATE, RecommendedAction.SEND_PAYMENT_REMINDER, idempotency_id=identity)
    assert repeated is first
    assert len([item for item in db.added if isinstance(item, RecoveryAction)]) == 1


def test_approval_required_action_cannot_execute_before_approval() -> None:
    case = _case(strategic=True); _active_promise(case); action = _create(case, RecommendedAction.MONITOR_ACTIVE_PROMISE)
    with pytest.raises(HTTPException, match="Human approval"):
        execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)


def test_approved_action_can_execute_simulated_work() -> None:
    case = _case(strategic=True); _active_promise(case); db = FakeSession(); action = create_action(db, case, SIM_DATE, RecommendedAction.MONITOR_ACTIVE_PROMISE)
    approve_action(db, action, "operator", "Reviewed", None)
    execute_action(db, action, case, SIM_DATE, "operator", "Simulate monitoring")
    assert action.status is RecoveryActionStatus.EXECUTED
    assert action.executed_at is not None


def test_rejected_action_cannot_execute() -> None:
    case = _case(); action = _create(case)
    reject_action(FakeSession(), action, "operator", "Not appropriate", None)
    with pytest.raises(HTTPException, match="REJECTED"):
        execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)


def test_held_action_cannot_execute() -> None:
    case = _case(); action = _create(case)
    hold_action(FakeSession(), action, "operator", "Awaiting documents", None)
    with pytest.raises(HTTPException, match="HELD"):
        execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)


def test_dispute_blocks_unsafe_preexisting_outreach_execution() -> None:
    case = _case(invoice_status=InvoiceStatus.DISPUTED); action = RecoveryAction(id=uuid4(), recovery_case=case, recovery_case_id=case.id, action_type=RecoveryActionType.OUTREACH, status=RecoveryActionStatus.RECOMMENDED, recommendation_action=RecommendedAction.SEND_PAYMENT_REMINDER.value, human_approval_required=False)
    with pytest.raises(HTTPException, match="active dispute"):
        execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)


def test_paid_or_closed_case_prevents_execution() -> None:
    case = _case(invoice_status=InvoiceStatus.PAID, outstanding="0"); action = RecoveryAction(id=uuid4(), recovery_case=case, recovery_case_id=case.id, action_type=RecoveryActionType.OUTREACH, status=RecoveryActionStatus.RECOMMENDED, recommendation_action=RecommendedAction.SEND_PAYMENT_REMINDER.value, human_approval_required=False)
    with pytest.raises(HTTPException, match="no executable action"):
        execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)


def test_duplicate_execution_is_prevented() -> None:
    case = _case(); action = _create(case)
    execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)
    with pytest.raises(HTTPException, match="already executed"):
        execute_action(FakeSession(), action, case, SIM_DATE, "operator", None)


def test_stale_expected_recommendation_is_rejected() -> None:
    with pytest.raises(HTTPException, match="stale"):
        create_action(FakeSession(), _case(), SIM_DATE, RecommendedAction.MONITOR_ACTIVE_PROMISE)


def test_previously_created_action_is_blocked_when_current_recommendation_changes() -> None:
    case = _case()
    db = FakeSession()
    action = create_action(db, case, SIM_DATE, RecommendedAction.SEND_PAYMENT_REMINDER)
    _active_promise(case)
    with pytest.raises(HTTPException, match="Recommendation is stale"):
        execute_action(db, action, case, SIM_DATE, "operator", None)
    assert action.status is RecoveryActionStatus.RECOMMENDED
