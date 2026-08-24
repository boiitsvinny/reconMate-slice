"""Lightweight response-level command audit metadata; no raw command persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from app.commands.schemas import CommandAudit, CommandPlan, ExecutionMode


def audit_for(plan: CommandPlan, execution_status: ExecutionMode | None = None) -> CommandAudit:
    return CommandAudit(
        plan_id=plan.plan_id,
        interpreted_intent=plan.intent,
        timestamp=datetime.now(UTC),
        proposal_count=len(plan.proposed_actions),
        execution_status=execution_status or plan.execution_mode,
    )
