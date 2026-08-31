from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.domain import (
    CommunicationConsentStatus, Customer, Invoice, InvoiceStatus, RecoveryAction,
    RecoveryCase, RecoveryPriority, RecoveryState,
)
from app.recommendations.schemas import RecommendedAction
from app.recommendations.service import recommend_case
from app.workflow.service import create_action, execute_action

SIM_DATE = date(2026, 8, 1)


class FakeSession:
    def __init__(self): self.added = []
    def add(self, item): self.added.append(item)
    def scalar(self, _query): return None
    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None: item.id = uuid4()
            if isinstance(item, RecoveryAction) and item.recovery_case_id is None: item.recovery_case_id = item.recovery_case.id
    def commit(self): pass
    def refresh(self, _item): pass


def _case(consent: CommunicationConsentStatus, channel: str | None = "EMAIL", *, status=InvoiceStatus.OVERDUE, outstanding="500"):
    customer = Customer(id=uuid4(), name="Consent Test", account_reference=f"CONSENT-{uuid4()}", communication_consent_status=consent, preferred_outreach_channel=channel)
    invoice = Invoice(id=uuid4(), customer=customer, invoice_number="CONSENT-1", issue_date=SIM_DATE - timedelta(days=40), due_date=SIM_DATE - timedelta(days=10), original_amount=Decimal("500"), outstanding_amount=Decimal(outstanding), status=status)
    return RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=RecoveryState.IN_PROGRESS, priority=RecoveryPriority.NORMAL)


def test_opted_out_customer_is_visibly_blocked_and_cannot_create_outreach() -> None:
    case = _case(CommunicationConsentStatus.OPTED_OUT)
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.SEND_PAYMENT_REMINDER
    assert "COMMUNICATION_OPTED_OUT" in recommendation.blockers
    assert recommendation.action_readiness.communication_permitted is False
    assert recommendation.action_readiness.external_execution == "BLOCKED"
    db = FakeSession()
    with pytest.raises(HTTPException, match="opted out"):
        create_action(db, case, SIM_DATE, RecommendedAction.SEND_PAYMENT_REMINDER)
    assert any(getattr(item, "event_type", None) == "RECOVERY_ACTION_READINESS_BLOCKED" for item in db.added)


def test_unknown_consent_and_missing_channel_fail_closed_to_human_review() -> None:
    recommendation = recommend_case(_case(CommunicationConsentStatus.UNKNOWN, None), SIM_DATE)
    assert {"COMMUNICATION_CONSENT_UNKNOWN", "COMMUNICATION_CHANNEL_UNAVAILABLE"}.issubset(recommendation.blockers)
    assert recommendation.human_approval_required is True
    assert recommendation.action_readiness.operator_approval == "REQUIRED"
    assert recommendation.action_readiness.external_execution == "BLOCKED"

    unsupported_channel = recommend_case(_case(CommunicationConsentStatus.OPTED_IN, "UNSUPPORTED"), SIM_DATE)
    assert "COMMUNICATION_CHANNEL_UNAVAILABLE" in unsupported_channel.blockers
    assert unsupported_channel.action_readiness.channel_available is False


def test_valid_consent_and_channel_continue_through_normal_policy() -> None:
    case = _case(CommunicationConsentStatus.OPTED_IN)
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.blockers == []
    assert recommendation.action_readiness.communication_permitted is True
    assert recommendation.action_readiness.channel_available is True
    assert recommendation.action_readiness.external_execution == "OPERATOR_CONTROLLED"
    db = FakeSession()
    action = create_action(db, case, SIM_DATE, RecommendedAction.SEND_PAYMENT_REMINDER)
    execute_action(db, action, case, SIM_DATE, "operator", None)
    assert action.status.value == "EXECUTED"


def test_consent_composes_without_replacing_financial_stopping_rules() -> None:
    recommendation = recommend_case(_case(CommunicationConsentStatus.OPTED_OUT, status=InvoiceStatus.DISPUTED), SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.HOLD_FOR_DISPUTE
    assert "ACTIVE_DISPUTE" in recommendation.blockers
    assert recommendation.action_readiness.communication_required is False
    assert recommendation.action_readiness.communication_permitted is False

    paid = recommend_case(_case(CommunicationConsentStatus.OPTED_IN, status=InvoiceStatus.PAID, outstanding="0"), SIM_DATE)
    assert paid.recommended_action is RecommendedAction.NO_ACTION_REQUIRED
    assert paid.action_readiness.financially_actionable is False
