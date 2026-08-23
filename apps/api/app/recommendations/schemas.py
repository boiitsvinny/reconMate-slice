"""Bounded API contracts for operator-facing recovery recommendations."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict


class RecommendedAction(str, Enum):
    SEND_PAYMENT_REMINDER = "SEND_PAYMENT_REMINDER"
    MONITOR_ACTIVE_PROMISE = "MONITOR_ACTIVE_PROMISE"
    REQUEST_PAYMENT_DATE = "REQUEST_PAYMENT_DATE"
    REVIEW_PAYMENT_CLAIM = "REVIEW_PAYMENT_CLAIM"
    HOLD_FOR_DISPUTE = "HOLD_FOR_DISPUTE"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    PREPARE_ESCALATION = "PREPARE_ESCALATION"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"


class RecommendationPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CommunicationSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    communication_id: str
    intent: str
    occurred_at: str
    confidence: Decimal | None = None
    payment_completed_claim: bool = False
    dispute_detected: bool = False
    has_payment_commitment: bool = False
    requires_human_review: bool = False


class RecoveryRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_id: str
    customer_name: str
    recommended_action: RecommendedAction
    priority: RecommendationPriority
    human_approval_required: bool
    factual_reasons: list[str]
    communication_signals: list[CommunicationSignal]
    blockers: list[str]
    relevant_exposure: Decimal
    relevant_days_overdue: int
    recovery_state: str
    operator_explanation: str
