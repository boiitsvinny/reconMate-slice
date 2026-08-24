"""Public contracts for deterministic operational portfolio intelligence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SignalType(str, Enum):
    HIGH_VALUE_OVERDUE = "HIGH_VALUE_OVERDUE"
    LONG_OVERDUE = "LONG_OVERDUE"
    MULTIPLE_OVERDUE_INVOICES = "MULTIPLE_OVERDUE_INVOICES"
    BROKEN_PROMISE = "BROKEN_PROMISE"
    MULTIPLE_BROKEN_PROMISES = "MULTIPLE_BROKEN_PROMISES"
    PAYMENT_ACTIVITY_STALLED = "PAYMENT_ACTIVITY_STALLED"
    ACTIVE_DISPUTE = "ACTIVE_DISPUTE"
    RECOVERY_STALLED = "RECOVERY_STALLED"
    HIGH_RECOVERY_EXPOSURE = "HIGH_RECOVERY_EXPOSURE"


class PriorityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendationAction(str, Enum):
    MONITOR = "MONITOR"
    FOLLOW_UP = "FOLLOW_UP"
    ESCALATE = "ESCALATE"
    REVIEW_DISPUTE = "REVIEW_DISPUTE"
    PRIORITIZE_RECOVERY = "PRIORITIZE_RECOVERY"
    WAIT_FOR_PROMISE = "WAIT_FOR_PROMISE"


class IntelligenceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SignalType
    severity: PriorityLevel
    title: str
    explanation: str
    contributing_value: Decimal | int | str | None = None
    calculated_at: date


class ContributingFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SignalType
    impact: PriorityLevel
    points: int = Field(ge=0, le=100)
    explanation: str
    contributing_value: Decimal | int | str | None = None


class IntelligenceRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: RecommendationAction
    title: str
    explanation: str
    priority_level: PriorityLevel
    operator_confirmation_required: bool


class IntelligenceMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_outstanding_amount: Decimal
    overdue_exposure: Decimal
    overdue_invoice_count: int
    max_days_overdue: int
    broken_promise_count: int
    active_promise_count: int
    active_dispute_count: int
    days_since_last_payment: int | None
    active_recovery_case_count: int
    stalled_recovery_case_count: int


class IntelligenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    entity_id: str
    entity_name: str
    calculated_at: date
    score: int = Field(ge=0, le=100)
    level: PriorityLevel
    metrics: IntelligenceMetrics
    signals: list[IntelligenceSignal]
    factors: list[ContributingFactor]
    recommendation: IntelligenceRecommendation


class PortfolioIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calculated_at: date
    customer_count: int
    average_score: Decimal
    level_counts: dict[PriorityLevel, int]
    highest_priority: list[IntelligenceResult]
    customers: list[IntelligenceResult]
