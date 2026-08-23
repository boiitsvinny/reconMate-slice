"""Add persisted deterministic simulation cycles and event history.

Revision ID: 20260823_0004
Revises: 20260823_0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260823_0004"
down_revision = "20260823_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simulation_states", sa.Column("cycle", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "simulation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cycle", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True)),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (("ix_simulation_events_cycle", ["cycle"]), ("ix_simulation_events_event_type", ["event_type"]), ("ix_simulation_events_customer_id", ["customer_id"]), ("ix_simulation_events_invoice_id", ["invoice_id"]), ("ix_simulation_events_recovery_case_id", ["recovery_case_id"]), ("ix_simulation_events_occurred_at", ["occurred_at"]), ("ix_simulation_events_cycle_occurred_at", ["cycle", "occurred_at"])):
        op.create_index(name, "simulation_events", columns)


def downgrade() -> None:
    op.drop_table("simulation_events")
    op.drop_column("simulation_states", "cycle")
