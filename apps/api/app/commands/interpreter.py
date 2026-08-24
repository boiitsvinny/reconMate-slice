"""Replaceable command interpretation boundary with deterministic Phase B rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
import re

from app.commands.schemas import (
    CommandFilters,
    CommandIntent,
    CommandIntentType,
    CommandRequest,
    CommandScope,
)
from app.intelligence.operational_schemas import PriorityLevel


class BaseCommandInterpreter(ABC):
    @abstractmethod
    def interpret(self, request: CommandRequest) -> CommandIntent:
        """Convert user wording into a bounded, structured intent."""


class FutureLLMCommandInterpreter(BaseCommandInterpreter):
    """Explicit extension point; no external provider is configured in Phase B."""

    def interpret(self, request: CommandRequest) -> CommandIntent:
        raise NotImplementedError("An LLM command interpreter is intentionally not implemented in Phase B.")


class RuleBasedCommandInterpreter(BaseCommandInterpreter):
    def interpret(self, request: CommandRequest) -> CommandIntent:
        text = " ".join(request.command.lower().split())
        filters = self._filters(text)

        explanation_words = ("why", "explain", "reason", "recommendation")
        case_words = ("case", "recovery")
        customer_words = ("customer", "account")
        broken_words = (
            "broken promise", "broken promises", "promise is broken", "promises are broken",
            "missed payment promise", "missed promises",
        )
        reminder_words = ("draft reminder", "draft reminders", "payment reminder", "payment reminders", "overdue reminder")
        recovery_prepare_words = ("prepare recovery action", "prepare recovery actions", "prepare recovery plan", "critical recoveries")
        follow_up_words = ("follow up", "follow-up", "followups", "follow ups")
        prioritize_words = (
            "focus on", "should i focus", "prioritize", "priority", "highest risk",
            "high-risk", "critical customer", "urgent case", "urgent customer", "top risk",
        )

        if any(word in text for word in explanation_words):
            if request.context_case_id is not None and any(word in text for word in case_words):
                return self._intent(CommandIntentType.EXPLAIN_RECOMMENDATION, .96, CommandScope.CASE, filters,
                                    "Explanation wording and case context were both provided.")
            if request.context_customer_id is not None and any(word in text for word in customer_words):
                return self._intent(CommandIntentType.CUSTOMER_ANALYSIS, .93, CommandScope.CUSTOMER, filters,
                                    "Explanation wording and customer context were both provided.")
            return self._unknown(filters, "An explanation command needs a context_case_id or context_customer_id.")

        if any(word in text for word in reminder_words):
            filters.overdue_only = True
            return self._intent(CommandIntentType.PREPARE_PAYMENT_REMINDERS, .96, CommandScope.PORTFOLIO, filters,
                                "The command explicitly asks to draft or prepare overdue payment reminders.")

        if any(word in text for word in broken_words):
            filters.broken_promises_only = True
            if any(word in text for word in follow_up_words):
                return self._intent(CommandIntentType.PREPARE_FOLLOW_UPS, .97, CommandScope.PORTFOLIO, filters,
                                    "The command combines broken-promise scope with follow-up preparation.")
            return self._intent(CommandIntentType.REVIEW_BROKEN_PROMISES, .96, CommandScope.PORTFOLIO, filters,
                                "The command explicitly requests accounts with broken payment promises.")

        if any(word in text for word in recovery_prepare_words):
            return self._intent(CommandIntentType.PREPARE_RECOVERY_ACTIONS, .97, CommandScope.PORTFOLIO, filters,
                                "The command explicitly requests preparation of recovery work.")

        if "analy" in text and any(word in text for word in customer_words):
            if request.context_customer_id is None:
                return self._unknown(filters, "Customer analysis requires context_customer_id.")
            return self._intent(CommandIntentType.CUSTOMER_ANALYSIS, .95, CommandScope.CUSTOMER, filters,
                                "The command asks for customer analysis and includes customer context.")

        if "analy" in text and "case" in text:
            if request.context_case_id is None:
                return self._unknown(filters, "Case analysis requires context_case_id.")
            return self._intent(CommandIntentType.CASE_ANALYSIS, .95, CommandScope.CASE, filters,
                                "The command asks for case analysis and includes case context.")

        if any(word in text for word in prioritize_words):
            return self._intent(CommandIntentType.PRIORITIZE_CASES, .92, CommandScope.PORTFOLIO, filters,
                                "The command asks for ranked operational focus or risk prioritization.")

        if "portfolio" in text and any(word in text for word in ("analyze", "analysis", "overview", "health")):
            return self._intent(CommandIntentType.PORTFOLIO_ANALYSIS, .90, CommandScope.PORTFOLIO, filters,
                                "The command requests a portfolio-level analysis.")

        return self._unknown(
            filters,
            "Supported commands include portfolio prioritization, customer or case analysis, broken-promise review, recovery preparation, and reminder drafting.",
        )

    @staticmethod
    def _filters(text: str) -> CommandFilters:
        match = re.search(r"\btop\s+(\d{1,3})\b", text)
        top_n = min(int(match.group(1)), 50) if match else None
        risk_levels: list[PriorityLevel] = []
        if "critical" in text:
            risk_levels.append(PriorityLevel.CRITICAL)
        if "high risk" in text or "high-risk" in text or "high priority" in text:
            risk_levels.append(PriorityLevel.HIGH)
            if PriorityLevel.CRITICAL not in risk_levels:
                risk_levels.append(PriorityLevel.CRITICAL)
        return CommandFilters(
            top_n=top_n,
            risk_levels=risk_levels,
            overdue_only="overdue" in text,
            broken_promises_only=(
                "broken promise" in text or "promise is broken" in text
                or "promises are broken" in text or "missed promise" in text
            ),
            include_all=bool(re.search(r"\ball\b", text)),
        )

    @staticmethod
    def _intent(
        intent: CommandIntentType,
        confidence: float,
        scope: CommandScope,
        filters: CommandFilters,
        reason: str,
    ) -> CommandIntent:
        return CommandIntent(intent=intent, confidence=confidence, scope=scope, filters=filters, reasoning=[reason])

    @staticmethod
    def _unknown(filters: CommandFilters, guidance: str) -> CommandIntent:
        return CommandIntent(
            intent=CommandIntentType.UNKNOWN,
            confidence=.20,
            scope=CommandScope.PORTFOLIO,
            filters=filters,
            reasoning=["The wording did not map safely to one supported command intent."],
            guidance=guidance,
        )
