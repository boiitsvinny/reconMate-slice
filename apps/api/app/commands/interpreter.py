"""Deterministic natural-language boundary for composable ReconMate queries."""

from __future__ import annotations

from abc import ABC, abstractmethod
import re

from app.commands.schemas import (
    CommandFilters, CommandIntent, CommandIntentType, CommandRequest, CommandScope,
    QueryEntity, QuerySort, QueryTimeScope, StructuredQuery,
)
from app.intelligence.operational_schemas import PriorityLevel


class BaseCommandInterpreter(ABC):
    @abstractmethod
    def interpret(self, request: CommandRequest) -> CommandIntent:
        """Convert user wording into a bounded, structured intent."""


class FutureLLMCommandInterpreter(BaseCommandInterpreter):
    def interpret(self, request: CommandRequest) -> CommandIntent:
        raise NotImplementedError("An external language-model interpreter is intentionally not configured.")


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20, "twenty five": 25, "fifty": 50,
}
_QUERY_OPERATIONS = ("show", "list", "give", "which", "who", "find", "rank", "top", "count", "how many", "summarize", "summary", "explain")
_PREDICTIVE = ("churn", "next quarter", "forecast", "predict", "likelihood", "probability", "will pay", "future revenue")
_UNSUPPORTED_DOMAINS = ("weather", "sport", "sports", "football", "cricket", "investment", "investments", "stock", "stocks", "crypto", "cryptocurrency")
_DOMAIN_CONCEPTS = (
    "customer", "customers", "account", "invoice", "invoices", "receivable", "receivables",
    "collection", "collections", "overdue", "exposure", "payment", "payments", "promise", "promises",
    "dispute", "disputes", "recovery", "risk", "risky", "riskiest", "priority", "priorities",
    "escalation", "actionable", "monitoring", "latest cycle", "last cycle",
)
_BROAD_FOCUS_PHRASES = (
    "focus on", "need my attention", "needs my attention", "need attention", "needs attention",
    "requiring operator attention", "require operator attention", "should collections work on",
    "worst case",
)


