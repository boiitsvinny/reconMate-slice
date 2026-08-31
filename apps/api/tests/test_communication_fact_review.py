from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.intelligence.candidates import candidate_facts
from app.intelligence.evaluation import COMMUNICATION_EXTRACTION_EVALUATION, run_communication_extraction_evaluation
from app.intelligence.fact_review import review_candidate_fact
from app.api.routes.workflow import _safe_interpretation_failure
from app.intelligence.provider import MockCommunicationIntelligenceProvider, ProviderError, get_provider
from app.intelligence.schemas import CandidateDecision, CandidateFact, CommunicationAnalysisResult
from app.models.domain import (
    AnalysisReviewStatus,
    AIProcessingStatus,
    AuditEvent,
    Communication,
    CommunicationAnalysis,
    CommunicationChannel,
    CommunicationDirection,
    Customer,
    Invoice,
    InvoiceStatus,
    RecoveryCase,
    RecoveryPriority,
    RecoveryState,
)
from app.recommendations.service import recommend_case

OPERATING_DATE = date(2026, 8, 26)


class FakeSession:
    def __init__(self, prior=None):
        self.added = []
        self.prior = list(prior or [])
        self.commits = 0

    def scalars(self, _query):
        return list(self.prior)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    def commit(self):
        self.commits += 1


def _scope(message="We raised a dispute because the invoice quantity is wrong."):
    customer = Customer(id=uuid4(), name="AI Review Co", account_reference="AI-REVIEW", is_strategic_account=False)
    invoice = Invoice(
        id=uuid4(), customer=customer, customer_id=customer.id, invoice_number="AI-INV",
        issue_date=OPERATING_DATE - timedelta(days=70), due_date=OPERATING_DATE - timedelta(days=40),
        original_amount=Decimal("300000"), outstanding_amount=Decimal("300000"), status=InvoiceStatus.OVERDUE,
    )
    case = RecoveryCase(
        id=uuid4(), customer=customer, customer_id=customer.id, invoice=invoice, invoice_id=invoice.id,
        current_state=RecoveryState.IN_PROGRESS, priority=RecoveryPriority.HIGH,
    )
    communication = Communication(
        id=uuid4(), customer=customer, customer_id=customer.id, direction=CommunicationDirection.INBOUND,
        channel=CommunicationChannel.EMAIL, content=message,
        occurred_at=datetime(2026, 8, 25, 10, tzinfo=UTC),
    )
    result = MockCommunicationIntelligenceProvider().analyze(message, OPERATING_DATE)
    analysis = CommunicationAnalysis(
        id=uuid4(), communication=communication, communication_id=communication.id,
        provider="mock", model_version="deterministic-rules-v1", result=result.model_dump(mode="json"),
        confidence=Decimal("0.9300"), review_status=AnalysisReviewStatus.PENDING_REVIEW,
    )
    return customer, invoice, case, communication, analysis


def test_candidate_schema_is_typed_and_multiple_signals_are_preserved() -> None:
    message = "The invoice is disputed, but we will pay INR 10,000 on Friday."
    result = MockCommunicationIntelligenceProvider().analyze(message, date(2026, 8, 24))
    candidates = candidate_facts(message, result)
    assert {item.fact_type.value for item in candidates} == {"ACTIVE_DISPUTE", "PAYMENT_PROMISE"}
    assert all(CandidateFact.model_validate(item.model_dump()) for item in candidates)
    assert all(item.evidence_span and 0 <= item.confidence <= 1 for item in candidates)


def test_low_confidence_and_irrelevant_messages_defer_safely() -> None:
    provider = MockCommunicationIntelligenceProvider()
    ambiguous = candidate_facts("We will pay soon.", provider.analyze("We will pay soon.", OPERATING_DATE))
    irrelevant = candidate_facts("Please update our billing address.", provider.analyze("Please update our billing address.", OPERATING_DATE))
    assert ambiguous[0].fact_type.value == "PAYMENT_PROMISE" and not ambiguous[0].persistence_eligible
    assert irrelevant[0].fact_type.value == "UNKNOWN_NEEDS_REVIEW" and not irrelevant[0].persistence_eligible


def test_analysis_alone_cannot_mutate_finance_score_or_recommendation() -> None:
    _, invoice, case, _, _ = _scope()
    before = recommend_case(case, OPERATING_DATE)
    result = MockCommunicationIntelligenceProvider().analyze("We raised a dispute because quantity is wrong.", OPERATING_DATE)
    candidate_facts("We raised a dispute because quantity is wrong.", result)
    after = recommend_case(case, OPERATING_DATE)
    assert invoice.status is InvoiceStatus.OVERDUE
    assert invoice.outstanding_amount == Decimal("300000")
    assert before.recommended_action == after.recommended_action


