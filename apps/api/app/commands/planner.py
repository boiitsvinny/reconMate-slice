"""Deterministic planner that turns interpreted intent and real data into proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.commands.schemas import (
    ActionProposal,
    CommandIntent,
    CommandIntentType,
    CommandPlan,
    CommandRequest,
    EntityReference,
    ExecutionMode,
    ExclusionCount,
    InspectionScope,
    ProposalActionType,
    QueryEvidence,
    RankingEvidence,
)
from app.commands.tools import CaseCandidate, CommandTools, QueryExecution
from app.intelligence.operational_schemas import IntelligenceResult, PriorityLevel
from app.models.domain import RecoveryPriority
from app.recommendations.schemas import RecommendedAction


PLAN_TTL_MINUTES = 30
DEFAULT_RESULT_LIMIT = 5


@dataclass(frozen=True)
class PlanningOutput:
    plan: CommandPlan
    analyzed_entities: list[IntelligenceResult]
    understanding_summary: str
    warnings: list[str]
    query_evidence: QueryEvidence


class CommandPlanner:
    def plan(
        self,
        request: CommandRequest,
        interpreted: CommandIntent,
        tools: CommandTools,
    ) -> PlanningOutput:
        plan_id = uuid4()
        created_at = datetime.now(UTC)
        actions: list[ActionProposal] = []
        analyzed: list[IntelligenceResult] = []
        warnings: list[str] = []
        evidence = QueryEvidence()
        summary = "The command could not be mapped safely to a supported operation."
        limit = interpreted.filters.top_n or DEFAULT_RESULT_LIMIT
        intent = interpreted.intent

        if intent is CommandIntentType.UNKNOWN:
            warnings.append(interpreted.guidance or "Use a supported analysis or preparation command.")

        elif intent is CommandIntentType.PORTFOLIO_ANALYSIS:
            portfolio = tools.get_portfolio_intelligence()
            analyzed = portfolio.highest_priority[:limit]
            summary = f"Analyzed {portfolio.customer_count} customers and summarized the {len(analyzed)} highest-priority accounts."
            actions.append(self._portfolio_action(plan_id, portfolio.customer_count))
            evidence = QueryEvidence(
                records_inspected=portfolio.customer_count, records_matched=portfolio.customer_count,
                records_excluded=0, records_returned=len(analyzed),
                inspection_scope=InspectionScope(customers=portfolio.customer_count),
                ranking=self._ranking_evidence(analyzed), latest_cycle=tools.latest_cycle_evidence(analyzed),
            )

        elif intent in {CommandIntentType.PRIORITIZE_CASES, CommandIntentType.REVIEW_BROKEN_PROMISES}:
            query = interpreted.query
            if intent is CommandIntentType.PRIORITIZE_CASES and not query.count_only and query.limit is None and not interpreted.filters.include_all:
                query = query.model_copy(update={"limit": DEFAULT_RESULT_LIMIT})
            if query.entity.value == "RECOVERY_CASES":
                execution = tools.execute_case_query(query)
                candidates = execution.records
                analyzed = [item.intelligence for item in candidates]
                summary = f"Found {len(candidates)} recovery cases matching the composed current-state query."
                if query.count_only:
                    actions.append(self._query_count_action(plan_id, len(candidates), "recovery cases"))
                    analyzed = []
                else:
                    actions.extend(self._case_analysis_action(plan_id, item.intelligence, item.case) for item in candidates)
                stored = {item.intelligence.entity_id: item.case.priority.value for item in candidates}
                evidence = self._execution_evidence(execution, analyzed, tools, stored)
            else:
                execution = tools.execute_customer_query(query)
                analyzed = execution.records
                label = "customers with factually broken payment promises" if intent is CommandIntentType.REVIEW_BROKEN_PROMISES else "customers"
                summary = f"Found {len(analyzed)} {label} matching the composed current-state query."
                if query.count_only:
                    actions.append(self._query_count_action(plan_id, len(analyzed), "customers"))
                    analyzed = []
                else:
                    actions.extend(self._customer_review(plan_id, item) for item in analyzed)
                evidence = self._execution_evidence(execution, analyzed, tools)

        elif intent is CommandIntentType.CUSTOMER_ANALYSIS:
            result = tools.get_customer_intelligence(request.context_customer_id) if request.context_customer_id else None
            if result is None:
                warnings.append("The requested customer was not found or no customer context was supplied.")
                summary = "No customer could be analyzed."
            else:
                analyzed = [result]
                summary = f"Analyzed {result.entity_name} using current invoices, payments, promises, disputes, and recovery cases."
                actions.append(self._analysis_action(plan_id, result, ProposalActionType.ANALYZE_CUSTOMER))

        elif intent in {CommandIntentType.CASE_ANALYSIS, CommandIntentType.EXPLAIN_RECOMMENDATION}:
            result = tools.get_case_intelligence(request.context_case_id) if request.context_case_id else None
            if result is None:
                warnings.append("The requested recovery case was not found or no case context was supplied.")
                summary = "No recovery case could be analyzed."
            else:
                analyzed = [result]
                case = tools.get_case(request.context_case_id) if request.context_case_id else None
                stored_priority = case.priority if case is not None else None
                summary = (
                    f"Explained the recommendation for {result.entity_name} from its current intelligence factors."
                    if intent is CommandIntentType.EXPLAIN_RECOMMENDATION
                    else f"Analyzed recovery case {result.entity_name} from current factual data."
                )
                actions.append(self._case_analysis_action(plan_id, result, case))
                if stored_priority is not None and self._stored_level(stored_priority) is not result.level:
                    warnings.append(
                        f"Stored workflow priority is {stored_priority.value}; fresh operational intelligence is {result.level.value}. "
                        "These are reported separately rather than silently overwriting case state."
                    )

        elif intent is CommandIntentType.PREPARE_FOLLOW_UPS:
            query = interpreted.query.model_copy(update={"broken_promise": True})
            broken = tools.query_customer_intelligence(query)
            analyzed = broken
            customer_ids = {item.entity_id for item in broken}
            candidates = tools.get_recovery_candidates(customer_ids=customer_ids, top_n=interpreted.filters.top_n)
            summary = f"Prepared safe follow-up proposals for {len(candidates)} recovery cases belonging to customers with broken promises."
            actions.extend(self._case_recovery_proposal(plan_id, item, follow_up=True) for item in candidates)
            if broken and not candidates:
                warnings.append("Broken-promise customers were found, but none currently has a recovery case that can receive workflow work.")

        elif intent is CommandIntentType.PREPARE_RECOVERY_ACTIONS:
            levels = interpreted.filters.risk_levels or [PriorityLevel.CRITICAL]
            candidates = tools.get_recovery_candidates(levels=levels, top_n=None if interpreted.filters.include_all else limit)
            analyzed = [item.intelligence for item in candidates]
            summary = f"Prepared {len(candidates)} recovery-case proposals after applying current intelligence and recovery blockers."
            actions.extend(self._case_recovery_proposal(plan_id, item) for item in candidates)

        elif intent is CommandIntentType.PREPARE_PAYMENT_REMINDERS:
            analyzed = tools.get_overdue_customers(interpreted.filters.top_n)
            summary = f"Prepared {len(analyzed)} deterministic reminder drafts for customers with current overdue exposure."
            actions.extend(self._reminder_proposal(plan_id, item, tools.get_customer(item.entity_id), created_at, tools.simulation_date) for item in analyzed)

        if not actions and intent is not CommandIntentType.UNKNOWN and not warnings:
            warnings.append("No current data matched the command filters; no action was invented.")

        requires_confirmation = any(action.requires_confirmation for action in actions)
        if requires_confirmation:
            mode = ExecutionMode.CONFIRMATION_REQUIRED
            expires_at = created_at + timedelta(minutes=PLAN_TTL_MINUTES)
        elif any(action.execution_mode is ExecutionMode.PREPARE for action in actions):
            mode = ExecutionMode.PREPARE
            expires_at = None
        else:
            mode = ExecutionMode.READ_ONLY
            expires_at = None
        entities = [
            EntityReference(entity_type=item.entity_type, entity_id=item.entity_id, display_name=item.entity_name)
            for item in analyzed
        ]
        plan = CommandPlan(
            plan_id=plan_id,
            created_at=created_at,
            expires_at=expires_at,
            intent=intent,
            entities=entities,
            filters=interpreted.filters,
            reasoning=interpreted.reasoning + [self._plan_reason(actions)],
            proposed_actions=actions,
            requires_confirmation=requires_confirmation,
            execution_mode=mode,
        )
        if evidence.records_inspected == 0 and analyzed:
            evidence = QueryEvidence(
                records_inspected=len(analyzed), records_matched=len(analyzed), records_returned=len(analyzed),
                ranking=self._ranking_evidence(analyzed), latest_cycle=tools.latest_cycle_evidence(analyzed),
            )
        return PlanningOutput(plan=plan, analyzed_entities=analyzed, understanding_summary=summary, warnings=warnings, query_evidence=evidence)

    def _execution_evidence(
        self,
        execution: QueryExecution,
        analyzed: list[IntelligenceResult],
        tools: CommandTools,
        stored_priorities: dict[str, str] | None = None,
    ) -> QueryEvidence:
        return QueryEvidence(
            records_inspected=execution.inspected,
            records_matched=execution.matched,
            records_excluded=execution.inspected - execution.matched,
            records_returned=len(analyzed),
            inspection_scope=execution.scope,
            exclusions=[ExclusionCount(reason=reason, count=count) for reason, count in execution.exclusions],
            ranking=self._ranking_evidence(analyzed, stored_priorities),
            latest_cycle=tools.latest_cycle_evidence(analyzed),
        )

    @staticmethod
    def _ranking_evidence(results: list[IntelligenceResult], stored_priorities: dict[str, str] | None = None) -> list[RankingEvidence]:
        rows = []
        for rank, result in enumerate(results, start=1):
            metrics = result.metrics
            facts = []
            if metrics.overdue_exposure > 0:
                facts.append(f"INR {metrics.overdue_exposure} overdue across {metrics.overdue_invoice_count} invoice(s)")
            if metrics.max_days_overdue:
                facts.append(f"Oldest balance is {metrics.max_days_overdue} days overdue")
            if metrics.broken_promise_count:
                facts.append(f"{metrics.broken_promise_count} broken payment promise(s)")
            if metrics.days_since_last_payment is None:
                facts.append("No payment activity recorded")
            elif metrics.days_since_last_payment < 30:
                facts.append(f"Payment activity recorded {metrics.days_since_last_payment} days ago")
            if metrics.active_promise_count:
                facts.append(f"{metrics.active_promise_count} active payment promise(s)")
            if metrics.active_dispute_count:
                facts.append(f"{metrics.active_dispute_count} active dispute blocker(s)")
            blocker = (
                "High risk, but standard recovery is blocked by an active dispute."
                if metrics.active_dispute_count else
                "Exposure remains at risk, but the current payment promise is still being monitored."
                if metrics.active_promise_count else None
            )
            rows.append(RankingEvidence(
                entity_id=result.entity_id, rank=rank, score=result.score, raw_score=result.raw_score,
                severity=result.level, stored_workflow_priority=(stored_priorities or {}).get(result.entity_id),
                facts=facts[:5], blocker=blocker, decision=f"{result.recommendation.title}: {result.recommendation.explanation}",
            ))
        return rows

    @staticmethod
    def _proposal_id(plan_id: UUID, target_id: str, action: ProposalActionType) -> UUID:
        return uuid5(NAMESPACE_URL, f"reconmate/command/{plan_id}/{target_id}/{action.value}")

    def _portfolio_action(self, plan_id: UUID, customer_count: int) -> ActionProposal:
        action = ProposalActionType.ANALYZE_PORTFOLIO
        return ActionProposal(
            proposal_id=self._proposal_id(plan_id, "portfolio", action), action_type=action,
            target_type="PORTFOLIO", target_id="portfolio", title="Review portfolio intelligence",
            explanation=f"Phase A intelligence evaluated {customer_count} current customer portfolios.",
            priority=PriorityLevel.MEDIUM, risk_level=PriorityLevel.MEDIUM,
            execution_mode=ExecutionMode.READ_ONLY, executable=True, requires_confirmation=False,
        )

    def _query_count_action(self, plan_id: UUID, count: int, entity_label: str) -> ActionProposal:
        action = ProposalActionType.ANALYZE_PORTFOLIO
        return ActionProposal(
            proposal_id=self._proposal_id(plan_id, f"count/{entity_label}", action), action_type=action,
            target_type="PORTFOLIO", target_id="portfolio", title=f"{count} matching {entity_label}",
            explanation=f"The count was calculated from current persisted records after applying every structured query condition.",
            priority=PriorityLevel.MEDIUM, risk_level=PriorityLevel.MEDIUM,
            execution_mode=ExecutionMode.READ_ONLY, executable=True, requires_confirmation=False,
        )

    def _customer_review(self, plan_id: UUID, result: IntelligenceResult) -> ActionProposal:
        action = ProposalActionType.REVIEW_CUSTOMER
        return ActionProposal(
            proposal_id=self._proposal_id(plan_id, result.entity_id, action), action_type=action,
            target_type="CUSTOMER", target_id=result.entity_id, title=f"Review {result.entity_name}",
            explanation=self._factor_explanation(result), priority=result.level, risk_level=result.level,
            execution_mode=ExecutionMode.READ_ONLY, executable=True, requires_confirmation=False,
        )

    def _analysis_action(
        self,
        plan_id: UUID,
        result: IntelligenceResult,
        action: ProposalActionType,
    ) -> ActionProposal:
        return ActionProposal(
            proposal_id=self._proposal_id(plan_id, result.entity_id, action), action_type=action,
            target_type=result.entity_type, target_id=result.entity_id,
            title=f"Explain {result.entity_name}", explanation=self._factor_explanation(result),
            priority=result.level, risk_level=result.level, execution_mode=ExecutionMode.READ_ONLY,
            executable=True, requires_confirmation=False,
        )

    def _case_analysis_action(self, plan_id: UUID, result: IntelligenceResult, case) -> ActionProposal:
        proposal = self._analysis_action(plan_id, result, ProposalActionType.ANALYZE_CASE)
        if case is None:
            return proposal
        stored_level = self._stored_level(case.priority)
        effective_level = max((result.level, stored_level), key=lambda level: list(PriorityLevel).index(level))
        recorded_reason = next((action.reason for action in case.actions if action.reason), None)
        context = f" Stored workflow priority is {case.priority.value}."
        if recorded_reason:
            context += f" Recorded case context: {recorded_reason}"
        return proposal.model_copy(update={
            "priority": effective_level,
            "risk_level": effective_level,
            "explanation": proposal.explanation + context,
        })

    def _case_recovery_proposal(
        self,
        plan_id: UUID,
        candidate: CaseCandidate,
        *,
        follow_up: bool = False,
    ) -> ActionProposal:
        recommendation = candidate.recommendation
        if recommendation.recommended_action is RecommendedAction.HOLD_FOR_DISPUTE:
            action = ProposalActionType.REVIEW_DISPUTE
            return ActionProposal(
                proposal_id=self._proposal_id(plan_id, str(candidate.case.id), action), action_type=action,
                target_type="RECOVERY_CASE", target_id=str(candidate.case.id), title="Review dispute before recovery",
                explanation=recommendation.operator_explanation, priority=candidate.risk_level,
                risk_level=candidate.risk_level, execution_mode=ExecutionMode.PREPARE,
                executable=False, requires_confirmation=False,
                limitations=["The active dispute blocks standard collection outreach."],
            )
        if recommendation.recommended_action is RecommendedAction.MONITOR_ACTIVE_PROMISE:
            action = ProposalActionType.MONITOR_PROMISE
            return ActionProposal(
                proposal_id=self._proposal_id(plan_id, str(candidate.case.id), action), action_type=action,
                target_type="RECOVERY_CASE", target_id=str(candidate.case.id), title="Monitor active payment promise",
                explanation=recommendation.operator_explanation, priority=candidate.risk_level,
                risk_level=candidate.risk_level, execution_mode=ExecutionMode.READ_ONLY,
                executable=True, requires_confirmation=False,
                limitations=["No follow-up is dispatched before the promise deadline."],
            )
        if recommendation.recommended_action is RecommendedAction.NO_ACTION_REQUIRED:
            action = ProposalActionType.REVIEW_CASE
            return ActionProposal(
                proposal_id=self._proposal_id(plan_id, str(candidate.case.id), action), action_type=action,
                target_type="RECOVERY_CASE", target_id=str(candidate.case.id), title="No recovery action required",
                explanation=recommendation.operator_explanation, priority=candidate.risk_level,
                risk_level=candidate.risk_level, execution_mode=ExecutionMode.READ_ONLY,
                executable=True, requires_confirmation=False,
            )
        action = ProposalActionType.PREPARE_FOLLOW_UP if follow_up else ProposalActionType.PREPARE_RECOVERY_ACTION
        return ActionProposal(
            proposal_id=self._proposal_id(plan_id, str(candidate.case.id), action), action_type=action,
            target_type="RECOVERY_CASE", target_id=str(candidate.case.id),
            title="Prepare operator follow-up" if follow_up else "Prepare recovery workflow action",
            explanation=recommendation.operator_explanation, priority=candidate.risk_level,
            risk_level=candidate.risk_level, execution_mode=ExecutionMode.CONFIRMATION_REQUIRED,
            executable=True, requires_confirmation=True,
            workflow_recommendation_action=recommendation.recommended_action.value,
            limitations=["Confirmation creates only an internal workflow action; it does not contact the customer."],
        )

    def _reminder_proposal(self, plan_id: UUID, result: IntelligenceResult, customer, prepared_at: datetime, simulation_date) -> ActionProposal:
        action = ProposalActionType.DRAFT_PAYMENT_REMINDER
        invoices = [] if customer is None else [invoice for invoice in customer.invoices if invoice.outstanding_amount > 0 and invoice.due_date < simulation_date]
        invoices.sort(key=lambda invoice: (invoice.due_date, invoice.invoice_number))
        invoice_facts = [{"invoice_number": invoice.invoice_number, "outstanding_amount": invoice.outstanding_amount, "due_date": invoice.due_date, "days_overdue": (simulation_date - invoice.due_date).days} for invoice in invoices]
        references = ", ".join(invoice.invoice_number for invoice in invoices)
        total = sum((invoice.outstanding_amount for invoice in invoices), start=0)
        broken = result.metrics.broken_promise_count > 0
        blocked = result.metrics.active_dispute_count > 0
        deferred = result.metrics.active_promise_count > 0
        missing_facts = not invoices
        status = "BLOCKED" if blocked else "DEFERRED" if deferred else "UNAVAILABLE" if missing_facts else "PREPARED_FOR_REVIEW"
        reason = "An active dispute requires operator review before payment outreach." if blocked else "An active payment promise is still being monitored; a reminder is not appropriate yet." if deferred else "No current overdue invoice facts were available for a grounded reminder." if missing_facts else "Current overdue invoices have no active dispute or active promise blocking an operator-reviewed reminder."
        tone = "Firm factual follow-up" if broken else "Professional payment-status follow-up"
        body = None if blocked or deferred or missing_facts else (
            f"Hello {result.entity_name},\n\nOur records show {references} with a total outstanding balance of INR {total:.2f}. "
            f"The oldest referenced invoice is {max((simulation_date - invoice.due_date).days for invoice in invoices)} days overdue. "
            + ("A previously recorded payment promise has passed without matching payment evidence. " if broken else "")
            + "Please confirm the current payment status and expected resolution date.\n\nThank you."
        )
        return ActionProposal(
            proposal_id=self._proposal_id(plan_id, result.entity_id, action), action_type=action,
            target_type="CUSTOMER", target_id=result.entity_id,
            title=f"Draft payment reminder for {result.entity_name}",
            explanation=(
                f"Prepare a factual reminder referencing {result.metrics.overdue_invoice_count} overdue invoice(s) "
                f"and {result.metrics.overdue_exposure} in overdue exposure."
            ),
            priority=result.level, risk_level=result.level, execution_mode=ExecutionMode.PREPARE,
            executable=True, requires_confirmation=False,
            reminder_artifact={"status": status, "customer_name": result.entity_name, "account_reference": customer.account_reference if customer else "", "invoices": invoice_facts, "total_outstanding": total, "promise_state": "BROKEN" if broken else "ACTIVE" if deferred else "NONE", "dispute_state": "ACTIVE" if blocked else "NONE", "intended_channel": "Operator-selected channel", "purpose": "Request payment status and expected resolution", "tone": tone, "prepared_at": prepared_at, "body": body, "reason": reason},
            limitations=["Draft preparation does not send email, SMS, WhatsApp, or a payment link."],
        )

    @staticmethod
    def _factor_explanation(result: IntelligenceResult) -> str:
        if not result.factors:
            return result.recommendation.explanation
        factors = "; ".join(item.explanation for item in result.factors[:3])
        return f"Score {result.score}/100 ({result.level.value}) because {factors}"

    @staticmethod
    def _plan_reason(actions: list[ActionProposal]) -> str:
        if not actions:
            return "No action proposal was generated because no supported data matched the command."
        confirmations = sum(action.requires_confirmation for action in actions)
        return (
            f"Generated {len(actions)} bounded proposals; {confirmations} require explicit confirmation."
        )

    @staticmethod
    def _stored_level(priority: RecoveryPriority) -> PriorityLevel:
        return {
            RecoveryPriority.LOW: PriorityLevel.LOW,
            RecoveryPriority.NORMAL: PriorityLevel.MEDIUM,
            RecoveryPriority.HIGH: PriorityLevel.HIGH,
            RecoveryPriority.CRITICAL: PriorityLevel.CRITICAL,
        }[priority]
