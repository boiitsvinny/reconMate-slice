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


class PreviewRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    reference_date: date | None = None


class AnalysisResponse(BaseModel):
    analysis_id: str | None = None
    provider: str
    model_version: str | None = None
    analyzed_at: str | None = None
    result: CommunicationAnalysisResult
