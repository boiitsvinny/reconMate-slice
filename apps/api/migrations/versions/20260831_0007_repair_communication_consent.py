"""Repair customer communication-consent columns if a deploy missed revision 0006.

Revision ID: 20260831_0007
Revises: 20260831_0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_0007"
down_revision = "20260831_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    consent = postgresql.ENUM("UNKNOWN", "OPTED_IN", "OPTED_OUT", name="communication_consent_status")
    consent.create(bind, checkfirst=True)
    existing = {column["name"] for column in sa.inspect(bind).get_columns("customers")}
    added_status = "communication_consent_status" not in existing
    added_channel = "preferred_outreach_channel" not in existing

    if added_status:
        op.add_column("customers", sa.Column(
            "communication_consent_status",
            postgresql.ENUM(name="communication_consent_status", create_type=False),
            nullable=True,
            server_default="UNKNOWN",
        ))
    if added_channel:
        op.add_column("customers", sa.Column("preferred_outreach_channel", sa.String(length=30), nullable=True))

    # Only a genuinely missing column means the existing portfolio predates
    # consent metadata. Preserve any values already written by revision 0006.
    if added_status:
        op.execute("UPDATE customers SET communication_consent_status = 'OPTED_IN'")
    if added_channel:
        op.execute("UPDATE customers SET preferred_outreach_channel = 'EMAIL' WHERE communication_consent_status = 'OPTED_IN'")
    op.alter_column(
        "customers", "communication_consent_status", nullable=False,
        server_default="UNKNOWN", existing_type=postgresql.ENUM(name="communication_consent_status", create_type=False),
    )


def downgrade() -> None:
    # Revision 0006 owns these columns. This repair revision is intentionally
    # schema-idempotent and has nothing additional to remove.
    pass