def test_operator_acceptance_persists_fact_then_reassesses_without_financial_mutation(monkeypatch) -> None:
    _, invoice, case, communication, analysis = _scope()
    db = FakeSession()
    monkeypatch.setattr("app.intelligence.fact_review.synchronize_recovery_states", lambda *_args, **_kwargs: {"cases_evaluated": 1, "cases_changed": 1})
    response = review_candidate_fact(
        db, communication=communication, analysis=analysis, case=case, invoice=invoice,
        candidate_id="ACTIVE_DISPUTE:0", decision=CandidateDecision.ACCEPT,
        operator_id="operator-1", operating_date=OPERATING_DATE,
    )
    assert invoice.status is InvoiceStatus.DISPUTED
    assert invoice.outstanding_amount == Decimal("300000")
    assert response.persisted_fact == "Active dispute opened"
    assert response.financial_mutation == "NONE"
    assert response.recommendation_before != "HOLD_FOR_DISPUTE"
    assert response.recommendation_after == "HOLD_FOR_DISPUTE"
    assert response.blockers_before == [] and response.blockers_after == ["ACTIVE_DISPUTE"]
    assert analysis.review_status is AnalysisReviewStatus.NOT_REQUIRED
    events = [item for item in db.added if isinstance(item, AuditEvent)]
    assert [item.event_type for item in events] == [
        "AI_CANDIDATE_EXTRACTED", "AI_CANDIDATE_ACCEPTED", "DISPUTE_OPENED", "AI_FACT_INTELLIGENCE_REASSESSMENT",
    ]
    assert [item.occurred_at for item in events] == sorted(item.occurred_at for item in events)


def test_rejected_candidate_creates_no_operational_fact(monkeypatch) -> None:
    _, invoice, case, communication, analysis = _scope()
    db = FakeSession()
    monkeypatch.setattr("app.intelligence.fact_review.synchronize_recovery_states", lambda *_args, **_kwargs: {})
    response = review_candidate_fact(
        db, communication=communication, analysis=analysis, case=case, invoice=invoice,
        candidate_id="ACTIVE_DISPUTE:0", decision=CandidateDecision.REJECT,
        operator_id="operator-1", operating_date=OPERATING_DATE,
    )
    assert response.persisted_fact is None and response.score_before == response.score_after
    assert invoice.status is InvoiceStatus.OVERDUE and invoice.outstanding_amount == Decimal("300000")
    assert [item.event_type for item in db.added if isinstance(item, AuditEvent)] == ["AI_CANDIDATE_EXTRACTED", "AI_CANDIDATE_REJECTED"]


def test_unavailable_provider_fails_without_domain_mutation() -> None:
    _, invoice, case, _, _ = _scope()
    before = (invoice.status, invoice.outstanding_amount, recommend_case(case, OPERATING_DATE).recommended_action)
    with pytest.raises(ProviderError):
        get_provider("not-configured")
    assert (invoice.status, invoice.outstanding_amount, recommend_case(case, OPERATING_DATE).recommended_action) == before


def test_workspace_failure_reason_only_exposes_known_safe_provider_messages() -> None:
    _, _, _, communication, _ = _scope()
    communication.ai_processing_status = AIProcessingStatus.FAILED
    communication.ai_processing_metadata = {"error": "The live model timed out; no fact was written."}
    assert _safe_interpretation_failure(communication) == "The live model timed out; no fact was written."

    communication.ai_processing_metadata = {"error": "secret-looking untrusted provider payload"}
    assert _safe_interpretation_failure(communication) == "Interpretation provider failed; no fact was written."


def test_fixed_communication_extraction_evaluation() -> None:
    result = run_communication_extraction_evaluation()
    assert len(COMMUNICATION_EXTRACTION_EVALUATION) == 30
    assert result["provider"] == "mock" and result["runtime_mode"] == "MOCK / DEV MODE"
    assert result["total"] == 30 and result["exact"] == 30
    assert result["deferred"] == 12 and result["incorrect"] == 0
    assert result["provider_failures"] == 0 and result["schema_validation_failures"] == 0
    assert result["direct_financial_mutations"] == 0
    assert result["intent_classification"] == {"correct": 30, "total": 30, "accuracy": 1.0}
    assert result["amount_extraction"]["accuracy"] == 1.0
    assert result["promise_date_extraction"]["accuracy"] == 1.0
    assert result["dispute_recognition"]["accuracy"] == 1.0
    assert result["low_confidence_human_review"]["accuracy"] == 1.0
    assert result["unsupported_input_rejection"]["accuracy"] == 1.0
    assert len(result["evidence"]) == 30
    assert all(item["authoritative_state_mutation"] is False for item in result["evidence"])
