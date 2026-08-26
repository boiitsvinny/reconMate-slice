"""Safe command-plan preparation and explicit-confirmation execution."""

from __future__ import annotations

from fastapi import HTTPException
from uuid import NAMESPACE_URL, uuid5

from app.commands.schemas import (
    ActionOutcome,
    CommandPlan,
    ConfirmCommandRequest,
    ExecutionMode,
    ProposalStatus,
)
from app.commands.tools import CommandTools
from app.recommendations.schemas import RecommendedAction
from app.workflow.service import create_action


class CommandExecutor:
    def initial_outcomes(self, plan: CommandPlan) -> list[ActionOutcome]:
        outcomes: list[ActionOutcome] = []
        for proposal in plan.proposed_actions:
            if proposal.requires_confirmation:
                status = ProposalStatus.AWAITING_CONFIRMATION
                message = "Explicit confirmation is required before creating the internal workflow action."
            elif proposal.execution_mode is ExecutionMode.PREPARE and proposal.executable:
                status = ProposalStatus.PREPARED
                message = "The draft or operational preparation was generated; nothing was sent or externally executed."
            elif proposal.executable:
                status = ProposalStatus.ANALYZED
                message = "The read-only analysis completed from current ReconMate data."
            else:
                status = ProposalStatus.NOT_EXECUTABLE
                message = "This item is advisory only because its current blocker prevents workflow execution."
            outcomes.append(ActionOutcome(proposal_id=proposal.proposal_id, status=status, message=message))
        return outcomes

    def confirm(
        self,
        plan: CommandPlan,
        request: ConfirmCommandRequest,
        tools: CommandTools,
    ) -> tuple[list[ActionOutcome], list[str]]:
        requested = set(request.proposal_ids or [])
        confirmation_actions = [item for item in plan.proposed_actions if item.requires_confirmation]
        if requested:
            selected = [item for item in confirmation_actions if item.proposal_id in requested]
        else:
            selected = confirmation_actions
        warnings: list[str] = []
        known_ids = {item.proposal_id for item in confirmation_actions}
        unknown_ids = requested - known_ids
        if unknown_ids:
            warnings.append(f"Ignored {len(unknown_ids)} proposal identifier(s) that were not confirmation-required actions in this plan.")
        if requested and len(selected) < len(confirmation_actions):
            warnings.append("Unselected actions were not executed; this one-time plan token is now consumed.")
        if not selected:
            warnings.append("The plan contains no selected action that is eligible for confirmation execution.")
            return [], warnings

        outcomes: list[ActionOutcome] = []
        for proposal in selected:
            case = tools.get_case(proposal.target_id)
            if case is None or proposal.workflow_recommendation_action is None:
                outcomes.append(ActionOutcome(
                    proposal_id=proposal.proposal_id,
                    status=ProposalStatus.NOT_EXECUTABLE,
                    message="The recovery case or workflow recommendation is no longer available.",
                ))
                continue
            try:
                expected_action = RecommendedAction(proposal.workflow_recommendation_action)
                action = create_action(
                    tools.db,
                    case,
                    tools.simulation_date,
                    expected_action,
                    operator_note=request.note,
                    idempotency_id=uuid5(NAMESPACE_URL, f"reconmate/command/{plan.plan_id}/{proposal.proposal_id}"),
                )
                outcomes.append(ActionOutcome(
                    proposal_id=proposal.proposal_id,
                    status=ProposalStatus.EXECUTED,
                    message="Created an internal approval-controlled recovery workflow action; no customer contact occurred.",
                    recovery_action_id=str(action.id),
                    recovery_action_status=getattr(getattr(action, "status", None), "value", None),
                    recovery_action_created_at=getattr(action, "created_at", None),
                    workflow_effect=(getattr(action, "recommendation_context", None) or {}).get("workflow_effect"),
                ))
            except (HTTPException, ValueError) as exc:
                message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                outcomes.append(ActionOutcome(
                    proposal_id=proposal.proposal_id,
                    status=ProposalStatus.FAILED,
                    message=f"Workflow action was not created: {message}",
                ))
        return outcomes, warnings
