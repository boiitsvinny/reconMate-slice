"""The provider contract. Values here describe language, never established facts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Intent(str, Enum):
    PAYMENT_COMMITMENT = "PAYMENT_COMMITMENT"
    PAYMENT_DELAY = "PAYMENT_DELAY"
    PAYMENT_COMPLETED_CLAIM = "PAYMENT_COMPLETED_CLAIM"
    DISPUTE = "DISPUTE"
    INFORMATION_REQUEST = "INFORMATION_REQUEST"
    NEGOTIATION = "NEGOTIATION"
    REFUSAL = "REFUSAL"
    NO_CLEAR_COMMITMENT = "NO_CLEAR_COMMITMENT"
    OTHER = "OTHER"


class CandidateFactType(str, Enum):
    ACTIVE_DISPUTE = "ACTIVE_DISPUTE"
    PAYMENT_PROMISE = "PAYMENT_PROMISE"
    BROKEN_PROMISE = "BROKEN_PROMISE"
    CUSTOMER_DELAY_REASON = "CUSTOMER_DELAY_REASON"
    POSSIBLE_PAYMENT_CLAIM = "POSSIBLE_PAYMENT_CLAIM"
    UNKNOWN_NEEDS_REVIEW = "UNKNOWN_NEEDS_REVIEW"


class Sentiment(str, Enum):
    COOPERATIVE = "COOPERATIVE"
    NEUTRAL = "NEUTRAL"
    DEFENSIVE = "DEFENSIVE"
    FRUSTRATED = "FRUSTRATED"
    UNRESPONSIVE = "UNRESPONSIVE"


class Urgency(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class PaymentCommitment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    expected_date: date | None = None
    confidence: float = Field(ge=0, le=1)
    conditional: bool = False
    condition: str | None = None
    source_wording: str | None = None
    ambiguous: bool = False

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class DisputeSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detected: bool = False
    description: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class PaymentCompletedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detected: bool = False
    description: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    fact_type: CandidateFactType
    confidence: float = Field(ge=0, le=1)
    evidence_span: str = Field(min_length=1, max_length=500)
    proposed_data: dict[str, str | bool | None] = Field(default_factory=dict)
    persistence_eligible: bool
    defer_reason: str | None = None
    operator_confirmation_required: bool = True


class CommunicationAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    payment_commitments: list[PaymentCommitment] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    dispute_signal: DisputeSignal = Field(default_factory=DisputeSignal)
    payment_completed_claim: PaymentCompletedClaim = Field(default_factory=PaymentCompletedClaim)
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.NORMAL
    requires_human_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    candidates: list[CandidateFact] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    reference_date: date | None = None


class AnalysisResponse(BaseModel):
    analysis_id: str | None = None
    provider: str
    model_version: str | None = None
    analyzed_at: str | None = None
    runtime_mode: str
    result: CommunicationAnalysisResult
    candidates: list[CandidateFact] = Field(default_factory=list)


class CandidateDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class CandidateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    invoice_id: str
    candidate_id: str
    decision: CandidateDecision
    operator_id: str = Field(min_length=1, max_length=255)


class CandidateDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    candidate: CandidateFact
    decision: CandidateDecision
    operator_id: str
    persisted_fact: str | None
    score_before: int
    score_after: int
    blockers_before: list[str]
    blockers_after: list[str]
    recommendation_before: str
    recommendation_after: str
    financial_mutation: str = "NONE"
