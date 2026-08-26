"""Add provider payment requests and idempotent inbound events.

Revision ID: 20260826_0005
Revises: 20260823_0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260826_0005"
down_revision = "20260823_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_payment_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_cases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_mode", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=100)),
        sa.Column("provider_url", sa.String(length=2048)),
        sa.Column("requested_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_PROVIDER"),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("operator_id", sa.String(length=255), nullable=False),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("requested_amount > 0", name="external_payment_request_amount_positive"),
        sa.CheckConstraint("paid_amount >= 0 AND paid_amount <= requested_amount", name="external_payment_request_paid_amount_valid"),
        sa.UniqueConstraint("provider", "provider_reference", name="external_payment_request_provider_reference"),
    )
    for name, columns in (
        ("ix_external_payment_requests_recovery_case_id", ["recovery_case_id"]),
        ("ix_external_payment_requests_customer_id", ["customer_id"]),
        ("ix_external_payment_requests_invoice_id", ["invoice_id"]),
        ("ix_external_payment_requests_provider_reference", ["provider_reference"]),
        ("ix_external_payment_requests_status", ["status"]),
        ("ix_external_payment_requests_case_created_at", ["recovery_case_id", "created_at"]),
    ):
        op.create_index(name, "external_payment_requests", columns)
    op.create_table(
        "provider_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("payment_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_payment_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_event_id", sa.String(length=100), nullable=False),
        sa.Column("provider_payment_reference", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_event_id", name="provider_event_identity"),
        sa.UniqueConstraint("provider", "provider_payment_reference", name="provider_payment_identity"),
    )
    for name, columns in (
        ("ix_provider_events_payment_request_id", ["payment_request_id"]),
        ("ix_provider_events_payment_id", ["payment_id"]),
        ("ix_provider_events_request_received_at", ["payment_request_id", "received_at"]),
    ):
        op.create_index(name, "provider_events", columns)


def downgrade() -> None:
    op.drop_table("provider_events")
    op.drop_table("external_payment_requests")
