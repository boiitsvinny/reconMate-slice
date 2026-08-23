from datetime import date

import pytest

from app.intelligence.provider import MockCommunicationIntelligenceProvider, ProviderError, get_provider
from app.intelligence.schemas import CommunicationAnalysisResult, Intent


def test_payment_commitment_extraction_is_structured():
    result = MockCommunicationIntelligenceProvider().analyze("We will clear ₹2 lakh by Friday.", date(2026, 8, 1))
    assert result.intent is Intent.PAYMENT_COMMITMENT
    assert result.payment_commitments[0].amount == 200000
    assert result.payment_commitments[0].expected_date == date(2026, 8, 7)


def test_no_clear_commitment():
    result = MockCommunicationIntelligenceProvider().analyze("We are reviewing internally and will revert.")
    assert result.intent is Intent.NO_CLEAR_COMMITMENT
    assert result.payment_commitments == []


def test_dispute_requires_review():
    result = MockCommunicationIntelligenceProvider().analyze("We cannot approve this invoice until the delivery discrepancy is resolved.")
    assert result.dispute_signal.detected and result.requires_human_review
    assert "Possible dispute detected" in result.review_reasons


def test_ambiguous_commitment_requires_review():
    result = MockCommunicationIntelligenceProvider().analyze("We should be able to clear around ₹3 lakh by Friday.", date(2026, 8, 1))
    assert result.payment_commitments[0].ambiguous and result.requires_human_review


def test_paid_language_is_claim_not_fact():
    result = MockCommunicationIntelligenceProvider().analyze("Payment has been initiated and should reflect tomorrow.")
    assert result.intent is Intent.PAYMENT_COMPLETED_CLAIM
    assert result.payment_completed_claim.detected


def test_provider_failure_is_clear():
    with pytest.raises(ProviderError): get_provider("not-configured")


def test_schema_rejects_unknown_fields():
    with pytest.raises(Exception):
        CommunicationAnalysisResult.model_validate({"intent": "OTHER", "untrusted": True})


def test_mock_is_deterministic():
    provider = MockCommunicationIntelligenceProvider()
    assert provider.analyze("We will clear ₹2 lakh by Friday.", date(2026, 8, 1)) == provider.analyze("We will clear ₹2 lakh by Friday.", date(2026, 8, 1))
