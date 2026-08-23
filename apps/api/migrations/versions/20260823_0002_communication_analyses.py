"""Store re-analyzable communication intelligence separately.

Revision ID: 20260823_0002
Revises: 20260823_0001
Create Date: 2026-08-23 01:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260823_0002"
down_revision = "20260823_0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # The type is shared by this migration's explicit setup and table DDL.  Keep
    # table creation from issuing a second CREATE TYPE after a prior failed run
    # has already left the enum in PostgreSQL.
    review_status = postgresql.ENUM(
        "PENDING_REVIEW", "NOT_REQUIRED", name="analysis_review_status", create_type=False,
    )
    postgresql.ENUM(
        "PENDING_REVIEW", "NOT_REQUIRED", name="analysis_review_status",
    ).create(op.get_bind(), checkfirst=True)
    op.create_table("communication_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("communication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=255)),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("review_status", review_status, nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["communication_id"], ["communications.id"], name="fk_communication_analyses_communication_id_communications", ondelete="CASCADE"),
    )
    op.create_index("ix_communication_analyses_communication_id", "communication_analyses", ["communication_id"])
    op.create_index("ix_communication_analyses_communication_analyzed_at", "communication_analyses", ["communication_id", "analyzed_at"])

def downgrade() -> None:
    op.drop_table("communication_analyses")
    sa.Enum(name="analysis_review_status").drop(op.get_bind(), checkfirst=True)
