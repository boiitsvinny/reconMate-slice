"""Command orchestration and short-lived confirmation-plan lifecycle."""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from app.commands.audit import audit_for
from app.commands.executor import CommandExecutor
from app.commands.interpreter import BaseCommandInterpreter, RuleBasedCommandInterpreter
from app.commands.planner import CommandPlanner
from app.commands.schemas import (
    CommandConfirmationResult,
    CommandPlan,
    CommandRequest,
    CommandResult,
    ConfirmCommandRequest,
    ExecutionMode,
    ProposalStatus,
)
from app.commands.tools import CommandTools


class PlanNotFoundError(LookupError):
    pass


class PlanExpiredError(LookupError):
    pass


class EphemeralPlanRegistry:
    """Bounded one-process plan storage; structured plans only, never raw commands."""

    def __init__(self, max_plans: int = 500):
        self.max_plans = max_plans
        self._plans: OrderedDict[UUID, CommandPlan] = OrderedDict()
        self._lock = Lock()

    def save(self, plan: CommandPlan) -> None:
        if not plan.requires_confirmation:
            return
        with self._lock:
            self._purge_expired()
            self._plans[plan.plan_id] = plan
            self._plans.move_to_end(plan.plan_id)
            while len(self._plans) > self.max_plans:
                self._plans.popitem(last=False)

    def claim(self, plan_id: UUID) -> CommandPlan:
        with self._lock:
            plan = self._plans.pop(plan_id, None)
            if plan is None:
                raise PlanNotFoundError("Command plan was not found or has already been confirmed.")
            if plan.expires_at is not None and plan.expires_at <= datetime.now(UTC):
                raise PlanExpiredError("Command plan has expired. Create a fresh plan from current data.")
            return plan

    def clear(self) -> None:
        """Discard plans that refer to operational records replaced by a demo reset."""
        with self._lock:
            self._plans.clear()

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [key for key, plan in self._plans.items() if plan.expires_at is not None and plan.expires_at <= now]
        for key in expired:
            self._plans.pop(key, None)


PLAN_REGISTRY = EphemeralPlanRegistry()


class CommandService:
    def __init__(
        self,
        interpreter: BaseCommandInterpreter | None = None,
        planner: CommandPlanner | None = None,
        executor: CommandExecutor | None = None,
        registry: EphemeralPlanRegistry | None = None,
    ):
        self.interpreter = interpreter or RuleBasedCommandInterpreter()
        self.planner = planner or CommandPlanner()
        self.executor = executor or CommandExecutor()
        self.registry = registry or PLAN_REGISTRY

    def run(self, request: CommandRequest, tools: CommandTools) -> CommandResult:
        interpreted = self.interpreter.interpret(request)
        planning = self.planner.plan(request, interpreted, tools)
        self.registry.save(planning.plan)
        outcomes = self.executor.initial_outcomes(planning.plan)
        limitations = [
            "ReconMate did not send communications, payment links, or perform financial actions.",
            "All intelligence and plans reflect the database state at command execution time.",
        ]
        if planning.plan.requires_confirmation:
            limitations.append(
                "The confirmation token is process-local, single-use, and expires after 30 minutes; it does not survive a service restart."
            )
        return CommandResult(
            plan_id=planning.plan.plan_id,
            interpreted_intent=interpreted,
            understanding_summary=planning.understanding_summary,
            query_evidence=planning.query_evidence,
            analyzed_entities=planning.analyzed_entities,
            plan=planning.plan,
            outcomes=outcomes,
            warnings=planning.warnings,
            limitations=limitations,
            audit=audit_for(planning.plan),
        )

    def confirm(
        self,
        plan_id: UUID,
        request: ConfirmCommandRequest,
        tools: CommandTools,
    ) -> CommandConfirmationResult:
        plan = self.registry.claim(plan_id)
        outcomes, warnings = self.executor.confirm(plan, request, tools)
        execution_mode = (
            ExecutionMode.EXECUTED
            if any(item.status is ProposalStatus.EXECUTED for item in outcomes)
            else ExecutionMode.CONFIRMATION_REQUIRED
        )
        return CommandConfirmationResult(
            plan_id=plan.plan_id,
            execution_mode=execution_mode,
            outcomes=outcomes,
            warnings=warnings,
            audit=audit_for(plan, execution_mode),
        )
