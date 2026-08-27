"""Command orchestration and short-lived confirmation-plan lifecycle."""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
from threading import Lock
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
from app.models.domain import AuditEvent


class PlanNotFoundError(LookupError):
    pass


class PlanExpiredError(LookupError):
    pass


class EphemeralPlanRegistry:
    """Bounded one-process plan storage; structured plans only, never raw commands."""

    def __init__(self, max_plans: int = 500):
        self.max_plans = max_plans
        self._plans: OrderedDict[UUID, CommandPlan] = OrderedDict()
        self._confirmations: OrderedDict[UUID, CommandConfirmationResult] = OrderedDict()
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

    def confirmed(self, plan_id: UUID) -> CommandConfirmationResult | None:
        with self._lock:
            result = self._confirmations.get(plan_id)
            if result is not None:
                self._confirmations.move_to_end(plan_id)
            return result

    def save_confirmation(self, result: CommandConfirmationResult) -> None:
        with self._lock:
            self._confirmations[result.plan_id] = result
            self._confirmations.move_to_end(result.plan_id)
            while len(self._confirmations) > self.max_plans:
                self._confirmations.popitem(last=False)

    def clear(self) -> None:
        """Discard plans that refer to operational records replaced by a demo reset."""
        with self._lock:
            self._plans.clear()
            self._confirmations.clear()

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
        self._save_plan(tools, planning.plan)
        outcomes = self.executor.initial_outcomes(planning.plan)
        limitations = [
            "ReconMate did not send communications, payment links, or perform financial actions.",
            "All intelligence and plans reflect the database state at command execution time.",
        ]
        if planning.plan.requires_confirmation:
            limitations.append(
                "The confirmation identity expires after 30 minutes. Its plan, selected work, and result are persisted so exact replays survive a service restart without creating duplicate workflow actions."
            )
        return CommandResult(
            plan_id=planning.plan.plan_id,
            interpreted_intent=interpreted,
            understanding_summary=planning.understanding_summary,
            result_kind=planning.result_kind,
            direct_records=planning.direct_records or [],
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
        previous = self.registry.confirmed(plan_id) or self._load_confirmation(tools, plan_id)
        if previous is not None:
            return previous
        try:
            plan = self.registry.claim(plan_id)
        except PlanNotFoundError:
            plan = self._load_plan(tools, plan_id)
            if plan is None:
                raise
        if plan.expires_at is not None and plan.expires_at <= datetime.now(UTC):
            raise PlanExpiredError("Command plan has expired. Create a fresh plan from current data.")
        durable_request = self._load_or_save_confirmation_request(tools, plan_id, request)
        outcomes, warnings = self.executor.confirm(plan, durable_request, tools)
        execution_mode = (
            ExecutionMode.EXECUTED
            if any(item.status is ProposalStatus.EXECUTED for item in outcomes)
            else ExecutionMode.CONFIRMATION_REQUIRED
        )
        result = CommandConfirmationResult(
            plan_id=plan.plan_id,
            execution_mode=execution_mode,
            outcomes=outcomes,
            warnings=warnings,
            audit=audit_for(plan, execution_mode),
        )
        self._save_confirmation(tools, result)
        self.registry.save_confirmation(result)
        return result

    @staticmethod
    def _persistence_available(tools: CommandTools) -> bool:
        return all(callable(getattr(tools.db, name, None)) for name in ("get", "add", "commit", "scalar"))

    @staticmethod
    def _audit_id(plan_id: UUID, suffix: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"reconmate/command/{plan_id}/{suffix}")

    def _save_plan(self, tools: CommandTools, plan: CommandPlan) -> None:
        if not plan.requires_confirmation or not self._persistence_available(tools):
            return
        event_id = self._audit_id(plan.plan_id, "plan")
        if tools.db.get(AuditEvent, event_id) is None:
            tools.db.add(AuditEvent(
                id=event_id, entity_type="CommandPlan", entity_id=plan.plan_id,
                event_type="COMMAND_PLAN_PREPARED", actor_type="system",
                payload={"plan": plan.model_dump(mode="json")}, occurred_at=plan.created_at,
            ))
            tools.db.commit()

    def _load_plan(self, tools: CommandTools, plan_id: UUID) -> CommandPlan | None:
        if not self._persistence_available(tools):
            return None
        event = tools.db.get(AuditEvent, self._audit_id(plan_id, "plan"))
        payload = (event.payload or {}).get("plan") if event else None
        plan = CommandPlan.model_validate(payload) if payload else None
        if plan is None:
            return None
        latest_reset = tools.db.scalar(
            select(AuditEvent.occurred_at)
            .where(AuditEvent.event_type == "SYNTHETIC_PORTFOLIO_SEEDED")
            .order_by(AuditEvent.occurred_at.desc())
            .limit(1)
        )
        if latest_reset is not None and latest_reset > plan.created_at:
            raise PlanExpiredError("Command plan predates the latest demo reset. Create a fresh plan from current data.")
        return plan

    def _load_or_save_confirmation_request(
        self, tools: CommandTools, plan_id: UUID, request: ConfirmCommandRequest,
    ) -> ConfirmCommandRequest:
        if not self._persistence_available(tools):
            return request
        event_id = self._audit_id(plan_id, "confirmation-request")
        event = tools.db.get(AuditEvent, event_id)
        if event is not None:
            return ConfirmCommandRequest.model_validate((event.payload or {})["request"])
        tools.db.add(AuditEvent(
            id=event_id, entity_type="CommandPlan", entity_id=plan_id,
            event_type="COMMAND_CONFIRMATION_RECEIVED", actor_type="operator", actor_id=request.operator_id,
            payload={"request": request.model_dump(mode="json")}, occurred_at=datetime.now(UTC),
        ))
        try:
            tools.db.commit()
            return request
        except IntegrityError:
            tools.db.rollback()
            event = tools.db.get(AuditEvent, event_id)
            if event is None:
                raise
            return ConfirmCommandRequest.model_validate((event.payload or {})["request"])

    def _save_confirmation(self, tools: CommandTools, result: CommandConfirmationResult) -> None:
        if not self._persistence_available(tools):
            return
        event_id = self._audit_id(result.plan_id, "confirmation-result")
        if tools.db.get(AuditEvent, event_id) is None:
            tools.db.add(AuditEvent(
                id=event_id, entity_type="CommandPlan", entity_id=result.plan_id,
                event_type="COMMAND_CONFIRMATION_RECORDED", actor_type="system",
                payload={"result": result.model_dump(mode="json")}, occurred_at=datetime.now(UTC),
            ))
            try:
                tools.db.commit()
            except IntegrityError:
                tools.db.rollback()
                if tools.db.get(AuditEvent, event_id) is None:
                    raise

    def _load_confirmation(self, tools: CommandTools, plan_id: UUID) -> CommandConfirmationResult | None:
        if not self._persistence_available(tools):
            return None
        event = tools.db.get(AuditEvent, self._audit_id(plan_id, "confirmation-result"))
        payload = (event.payload or {}).get("result") if event else None
        return CommandConfirmationResult.model_validate(payload) if payload else None
