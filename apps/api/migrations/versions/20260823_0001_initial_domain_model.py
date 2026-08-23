"""Create ReconMate domain tables.

Revision ID: 20260823_0001
Revises:
Create Date: 2026-08-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260823_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    invoice_status = sa.Enum("OPEN", "PARTIALLY_PAID", "PAID", "OVERDUE", "DISPUTED", "WRITTEN_OFF", "CANCELLED", name="invoice_status")
    promise_status = sa.Enum("ACTIVE", "FULFILLED", "BROKEN", "CANCELLED", name="promise_status")
    communication_direction = sa.Enum("INBOUND", "OUTBOUND", name="communication_direction")
    communication_channel = sa.Enum("EMAIL", "PHONE", "SMS", "WHATSAPP", "PORTAL", "LETTER", "OTHER", name="communication_channel")
    ai_processing_status = sa.Enum("NOT_REQUESTED", "PENDING", "PROCESSED", "FAILED", name="ai_processing_status")
    recovery_state = sa.Enum("NEW", "IN_PROGRESS", "AWAITING_CUSTOMER", "PROMISE_MONITORING", "ESCALATED", "RESOLVED", "CLOSED", name="recovery_state")
    recovery_priority = sa.Enum("LOW", "NORMAL", "HIGH", "CRITICAL", name="recovery_priority")
    recovery_action_type = sa.Enum("OUTREACH", "FOLLOW_UP", "RECORD_PROMISE", "ESCALATE", "CLOSE_CASE", "NOTE", name="recovery_action_type")
    recovery_action_status = sa.Enum("PLANNED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED", "FAILED", name="recovery_action_status")
    approval_status = sa.Enum("NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED", name="approval_status")

    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_reference", sa.String(length=100), nullable=False),
        sa.Column("segment", sa.String(length=100)),
        sa.Column("is_strategic_account", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("account_reference", name="uq_customers_account_reference"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("original_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("outstanding_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", invoice_status, nullable=False, server_default="OPEN"),
        sa.CheckConstraint("original_amount >= 0", name="original_amount_nonnegative"),
        sa.CheckConstraint("outstanding_amount >= 0", name="outstanding_amount_nonnegative"),
        sa.CheckConstraint("outstanding_amount <= original_amount", name="outstanding_not_greater_than_original"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_invoices_customer_id_customers", ondelete="RESTRICT"),
        sa.UniqueConstraint("customer_id", "invoice_number", name="customer_invoice_number"),
    )
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_customer_status_due_date", "invoices", ["customer_id", "status", "due_date"])
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name="fk_payments_invoice_id_invoices", ondelete="RESTRICT"),
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"])
    op.create_index("ix_payments_reference", "payments", ["reference"])
    op.create_table(
        "communications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", communication_direction, nullable=False),
        sa.Column("channel", communication_channel, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ai_processing_status", ai_processing_status, nullable=False, server_default="NOT_REQUESTED"),
        sa.Column("ai_processing_metadata", postgresql.JSONB(astext_type=sa.Text())),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_communications_customer_id_customers", ondelete="RESTRICT"),
    )
    op.create_index("ix_communications_customer_id", "communications", ["customer_id"])
    op.create_index("ix_communications_occurred_at", "communications", ["occurred_at"])
    op.create_index("ix_communications_customer_occurred_at", "communications", ["customer_id", "occurred_at"])
    op.create_table(
        "promises_to_pay",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True)),
        sa.Column("promised_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("promised_date", sa.Date(), nullable=False),
        sa.Column("status", promise_status, nullable=False, server_default="ACTIVE"),
        sa.Column("source_communication_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("promised_amount > 0", name="promised_amount_positive"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_between_zero_and_one"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_promises_to_pay_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name="fk_promises_to_pay_invoice_id_invoices", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_communication_id"], ["communications.id"], name="fk_promises_to_pay_source_communication_id_communications", ondelete="SET NULL"),
    )
    for name, column in (("ix_promises_to_pay_customer_id", "customer_id"), ("ix_promises_to_pay_invoice_id", "invoice_id"), ("ix_promises_to_pay_promised_date", "promised_date"), ("ix_promises_to_pay_status", "status"), ("ix_promises_to_pay_source_communication_id", "source_communication_id")):
        op.create_index(name, "promises_to_pay", [column])
    op.create_index("ix_promises_to_pay_customer_status_date", "promises_to_pay", ["customer_id", "status", "promised_date"])
    op.create_table(
        "recovery_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True)),
        sa.Column("current_state", recovery_state, nullable=False, server_default="NEW"),
        sa.Column("priority", recovery_priority, nullable=False, server_default="NORMAL"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_recovery_cases_customer_id_customers", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name="fk_recovery_cases_invoice_id_invoices", ondelete="SET NULL"),
    )
    for name, column in (("ix_recovery_cases_customer_id", "customer_id"), ("ix_recovery_cases_invoice_id", "invoice_id"), ("ix_recovery_cases_current_state", "current_state"), ("ix_recovery_cases_priority", "priority")):
        op.create_index(name, "recovery_cases", [column])
    op.create_index("ix_recovery_cases_customer_state_priority", "recovery_cases", ["customer_id", "current_state", "priority"])
    op.create_table(
        "recovery_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", recovery_action_type, nullable=False),
        sa.Column("status", recovery_action_status, nullable=False, server_default="PLANNED"),
        sa.Column("reason", sa.Text()),
        sa.Column("approval_status", approval_status, nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"], name="fk_recovery_actions_recovery_case_id_recovery_cases", ondelete="RESTRICT"),
    )
    for name, column in (("ix_recovery_actions_recovery_case_id", "recovery_case_id"), ("ix_recovery_actions_status", "status"), ("ix_recovery_actions_approval_status", "approval_status")):
        op.create_index(name, "recovery_actions", [column])
    op.create_index("ix_recovery_actions_case_status_created_at", "recovery_actions", ["recovery_case_id", "status", "created_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=50)),
        sa.Column("actor_id", sa.String(length=255)),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_events_entity_occurred_at", "audit_events", ["entity_type", "entity_id", "occurred_at"])
    op.create_table(
        "simulation_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, server_default="default"),
        sa.Column("simulation_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_simulation_states_name"),
    )


def downgrade() -> None:
    for table in ("simulation_states", "audit_events", "recovery_actions", "recovery_cases", "promises_to_pay", "communications", "payments", "invoices", "customers"):
        op.drop_table(table)
    bind = op.get_bind()
    for enum_name in ("approval_status", "recovery_action_status", "recovery_action_type", "recovery_priority", "recovery_state", "ai_processing_status", "communication_channel", "communication_direction", "promise_status", "invoice_status"):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