class RuleBasedCommandInterpreter(BaseCommandInterpreter):
    """Compose a query from normalized domain concepts instead of matching sentences."""

    def interpret(self, request: CommandRequest) -> CommandIntent:
        text = self._normalize(request.command)
        unsupported_constraints = self._unsupported_constraints(text)
        if unsupported_constraints:
            named = ", ".join(unsupported_constraints)
            return self._unknown(
                CommandFilters(),
                StructuredQuery(),
                f"Unsupported query constraint(s): {named}. ReconMate cannot apply these from the current receivables model, so no part of the request was silently dropped.",
            )
        query = self._structured_query(text)
        filters = self._legacy_filters(query, text)

        if self._has(text, _UNSUPPORTED_DOMAINS):
            return self._unknown(filters, query, "ReconMate only queries persisted receivables and recovery facts; this request belongs to an unsupported domain.")
        if self._has(text, _PREDICTIVE):
            return self._unknown(filters, query, "ReconMate cannot answer predictive requests from the current receivables model. Supported dimensions include current risk, exposure, invoices, promises, disputes, payments, and recovery state.")
        if self._has(text, ("improved", "improvement", "worsened", "deteriorated")):
            return self._unknown(filters, query, "ReconMate can show factual latest-cycle changes, but directional improvement or deterioration is not a supported query filter.")
        conflict = self._query_conflict(text, query)
        if conflict:
            return self._unknown(filters, query, conflict)

        explanation = self._has(text, ("why", "explain", "reason", "what makes"))
        if explanation and request.context_case_id is not None:
            return self._intent(CommandIntentType.EXPLAIN_RECOMMENDATION, .97, CommandScope.CASE, filters, query, "The request asks for an explanation of the selected case's current recommendation.")
        if (explanation or "analy" in text) and request.context_customer_id is not None:
            return self._intent(CommandIntentType.CUSTOMER_ANALYSIS, .96, CommandScope.CUSTOMER, filters, query, "The request asks for analysis of the selected customer context.")
        if "analy" in text and request.context_case_id is not None:
            return self._intent(CommandIntentType.CASE_ANALYSIS, .96, CommandScope.CASE, filters, query, "The request asks for analysis of the selected recovery case.")
        if (explanation or "analy" in text) and self._has(text, ("this customer", "customer", "account")) and request.context_customer_id is None and not self._has(text, _QUERY_OPERATIONS):
            return self._unknown(filters, query, "Customer analysis requires context_customer_id.")
        if (explanation or "analy" in text) and "case" in text and request.context_case_id is None and not self._has(text, _QUERY_OPERATIONS):
            return self._unknown(filters, query, "Case analysis requires context_case_id.")

        reminder = "reminder" in text and self._has(text, ("draft", "prepare", "create"))
        recovery_prepare = self._has(text, ("prepare recovery", "prepare escalation", "create recovery", "recovery action", "recovery work"))
        follow_up = self._has(text, ("follow up", "contact again", "chase", "needs a response", "waiting for a response"))
        if recovery_prepare and follow_up:
            return self._unknown(filters, query, "This request could mean preparing recovery workflow work or preparing follow-ups. Ask for one controlled action explicitly.")
        if reminder:
            query = query.model_copy(update={"overdue": True})
            filters = self._legacy_filters(query, text)
            return self._intent(CommandIntentType.PREPARE_PAYMENT_REMINDERS, .98, CommandScope.PORTFOLIO, filters, query, "The operator explicitly requested prepared payment-reminder drafts.")
        if recovery_prepare:
            return self._intent(CommandIntentType.PREPARE_RECOVERY_ACTIONS, .97, CommandScope.PORTFOLIO, filters, query, "The operator explicitly requested preparation of controlled recovery workflow work.")
        if follow_up:
            if query.broken_promise is not True:
                query = query.model_copy(update={"broken_promise": True})
                filters = self._legacy_filters(query, text)
            return self._intent(CommandIntentType.PREPARE_FOLLOW_UPS, .96, CommandScope.PORTFOLIO, filters, query, "The operator explicitly requested prepared follow-up work; execution guardrails remain separate.")

        if "portfolio" in text and self._has(text, ("analyze", "analysis", "overview", "health", "summarize", "summary")) and not self._has_query_condition(query):
            return self._intent(CommandIntentType.PORTFOLIO_ANALYSIS, .93, CommandScope.PORTFOLIO, filters, query, "The request asks for a current portfolio-level summary.")

        if self._direct_invoice_request(text):
            return self._unknown(filters, query, "The command result contract currently returns customer or recovery-case intelligence, not standalone invoice rows. Ask for customers with the invoice condition instead.")

        if not self._has_domain_evidence(text, query):
            return self._unknown(filters, query, "ReconMate cannot answer this from the current receivables and recovery model. Supported dimensions include overdue exposure, payments, promises, disputes, recovery state, risk, and latest operational changes.")

        recognized = (
            self._has(text, _QUERY_OPERATIONS)
            or self._has_query_condition(query)
            or self._has(text, _BROAD_FOCUS_PHRASES)
            or self._has(text, ("risk", "risky", "riskiest", "exposure", "priority", "attention", "escalation"))
        )
        if not recognized:
            return self._unknown(filters, query, "ReconMate could not map this wording to current receivables, promise, dispute, payment, risk, or recovery dimensions.")

        if query.broken_promise is True and query.entity is QueryEntity.CUSTOMERS:
            intent = CommandIntentType.REVIEW_BROKEN_PROMISES
            reason = "The query targets customers with factual broken-promise state and composes any additional filters or exclusions."
        else:
            intent = CommandIntentType.PRIORITIZE_CASES
            reason = "The request was normalized into a bounded query over current operational intelligence and persisted receivables facts."
        return self._intent(intent, .92, CommandScope.PORTFOLIO, filters, query, reason)

    def _structured_query(self, text: str) -> StructuredQuery:
        case_target = self._has(text, ("case", "recovery case"))
        entity = QueryEntity.RECOVERY_CASES if case_target else QueryEntity.CUSTOMERS
        limit = self._limit(text)
        risk_levels = self._risk_levels(text)
        dispute_excluded = bool(re.search(r"\b(?:without|excluding|exclude|no) (?:active )?disputes?\b|\bundisputed\b", text))
        promise_excluded = bool(re.search(r"\b(?:without|excluding|exclude|no) active (?:payment )?promises?\b", text))
        no_recent_payment = bool(re.search(r"\b(?:no|without) recent payments?\b", text))
        active_dispute = False if dispute_excluded else True if re.search(r"\b(?:active )?disput(?:e|ed|es)\b", text) else None
        active_promise = False if promise_excluded else True if re.search(r"\bactive (?:payment )?promises?\b|\bvalid promises?\b", text) else None
        recent_payment = False if no_recent_payment else True if re.search(r"\brecent (?:partial )?payments?\b|\blatest payment activity\b", text) else None
        decision_changed = True if re.search(r"\b(?:decision|recommendation)s? changed\b|\bchanged (?:decision|recommendation)s?\b", text) else None
        decision_held = True if re.search(r"\b(?:decision|recommendation)s? (?:held|unchanged|remained)\b|\bheld after (?:a )?fact change\b", text) else None

        if self._has(text, ("exposure", "balance", "amount")):
            sort_by = QuerySort.OVERDUE_EXPOSURE if "overdue" in text else QuerySort.TOTAL_EXPOSURE
        elif self._has(text, ("oldest", "longest overdue", "days overdue")):
            sort_by = QuerySort.DAYS_OVERDUE
        elif recent_payment is not None and self._has(text, ("most recent", "latest")):
            sort_by = QuerySort.LAST_PAYMENT
        else:
            sort_by = QuerySort.RISK_SCORE
        descending = not self._has(text, ("lowest", "least", "smallest", "ascending"))
        if sort_by is QuerySort.LAST_PAYMENT and recent_payment is True:
            descending = False
        more_days = re.search(r"\b(?:more than|over) (\d{1,3}) days? overdue\b", text)
        fewer_days = re.search(r"\b(?:less than|under) (\d{1,3}) days? overdue\b", text)
        more_score = re.search(r"\b(?:risk )?score (?:more than|over) (\d{1,3})\b", text)
        fewer_score = re.search(r"\b(?:risk )?score (?:less than|under) (\d{1,3})\b", text)

        return StructuredQuery(
            entity=entity,
            risk_levels=risk_levels,
            overdue=True if "overdue" in text else None,
            broken_promise=True if re.search(r"\b(?:broken|missed|failed) (?:payment |their )?promises?\b|\bbroke (?:their |a )?promises?\b|\bpromises? (?:were|was|are|is) (?:broken|missed)\b|\bpromised to pay but did not\b|\bpromise to pay but did not\b", text) else None,
            active_promise=active_promise,
            active_dispute=active_dispute,
            partial_payment=True if re.search(r"\bpartial(?:ly)? paid\b|\bpartial payments?\b", text) else None,
            recent_payment=recent_payment,
            actionable=True if "actionable" in text or self._has(text, ("needs action", "need action")) else None,
            blocked=True if "blocked" in text and not re.search(r"\b(?:without|exclude|excluding) blocked\b", text) else False if re.search(r"\b(?:without|exclude|excluding) blocked\b", text) else None,
            monitoring=True if "monitoring" in text or "monitor" in text else None,
            decision_changed=decision_changed,
            decision_held=decision_held,
            min_days_overdue=int(more_days.group(1)) + 1 if more_days else None,
            max_days_overdue=max(0, int(fewer_days.group(1)) - 1) if fewer_days else None,
            min_score=min(100, int(more_score.group(1)) + 1) if more_score else None,
            max_score=min(100, max(0, int(fewer_score.group(1)) - 1)) if fewer_score else None,
            sort_by=sort_by,
            descending=descending,
            limit=limit,
            time_scope=QueryTimeScope.LATEST_CYCLE if decision_changed or decision_held or self._has(text, ("after latest cycle", "latest cycle", "last cycle", "after fact change")) else QueryTimeScope.CURRENT,
            count_only=self._has(text, ("count", "how many")),
            explanation_requested=self._has(text, ("why", "explain", "reason")),
        )

    @staticmethod
    def _risk_levels(text: str) -> list[PriorityLevel]:
        levels = []
        for word, level in (("critical", PriorityLevel.CRITICAL), ("medium", PriorityLevel.MEDIUM), ("low", PriorityLevel.LOW)):
            if re.search(rf"\b{word}(?: risk| priority)?\b", text):
                levels.append(level)
        # A named high-risk band remains a filter even when the operator also
        # asks for the top N. Superlatives such as "riskiest" only request order.
        if re.search(r"\bhigh(?: risk| priority)\b", text):
            levels.extend(level for level in (PriorityLevel.HIGH, PriorityLevel.CRITICAL) if level not in levels)
        return levels

    @staticmethod
    def _limit(text: str) -> int | None:
        digit = re.search(r"\b(?:top|first|limit)\s+(\d{1,3})\b|\b(\d{1,3})\s+(?:(?:high|low|critical)(?: risk)? )?(?:riskiest|highest|lowest|customers?|accounts?|cases?)\b", text)
        if digit:
            return min(int(digit.group(1) or digit.group(2)), 50)
        for word, value in sorted(_NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
            if re.search(rf"\b(?:top\s+)?{re.escape(word)}\s+(?:(?:high|low|critical)(?: risk)? )?(?:riskiest|highest|lowest|customers?|accounts?|cases?)\b", text):
                return value
        return None

    @staticmethod
    def _legacy_filters(query: StructuredQuery, text: str) -> CommandFilters:
        return CommandFilters(
            top_n=query.limit, risk_levels=query.risk_levels,
            overdue_only=query.overdue is True, broken_promises_only=query.broken_promise is True,
            include_all=bool(re.search(r"\ball\b", text)),
        )

    @staticmethod
    def _has_query_condition(query: StructuredQuery) -> bool:
        return bool(query.risk_levels or any(value is not None for value in (
            query.overdue, query.broken_promise, query.active_promise, query.active_dispute,
            query.partial_payment, query.recent_payment, query.actionable, query.blocked, query.monitoring,
            query.decision_changed, query.decision_held,
        )) or query.min_days_overdue is not None or query.max_days_overdue is not None
        or query.min_score is not None or query.max_score is not None
        or query.limit or query.count_only or query.time_scope is QueryTimeScope.LATEST_CYCLE)

    @staticmethod
    def _has_domain_evidence(text: str, query: StructuredQuery) -> bool:
        """Require receivables meaning; generic request verbs are never evidence."""
        return (
            RuleBasedCommandInterpreter._has(text, _DOMAIN_CONCEPTS)
            or RuleBasedCommandInterpreter._has(text, _BROAD_FOCUS_PHRASES)
            or any(value is not None for value in (
                query.overdue, query.broken_promise, query.active_promise, query.active_dispute,
                query.partial_payment, query.recent_payment, query.actionable, query.blocked, query.monitoring,
                query.decision_changed, query.decision_held,
                query.min_days_overdue, query.max_days_overdue, query.min_score, query.max_score,
            ))
        )

    @staticmethod
    def _direct_invoice_request(text: str) -> bool:
        return bool(re.search(r"\binvoices?\b", text)) and not bool(re.search(r"\b(?:customers?|accounts?|cases?)\b", text))

    @staticmethod
    def _normalize(command: str) -> str:
        command = command.replace(">", " more than ").replace("<", " less than ")
        text = command.lower().replace("â€™", "'").replace("’", "'")
        text = re.sub(r"[^a-z0-9']+", " ", text)
        replacements = (
            (r"\banyone\b|\bpeople\b", "customers"),
            (r"\baccounts?\b", "account"),
            (r"\bcases?\b", "case"),
            (r"\bfollow\s*ups?\b", "follow up"),
            (r"\bwho'?s\b", "who is"),
            (r"\bdidn'?t\b", "did not"),
        )
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        return " ".join(text.split())

    @staticmethod
    def _query_conflict(text: str, query: StructuredQuery) -> str | None:
        if re.search(r"\b(?:more than|over|less than|under)\s+[a-z]+\s+days? overdue\b", text):
            return "The overdue-day filter is malformed. Use a numeric value such as 'over 90 days overdue'."
        dispute_excluded = bool(re.search(r"\b(?:without|excluding|exclude|no) (?:active )?disputes?\b|\bundisputed\b", text))
        dispute_included = bool(re.search(r"\bwith (?:active )?disputes?\b|\bhaving (?:active )?disputes?\b", text))
        promise_excluded = bool(re.search(r"\b(?:without|excluding|exclude|no) active (?:payment )?promises?\b", text))
        promise_included = bool(re.search(r"\bwith active (?:payment )?promises?\b|\bhaving active (?:payment )?promises?\b", text))
        recent_excluded = bool(re.search(r"\b(?:no|without) recent payments?\b", text))
        recent_included = bool(re.search(r"\bwith recent (?:partial )?payments?\b|\bhaving recent (?:partial )?payments?\b", text))
        if dispute_excluded and dispute_included:
            return "The query both includes and excludes active disputes. Choose one condition; no filter was weakened."
        if promise_excluded and promise_included:
            return "The query both includes and excludes active promises. Choose one condition; no filter was weakened."
        if recent_excluded and recent_included:
            return "The query both includes and excludes recent payments. Choose one condition; no filter was weakened."
        if query.actionable is True and query.blocked is True:
            return "A recovery record cannot be both actionable and blocked under the current decision rules. Choose one state."
        if query.decision_changed is True and query.decision_held is True:
            return "A latest-cycle decision cannot be both changed and held. Choose one transition condition."
        if query.min_days_overdue is not None and query.max_days_overdue is not None and query.min_days_overdue > query.max_days_overdue:
            return "The minimum overdue-day filter exceeds the maximum. Correct the numeric range; no filter was weakened."
        if query.min_score is not None and query.max_score is not None and query.min_score > query.max_score:
            return "The minimum score filter exceeds the maximum. Correct the numeric range; no filter was weakened."
        return None

    @staticmethod
    def _unsupported_constraints(text: str) -> list[str]:
        """Reject plausible business filters that are absent from persisted facts."""
        unsupported: list[str] = []
        if re.search(r"\bcredit (?:scores?|ratings?|bureau)\b|\bcibil\b", text):
            unsupported.append("credit score")
        geography = re.search(
            r"\b(?:in|from|located in|based in) (?!disputes?\b|recovery\b|collections?\b|arrears\b|payments?\b|promises?\b|monitoring\b|workflow\b|portfolio\b|critical\b|high\b|medium\b|low\b)([a-z][a-z ]{1,30}?)(?=\s+(?:with|without|who|that|and|or|having|where)\b|$)|"
            r"\b(?:city|country|region|province|postal code|zip code|geography|location|customer state|billing state)\b",
            text,
        )
        if geography:
            place = geography.group(1).strip() if geography.lastindex and geography.group(1) else None
            unsupported.append(f"geography ({place})" if place else "geography")
        if re.search(r"\b(?:age|gender|sex|ethnicity|race|religion|marital status|demographic|demographics)\b", text):
            unsupported.append("demographic attributes")
        return unsupported

    @staticmethod
    def _has(text: str, concepts: tuple[str, ...]) -> bool:
        return any(re.search(rf"\b{re.escape(concept)}\b", text) for concept in concepts)

    @staticmethod
    def _intent(intent: CommandIntentType, confidence: float, scope: CommandScope, filters: CommandFilters, query: StructuredQuery, reason: str) -> CommandIntent:
        return CommandIntent(intent=intent, confidence=confidence, scope=scope, filters=filters, query=query, reasoning=[reason])

    @staticmethod
    def _unknown(filters: CommandFilters, query: StructuredQuery, guidance: str) -> CommandIntent:
        return CommandIntent(intent=CommandIntentType.UNKNOWN, confidence=.20, scope=CommandScope.PORTFOLIO, filters=filters, query=query,
                             reasoning=["The request could not be mapped safely to supported current-state dimensions."], guidance=guidance)
