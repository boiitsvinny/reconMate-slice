from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.domain import (
    AnalysisReviewStatus, Communication, CommunicationAnalysis, CommunicationChannel,
    CommunicationDirection, Customer, Invoice, InvoiceStatus, PromiseStatus,
    PromiseToPay, RecoveryCase, RecoveryPriority, RecoveryState,
)
from app.recommendations.schemas import RecommendedAction, RecommendationPriority
from app.recommendations.service import recommend_case

SIM_DATE = date(2026, 8, 1)


def _case(*, outstanding="100", due_days=10, status=InvoiceStatus.OVERDUE, priority=RecoveryPriority.NORMAL, state=RecoveryState.IN_PROGRESS):
    customer = Customer(id=uuid4(), name="Recommendation Test", account_reference=f"REC-{uuid4()}")
    invoice = Invoice(id=uuid4(), customer=customer, invoice_number="REC-INV", issue_date=SIM_DATE - timedelta(days=40),
                      due_date=SIM_DATE - timedelta(days=due_days), original_amount=Decimal("1000"),
                      outstanding_amount=Decimal(outstanding), status=status)
    return RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=state, priority=priority)


def _analysis(case, *, intent="NO_CLEAR_COMMITMENT", claim=False, dispute=False, commitment=False, when=SIM_DATE - timedelta(days=2)):
    communication = Communication(id=uuid4(), customer=case.customer, direction=CommunicationDirection.INBOUND,
                                  channel=CommunicationChannel.EMAIL, content="Customer response", occurred_at=datetime.combine(when, datetime.min.time(), UTC))
    result = {
        "intent": intent, "payment_commitments": ([{"amount": "100", "currency": "INR", "expected_date": str(SIM_DATE + timedelta(days=4)), "confidence": 0.8}] if commitment else []),
        "conditions": [], "dispute_signal": {"detected": dispute, "confidence": 0.8},
        "payment_completed_claim": {"detected": claim, "confidence": 0.9},
        "sentiment": "NEUTRAL", "urgency": "NORMAL", "requires_human_review": False, "review_reasons": [],
    }
    analysis = CommunicationAnalysis(id=uuid4(), communication=communication, provider="mock", model_version="test",
                                     result=result, confidence=Decimal("0.9000"), review_status=AnalysisReviewStatus.NOT_REQUIRED)
    communication.ai_processing_metadata = {"accepted_analysis_ids": [str(analysis.id)]}
    case.customer.communications = [communication]
    communication.analyses = [analysis]


def _promise(case, promised_date):
    promise = PromiseToPay(id=uuid4(), customer=case.customer, invoice=case.invoice, promised_amount=Decimal("100"),
                           promised_date=promised_date, status=PromiseStatus.ACTIVE, confidence=Decimal("0.8"))
    case.invoice.promises_to_pay = [promise]


def test_active_promise_is_monitored() -> None:
    case = _case()
    _promise(case, SIM_DATE + timedelta(days=2))
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.MONITOR_ACTIVE_PROMISE
    assert recommendation.human_approval_required is False


def test_broken_promise_prepares_escalation() -> None:
    case = _case(due_days=10)
    _promise(case, SIM_DATE - timedelta(days=1))
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.PREPARE_ESCALATION
    assert "A recorded payment promise is broken." in recommendation.factual_reasons


def test_active_dispute_holds_recovery() -> None:
    case = _case(status=InvoiceStatus.DISPUTED)
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.HOLD_FOR_DISPUTE
    assert "ACTIVE_DISPUTE" in recommendation.blockers


def test_payment_completed_claim_requires_evidence_review() -> None:
    case = _case()
    _analysis(case, intent="PAYMENT_COMPLETED_CLAIM", claim=True)
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.REVIEW_PAYMENT_CLAIM
    assert recommendation.relevant_exposure == Decimal("100")


def test_no_clear_commitment_gets_reminder() -> None:
    case = _case(due_days=10)
    _analysis(case)
    assert recommend_case(case, SIM_DATE).recommended_action is RecommendedAction.SEND_PAYMENT_REMINDER


def test_severe_overdue_case_prepares_escalation() -> None:
    case = _case(outstanding="100", due_days=20, priority=RecoveryPriority.CRITICAL)
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.PREPARE_ESCALATION
    assert recommendation.priority is RecommendationPriority.CRITICAL


def test_paid_or_closed_case_requires_no_action() -> None:
    case = _case(outstanding="0", status=InvoiceStatus.PAID)
    assert recommend_case(case, SIM_DATE).recommended_action is RecommendedAction.NO_ACTION_REQUIRED


def test_intelligence_cannot_override_factual_dispute_blocker() -> None:
    case = _case(status=InvoiceStatus.DISPUTED)
    _analysis(case, intent="PAYMENT_COMPLETED_CLAIM", claim=True)
    recommendation = recommend_case(case, SIM_DATE)
    assert recommendation.recommended_action is RecommendedAction.HOLD_FOR_DISPUTE
    assert "ACTIVE_DISPUTE" in recommendation.blockers
