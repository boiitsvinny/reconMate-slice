"""Typed candidate facts derived from provider interpretation, never policy decisions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.intelligence.schemas import (
    CandidateFact,
    CandidateFactType,
    CommunicationAnalysisResult,
    DisputeSignal,
    Intent,
    PaymentCommitment,
    PaymentCompletedClaim,
)


class CandidateValidationError(ValueError):
    """Raised when untrusted provider output is not safely source-grounded."""


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def normalize_candidate_facts(
    content: str,
    candidates: list[CandidateFact],
    *,
    confidence_threshold: float,
) -> list[CandidateFact]:
    """Validate, ground, de-duplicate, and assign server-owned eligibility."""
    source = _normalized(content)
    if not source:
        raise CandidateValidationError("The source communication is empty.")
    strongest: dict[CandidateFactType, CandidateFact] = {}
    for supplied in candidates:
        evidence = supplied.evidence_span.strip()
        if not evidence or _normalized(evidence) not in source:
            raise CandidateValidationError("A candidate evidence span was not found in the source communication.")
        data = dict(supplied.proposed_data)
        eligible = supplied.confidence >= confidence_threshold
        reason: str | None = None
        if supplied.fact_type is CandidateFactType.PAYMENT_PROMISE:
            try:
                amount = Decimal(str(data.get("amount") or "0"))
            except InvalidOperation as exc:
                raise CandidateValidationError("A payment-promise amount was not parseable.") from exc
            promised_date = data.get("promised_date")
            try:
                date.fromisoformat(promised_date) if isinstance(promised_date, str) else None
            except ValueError as exc:
                raise CandidateValidationError("A payment-promise date was not ISO-8601 parseable.") from exc
            eligible = eligible and amount > 0 and isinstance(promised_date, str) and not bool(data.get("conditional"))
            if not eligible:
                reason = "A precise positive amount, ISO date, non-conditional wording, and sufficient confidence are required."
        elif supplied.fact_type is CandidateFactType.UNKNOWN_NEEDS_REVIEW:
            eligible = False
            reason = supplied.defer_reason or "No supported operational fact could be extracted safely."
        elif not eligible:
            reason = "Confidence is below the configured operator-acceptance threshold."
        candidate = CandidateFact(
            candidate_id=f"{supplied.fact_type.value}:0",
            fact_type=supplied.fact_type,
            confidence=supplied.confidence,
            evidence_span=evidence,
            proposed_data=data,
            persistence_eligible=eligible,
            defer_reason=reason,
            operator_confirmation_required=True,
        )
        current = strongest.get(candidate.fact_type)
        if current is not None and current.proposed_data != candidate.proposed_data:
            preferred = candidate if candidate.confidence > current.confidence else current
            strongest[candidate.fact_type] = preferred.model_copy(update={
                "persistence_eligible": False,
                "defer_reason": "Conflicting candidates of the same type require manual review.",
            })
        elif current is None or candidate.confidence > current.confidence:
            strongest[candidate.fact_type] = candidate
    if not strongest:
        raise CandidateValidationError("The provider returned no candidate facts.")
    if len(strongest) > 1:
        strongest.pop(CandidateFactType.UNKNOWN_NEEDS_REVIEW, None)
    return list(strongest.values())


def analysis_from_candidates(candidates: list[CandidateFact]) -> CommunicationAnalysisResult:
    """Map extracted language facts into the legacy interpretation summary only."""
    types = {candidate.fact_type for candidate in candidates}
    if CandidateFactType.ACTIVE_DISPUTE in types:
        intent = Intent.DISPUTE
    elif CandidateFactType.POSSIBLE_PAYMENT_CLAIM in types:
        intent = Intent.PAYMENT_COMPLETED_CLAIM
    elif CandidateFactType.PAYMENT_PROMISE in types:
        intent = Intent.PAYMENT_COMMITMENT
    elif CandidateFactType.CUSTOMER_DELAY_REASON in types:
        intent = Intent.PAYMENT_DELAY
    else:
        intent = Intent.NO_CLEAR_COMMITMENT
    promises = []
    for candidate in candidates:
        if candidate.fact_type is not CandidateFactType.PAYMENT_PROMISE:
            continue
        data = candidate.proposed_data
        promised_date = data.get("promised_date")
        promises.append(PaymentCommitment(
            amount=Decimal(str(data["amount"])) if data.get("amount") else None,
            currency=str(data["currency"]) if data.get("currency") else None,
            expected_date=date.fromisoformat(promised_date) if isinstance(promised_date, str) else None,
            confidence=candidate.confidence,
            conditional=bool(data.get("conditional")),
            source_wording=candidate.evidence_span,
            ambiguous=not candidate.persistence_eligible,
        ))
    dispute = next((item for item in candidates if item.fact_type is CandidateFactType.ACTIVE_DISPUTE), None)
    claim = next((item for item in candidates if item.fact_type is CandidateFactType.POSSIBLE_PAYMENT_CLAIM), None)
    return CommunicationAnalysisResult(
        intent=intent,
        payment_commitments=promises,
        dispute_signal=DisputeSignal(
            detected=dispute is not None,
            description="Customer communication contains a candidate active dispute." if dispute else None,
            confidence=dispute.confidence if dispute else 0,
        ),
        payment_completed_claim=PaymentCompletedClaim(
            detected=claim is not None,
            description="Customer communication contains an unverified payment claim." if claim else None,
            confidence=claim.confidence if claim else 0,
        ),
        requires_human_review=True,
        review_reasons=["Model-extracted candidates require explicit operator confirmation."],
        candidates=candidates,
    )


def _span(content: str, terms: tuple[str, ...]) -> str:
    lower = content.lower()
    for term in terms:
        index = lower.find(term)
        if index >= 0:
            start = max(0, index - 40)
            end = min(len(content), index + len(term) + 60)
            return content[start:end].strip()
    return content.strip()[:160]


def candidate_facts(content: str, result: CommunicationAnalysisResult) -> list[CandidateFact]:
    if result.candidates:
        return result.candidates
    candidates: list[CandidateFact] = []
    if result.dispute_signal.detected:
        candidates.append(CandidateFact(
            candidate_id="ACTIVE_DISPUTE:0", fact_type=CandidateFactType.ACTIVE_DISPUTE,
            confidence=result.dispute_signal.confidence,
            evidence_span=_span(content, ("raised a dispute", "dispute", "quantity is wrong", "quantity", "delivery discrepancy", "cannot approve")),
            proposed_data={"status": "DISPUTED"}, persistence_eligible=result.dispute_signal.confidence >= 0.7,
            defer_reason=None if result.dispute_signal.confidence >= 0.7 else "Confidence is below the operator-review threshold.",
        ))
    for index, commitment in enumerate(result.payment_commitments):
        eligible = bool(commitment.amount and commitment.amount > 0 and commitment.expected_date and commitment.confidence >= 0.7 and not commitment.ambiguous)
        candidates.append(CandidateFact(
            candidate_id=f"PAYMENT_PROMISE:{index}", fact_type=CandidateFactType.PAYMENT_PROMISE,
            confidence=commitment.confidence,
            evidence_span=_span(content, ("will pay", "will clear", "can release", "can make", "clear by", "payment schedule")),
            proposed_data={
                "amount": str(commitment.amount) if commitment.amount is not None else None,
                "currency": commitment.currency,
                "promised_date": str(commitment.expected_date) if commitment.expected_date else None,
                "conditional": commitment.conditional,
            },
            persistence_eligible=eligible,
            defer_reason=None if eligible else "A precise positive amount, date, and sufficient confidence are required.",
        ))
    lower = content.lower()
    broken_terms = ("cannot keep our promise", "can't keep our promise", "missed the promised date", "promise has been missed", "will not meet the promise")
    if any(term in lower for term in broken_terms):
        candidates.append(CandidateFact(
            candidate_id="BROKEN_PROMISE:0", fact_type=CandidateFactType.BROKEN_PROMISE,
            confidence=0.86, evidence_span=_span(content, broken_terms), proposed_data={},
            persistence_eligible=True,
        ))
    if result.intent is Intent.PAYMENT_DELAY:
        candidates.append(CandidateFact(
            candidate_id="CUSTOMER_DELAY_REASON:0", fact_type=CandidateFactType.CUSTOMER_DELAY_REASON,
            confidence=0.78, evidence_span=_span(content, ("approval is pending", "approval pending", "delayed", "additional time", "cash-flow", "month-end")),
            proposed_data={"reason": content.strip()[:500]}, persistence_eligible=True,
        ))
    if result.payment_completed_claim.detected:
        candidates.append(CandidateFact(
            candidate_id="POSSIBLE_PAYMENT_CLAIM:0", fact_type=CandidateFactType.POSSIBLE_PAYMENT_CLAIM,
            confidence=result.payment_completed_claim.confidence,
            evidence_span=_span(content, ("already paid", "paid part", "payment has been", "we have paid", "processed")),
            proposed_data={"requires_payment_verification": True}, persistence_eligible=True,
        ))
    if not candidates:
        candidates.append(CandidateFact(
            candidate_id="UNKNOWN_NEEDS_REVIEW:0", fact_type=CandidateFactType.UNKNOWN_NEEDS_REVIEW,
            confidence=0.0, evidence_span=content.strip()[:160], proposed_data={}, persistence_eligible=False,
            defer_reason="No supported operational fact could be extracted safely.",
        ))
    return candidates
