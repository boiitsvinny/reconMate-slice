"""Add fail-closed customer communication consent metadata.

Revision ID: 20260831_0006
Revises: 20260826_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_0006"
down_revision = "20260826_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    consent = postgresql.ENUM("UNKNOWN", "OPTED_IN", "OPTED_OUT", name="communication_consent_status")
    consent.create(op.get_bind(), checkfirst=True)
    op.add_column("customers", sa.Column(
        "communication_consent_status", consent, nullable=False, server_default="UNKNOWN",
    ))
    op.add_column("customers", sa.Column("preferred_outreach_channel", sa.String(length=30), nullable=True))
    # Preserve the behavior of customers that existed before consent metadata;
    # newly created customers retain the fail-closed UNKNOWN default.
    op.execute("UPDATE customers SET communication_consent_status = 'OPTED_IN', preferred_outreach_channel = 'EMAIL'")


def downgrade() -> None:
    op.drop_column("customers", "preferred_outreach_channel")
    op.drop_column("customers", "communication_consent_status")
    postgresql.ENUM(name="communication_consent_status").drop(op.get_bind(), checkfirst=True)
