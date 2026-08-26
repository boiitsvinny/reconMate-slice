"""Core relational model for B2B receivables recovery."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InvoiceStatus(str, enum.Enum):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    DISPUTED = "DISPUTED"
    WRITTEN_OFF = "WRITTEN_OFF"
    CANCELLED = "CANCELLED"


class PromiseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    BROKEN = "BROKEN"
    CANCELLED = "CANCELLED"


class CommunicationDirection(str, enum.Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class CommunicationChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    PORTAL = "PORTAL"
    LETTER = "LETTER"
    OTHER = "OTHER"


class AIProcessingStatus(str, enum.Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class AnalysisReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    NOT_REQUIRED = "NOT_REQUIRED"


class RecoveryState(str, enum.Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    PROMISE_MONITORING = "PROMISE_MONITORING"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class RecoveryPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecoveryActionType(str, enum.Enum):
    OUTREACH = "OUTREACH"
    FOLLOW_UP = "FOLLOW_UP"
    RECORD_PROMISE = "RECORD_PROMISE"
    ESCALATE = "ESCALATE"
    CLOSE_CASE = "CLOSE_CASE"
    NOTE = "NOTE"


class RecoveryActionStatus(str, enum.Enum):
    RECOMMENDED = "RECOMMENDED"
    PLANNED = "PLANNED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HELD = "HELD"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ApprovalStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    segment: Mapped[str | None] = mapped_column(String(100))
    is_strategic_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    invoices: Mapped[list[Invoice]] = relationship(back_populates="customer")
    promises_to_pay: Mapped[list[PromiseToPay]] = relationship(back_populates="customer")
    communications: Mapped[list[Communication]] = relationship(back_populates="customer")
    recovery_cases: Mapped[list[RecoveryCase]] = relationship(back_populates="customer")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("original_amount >= 0", name="original_amount_nonnegative"),
        CheckConstraint("outstanding_amount >= 0", name="outstanding_amount_nonnegative"),
        CheckConstraint("outstanding_amount <= original_amount", name="outstanding_not_greater_than_original"),
        UniqueConstraint("customer_id", "invoice_number", name="customer_invoice_number"),
        Index("ix_invoices_customer_status_due_date", "customer_id", "status", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.OPEN, server_default=InvoiceStatus.OPEN.value, index=True)

    customer: Mapped[Customer] = relationship(back_populates="invoices")
    payments: Mapped[list[Payment]] = relationship(back_populates="invoice")
    promises_to_pay: Mapped[list[PromiseToPay]] = relationship(back_populates="invoice")
    recovery_cases: Mapped[list[RecoveryCase]] = relationship(back_populates="invoice")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reference: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class Communication(Base):
    __tablename__ = "communications"
    __table_args__ = (Index("ix_communications_customer_occurred_at", "customer_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    direction: Mapped[CommunicationDirection] = mapped_column(Enum(CommunicationDirection, name="communication_direction"), nullable=False)
    channel: Mapped[CommunicationChannel] = mapped_column(Enum(CommunicationChannel, name="communication_channel"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ai_processing_status: Mapped[AIProcessingStatus] = mapped_column(Enum(AIProcessingStatus, name="ai_processing_status"), nullable=False, default=AIProcessingStatus.NOT_REQUESTED, server_default=AIProcessingStatus.NOT_REQUESTED.value)
    ai_processing_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    customer: Mapped[Customer] = relationship(back_populates="communications")
    sourced_promises: Mapped[list[PromiseToPay]] = relationship(back_populates="source_communication")
    analyses: Mapped[list[CommunicationAnalysis]] = relationship(back_populates="communication", cascade="all, delete-orphan")


class CommunicationAnalysis(Base):
    """Provider interpretation only; it never changes financial or recovery facts."""

    __tablename__ = "communication_analyses"
    __table_args__ = (Index("ix_communication_analyses_communication_analyzed_at", "communication_id", "analyzed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    communication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("communications.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    review_status: Mapped[AnalysisReviewStatus] = mapped_column(Enum(AnalysisReviewStatus, name="analysis_review_status"), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    communication: Mapped[Communication] = relationship(back_populates="analyses")


class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"
    __table_args__ = (
        CheckConstraint("promised_amount > 0", name="promised_amount_positive"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_between_zero_and_one"),
        Index("ix_promises_to_pay_customer_status_date", "customer_id", "status", "promised_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    promised_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    promised_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[PromiseStatus] = mapped_column(Enum(PromiseStatus, name="promise_status"), nullable=False, default=PromiseStatus.ACTIVE, server_default=PromiseStatus.ACTIVE.value, index=True)
    source_communication_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("communications.id", ondelete="SET NULL"), index=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    customer: Mapped[Customer] = relationship(back_populates="promises_to_pay")
    invoice: Mapped[Invoice | None] = relationship(back_populates="promises_to_pay")
    source_communication: Mapped[Communication | None] = relationship(back_populates="sourced_promises")


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"
    __table_args__ = (Index("ix_recovery_cases_customer_state_priority", "customer_id", "current_state", "priority"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), index=True)
    current_state: Mapped[RecoveryState] = mapped_column(Enum(RecoveryState, name="recovery_state"), nullable=False, default=RecoveryState.NEW, server_default=RecoveryState.NEW.value, index=True)
    priority: Mapped[RecoveryPriority] = mapped_column(Enum(RecoveryPriority, name="recovery_priority"), nullable=False, default=RecoveryPriority.NORMAL, server_default=RecoveryPriority.NORMAL.value, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(back_populates="recovery_cases")
    invoice: Mapped[Invoice | None] = relationship(back_populates="recovery_cases")
    actions: Mapped[list[RecoveryAction]] = relationship(back_populates="recovery_case")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"
    __table_args__ = (Index("ix_recovery_actions_case_status_created_at", "recovery_case_id", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_cases.id", ondelete="RESTRICT"), nullable=False, index=True)
    action_type: Mapped[RecoveryActionType] = mapped_column(Enum(RecoveryActionType, name="recovery_action_type"), nullable=False)
    status: Mapped[RecoveryActionStatus] = mapped_column(Enum(RecoveryActionStatus, name="recovery_action_status"), nullable=False, default=RecoveryActionStatus.PLANNED, server_default=RecoveryActionStatus.PLANNED.value, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus, name="approval_status"), nullable=False, default=ApprovalStatus.NOT_REQUIRED, server_default=ApprovalStatus.NOT_REQUIRED.value, index=True)
    # Immutable snapshot of the read-only recommendation that originated work.
    recommendation_action: Mapped[str | None] = mapped_column(String(80), index=True)
    recommendation_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    human_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    decision_by: Mapped[str | None] = mapped_column(String(255))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_by: Mapped[str | None] = mapped_column(String(255))
    operator_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recovery_case: Mapped[RecoveryCase] = relationship(back_populates="actions")


class ExternalPaymentRequest(Base):
    """Operator-approved request sent across the payment-provider boundary."""

    __tablename__ = "external_payment_requests"
    __table_args__ = (
        CheckConstraint("requested_amount > 0", name="external_payment_request_amount_positive"),
        CheckConstraint("paid_amount >= 0 AND paid_amount <= requested_amount", name="external_payment_request_paid_amount_valid"),
        UniqueConstraint("provider", "provider_reference", name="external_payment_request_provider_reference"),
        Index("ix_external_payment_requests_case_created_at", "recovery_case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_cases.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(100), index=True)
    provider_url: Mapped[str | None] = mapped_column(String(2048))
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"), server_default="0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_PROVIDER", server_default="PENDING_PROVIDER", index=True)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ProviderEvent(Base):
    """Idempotency and evidence record for an inbound provider event."""

    __tablename__ = "provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="provider_event_identity"),
        UniqueConstraint("provider", "provider_payment_reference", name="provider_payment_identity"),
        Index("ix_provider_events_request_received_at", "payment_request_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("external_payment_requests.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_payment_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditEvent(Base):
    """Append-only event history. Application code must insert, never update or delete."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity_occurred_at", "entity_type", "entity_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String(50))
    actor_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class SimulationState(Base):
    __tablename__ = "simulation_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, server_default="default")
    simulation_date: Mapped[date] = mapped_column(Date, nullable=False)
    cycle: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SimulationEvent(Base):
    """Append-only operational events emitted by the deterministic simulator."""

    __tablename__ = "simulation_events"
    __table_args__ = (Index("ix_simulation_events_cycle_occurred_at", "cycle", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle: Mapped[int] = mapped_column(nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    recovery_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
