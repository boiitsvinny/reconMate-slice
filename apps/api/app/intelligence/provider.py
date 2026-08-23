from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal
import re

from app.intelligence.schemas import (CommunicationAnalysisResult, DisputeSignal, Intent, PaymentCommitment,
    PaymentCompletedClaim, Sentiment, Urgency)


class ProviderError(RuntimeError):
    pass


class CommunicationIntelligenceProvider(ABC):
    name: str
    model_version: str | None = None

    @abstractmethod
    def analyze(self, content: str, reference_date: date | None = None) -> CommunicationAnalysisResult: ...


class MockCommunicationIntelligenceProvider(CommunicationIntelligenceProvider):
    """Deterministic rules for demos/tests; no network or API key is involved."""
    name = "mock"
    model_version = "deterministic-rules-v1"

    def analyze(self, content: str, reference_date: date | None = None) -> CommunicationAnalysisResult:
        text = content.strip()
        lower = text.lower()
        reference_date = reference_date or date.today()
        dispute_terms = ("dispute", "delivery issue", "delivery discrepancy", "cannot approve", "quantities are checked")
        dispute = next((term for term in dispute_terms if term in lower), None)
        paid_terms = ("payment has been initiated", "payment has been made", "we have paid", "processed")
        claim = next((term for term in paid_terms if term in lower), None)
        amounts = re.findall(r"(?:₹|rs\.?|inr\s*)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lakhs|l)?", lower, re.I)
        amount: Decimal | None = None
        if amounts:
            number, unit = amounts[0]
            amount = Decimal(number.replace(",", "")) * (Decimal("100000") if unit else Decimal("1"))
        friday = "friday" in lower
        next_tuesday = "next tuesday" in lower
        expected = reference_date + timedelta(days=(4 - reference_date.weekday()) % 7 or 7) if friday else (reference_date + timedelta(days=(8 - reference_date.weekday()) % 7) if next_tuesday else None)
        commitment_words = ("will clear", "can release", "can make", "clear around", "clear by", "payment schedule")
        commitment_found = any(word in lower for word in commitment_words)
        conditional = any(word in lower for word in ("depends on", "until", "subject to", "if "))
        conditions = ["Payment depends on delivery issue resolution"] if "depends on the delivery issue" in lower else ([] if not conditional else ["Commitment is conditional"])
        ambiguous = commitment_found and (amount is None or expected is None or "should be able" in lower or "around" in lower)
        commitments = []
        if commitment_found:
            commitments = [PaymentCommitment(amount=amount, currency="INR" if amount is not None else None,
                expected_date=expected, confidence=0.62 if ambiguous else 0.91, conditional=conditional,
                condition=conditions[0] if conditions else None, source_wording=text, ambiguous=ambiguous)]
        if dispute:
            intent = Intent.DISPUTE if not commitment_found else Intent.PAYMENT_COMMITMENT
        elif claim:
            intent = Intent.PAYMENT_COMPLETED_CLAIM
        elif commitment_found:
            intent = Intent.PAYMENT_COMMITMENT
        elif any(word in lower for word in ("additional time", "cash-flow", "month-end", "unable to provide")):
            intent = Intent.PAYMENT_DELAY
        else:
            intent = Intent.NO_CLEAR_COMMITMENT
        reasons = []
        if dispute: reasons.append("Possible dispute detected")
        if ambiguous: reasons.append("Ambiguous payment amount or expected date")
        return CommunicationAnalysisResult(intent=intent, payment_commitments=commitments, conditions=conditions,
            dispute_signal=DisputeSignal(detected=bool(dispute), description="Customer raised a possible delivery or invoice issue" if dispute else None, confidence=0.93 if dispute else 0),
            payment_completed_claim=PaymentCompletedClaim(detected=bool(claim), description="Customer claims payment was initiated or processed" if claim else None, confidence=0.85 if claim else 0),
            sentiment=Sentiment.FRUSTRATED if dispute or "cash-flow" in lower else Sentiment.COOPERATIVE if commitment_found or claim else Sentiment.NEUTRAL,
            urgency=Urgency.HIGH if dispute or "urgent" in lower else Urgency.NORMAL,
            requires_human_review=bool(reasons), review_reasons=reasons)


def get_provider(name: str) -> CommunicationIntelligenceProvider:
    if name.lower() == "mock": return MockCommunicationIntelligenceProvider()
    raise ProviderError(f"AI provider '{name}' is not configured. Set AI_PROVIDER=mock or configure a supported provider.")
