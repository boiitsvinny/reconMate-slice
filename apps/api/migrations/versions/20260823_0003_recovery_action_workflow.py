"""Add immutable recommendation snapshots and workflow decisions to actions.

Revision ID: 20260823_0003
Revises: 20260823_0002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260823_0003"
down_revision = "20260823_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing actions retain their historical states; these labels are additive.
    op.execute("ALTER TYPE recovery_action_status ADD VALUE IF NOT EXISTS 'RECOMMENDED'")
    op.execute("ALTER TYPE recovery_action_status ADD VALUE IF NOT EXISTS 'HELD'")
    op.add_column("recovery_actions", sa.Column("recommendation_action", sa.String(length=80)))
    op.add_column("recovery_actions", sa.Column("recommendation_context", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("recovery_actions", sa.Column("human_approval_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("recovery_actions", sa.Column("decision_by", sa.String(length=255)))
    op.add_column("recovery_actions", sa.Column("decision_reason", sa.Text()))
    op.add_column("recovery_actions", sa.Column("decision_at", sa.DateTime(timezone=True)))
    op.add_column("recovery_actions", sa.Column("executed_by", sa.String(length=255)))
    op.add_column("recovery_actions", sa.Column("operator_note", sa.Text()))
    op.create_index("ix_recovery_actions_recommendation_action", "recovery_actions", ["recommendation_action"])


def downgrade() -> None:
    op.drop_index("ix_recovery_actions_recommendation_action", table_name="recovery_actions")
    for column in ("operator_note", "executed_by", "decision_at", "decision_reason", "decision_by", "human_approval_required", "recommendation_context", "recommendation_action"):
        op.drop_column("recovery_actions", column)
    # PostgreSQL enum labels intentionally remain: removing them is not safe while
    # historical rows may use them.
