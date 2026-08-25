"""Strongly typed contracts for the ReconMate command pipeline."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.operational_schemas import IntelligenceResult, PriorityLevel


class CommandIntentType(str, Enum):
    PORTFOLIO_ANALYSIS = "PORTFOLIO_ANALYSIS"
    CUSTOMER_ANALYSIS = "CUSTOMER_ANALYSIS"
    CASE_ANALYSIS = "CASE_ANALYSIS"
    PRIORITIZE_CASES = "PRIORITIZE_CASES"
    PREPARE_FOLLOW_UPS = "PREPARE_FOLLOW_UPS"
    PREPARE_RECOVERY_ACTIONS = "PREPARE_RECOVERY_ACTIONS"
    PREPARE_PAYMENT_REMINDERS = "PREPARE_PAYMENT_REMINDERS"
    EXPLAIN_RECOMMENDATION = "EXPLAIN_RECOMMENDATION"
    REVIEW_BROKEN_PROMISES = "REVIEW_BROKEN_PROMISES"
    UNKNOWN = "UNKNOWN"


class CommandScope(str, Enum):
    PORTFOLIO = "PORTFOLIO"
    CUSTOMER = "CUSTOMER"
    CASE = "CASE"


class ExecutionMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    PREPARE = "PREPARE"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    EXECUTED = "EXECUTED"


class ProposalActionType(str, Enum):
    ANALYZE_PORTFOLIO = "ANALYZE_PORTFOLIO"
    ANALYZE_CUSTOMER = "ANALYZE_CUSTOMER"
    ANALYZE_CASE = "ANALYZE_CASE"
    REVIEW_CUSTOMER = "REVIEW_CUSTOMER"
    REVIEW_CASE = "REVIEW_CASE"
    REVIEW_DISPUTE = "REVIEW_DISPUTE"
    MONITOR_PROMISE = "MONITOR_PROMISE"
    PREPARE_FOLLOW_UP = "PREPARE_FOLLOW_UP"
    PREPARE_RECOVERY_ACTION = "PREPARE_RECOVERY_ACTION"
    DRAFT_PAYMENT_REMINDER = "DRAFT_PAYMENT_REMINDER"


class ProposalStatus(str, Enum):
    ANALYZED = "ANALYZED"
    PREPARED = "PREPARED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTED = "EXECUTED"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"
    FAILED = "FAILED"


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=2_000)
    context_customer_id: UUID | None = None
    context_case_id: UUID | None = None


class CommandFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_n: int | None = Field(default=None, ge=1, le=50)
    risk_levels: list[PriorityLevel] = Field(default_factory=list)
    overdue_only: bool = False
    broken_promises_only: bool = False
    include_all: bool = False


class CommandIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: CommandIntentType
    confidence: float = Field(ge=0, le=1)
    scope: CommandScope
    filters: CommandFilters = Field(default_factory=CommandFilters)
    reasoning: list[str] = Field(default_factory=list)
    guidance: str | None = None


class EntityReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    entity_id: str
    display_name: str


class ReminderInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str
    outstanding_amount: Decimal
    due_date: date
    days_overdue: int


class ReminderArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    customer_name: str
    account_reference: str
    invoices: list[ReminderInvoice]
    total_outstanding: Decimal
    promise_state: str
    dispute_state: str
    intended_channel: str
    purpose: str
    tone: str
    prepared_at: datetime
    body: str | None = None
    reason: str


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    action_type: ProposalActionType
    target_type: str
    target_id: str
    title: str
    explanation: str
    priority: PriorityLevel
    risk_level: PriorityLevel
    execution_mode: ExecutionMode
    executable: bool
    requires_confirmation: bool
    workflow_recommendation_action: str | None = None
    reminder_artifact: ReminderArtifact | None = None
    limitations: list[str] = Field(default_factory=list)


class CommandPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    created_at: datetime
    expires_at: datetime | None = None
    intent: CommandIntentType
    entities: list[EntityReference]
    filters: CommandFilters
    reasoning: list[str]
    proposed_actions: list[ActionProposal]
    requires_confirmation: bool
    execution_mode: ExecutionMode


class ActionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    status: ProposalStatus
    message: str
    recovery_action_id: str | None = None
    recovery_action_status: str | None = None
    recovery_action_created_at: datetime | None = None
    workflow_effect: str | None = None


class CommandAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    interpreted_intent: CommandIntentType
    timestamp: datetime
    proposal_count: int
    execution_status: ExecutionMode


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    interpreted_intent: CommandIntent
    understanding_summary: str
    analyzed_entities: list[IntelligenceResult]
    plan: CommandPlan
    outcomes: list[ActionOutcome]
    warnings: list[str]
    limitations: list[str]
    audit: CommandAudit


class ConfirmCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(min_length=1, max_length=255)
    proposal_ids: list[UUID] | None = None
    note: str | None = Field(default=None, max_length=2_000)


class CommandConfirmationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    execution_mode: ExecutionMode
    outcomes: list[ActionOutcome]
    warnings: list[str]
    audit: CommandAudit
