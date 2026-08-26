from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes import commands as commands_route
from app.api.routes.workflow import _current_workspace_intelligence
from app.commands.interpreter import RuleBasedCommandInterpreter
from app.commands.planner import CommandPlanner
from app.commands.schemas import CommandIntentType, CommandRequest, ConfirmCommandRequest, ExecutionMode, InspectionScope, ProposalStatus, QueryEntity, QuerySort, QueryTimeScope, StructuredQuery
from app.commands.service import CommandService, EphemeralPlanRegistry
from app.commands.tools import CaseCandidate, CommandTools, QueryExecution
from app.db.session import get_db
from app.intelligence.operational_schemas import (
    ContributingFactor,
    IntelligenceMetrics,
    IntelligenceRecommendation,
    IntelligenceResult,
    IntelligenceSignal,
    PortfolioIntelligence,
    PriorityLevel,
    RecommendationAction,
    SignalType,
)
from app.intelligence.operational_service import evaluate_customer_intelligence
from app.main import app
from app.models.domain import AuditEvent, Customer, Invoice, InvoiceStatus, RecoveryAction, RecoveryActionStatus, RecoveryCase, RecoveryPriority, RecoveryState
from app.recommendations.schemas import RecommendedAction, RecommendationPriority, RecoveryRecommendation


TODAY = date(2026, 8, 1)
CUSTOMER_ID = uuid4()
CASE_ID = uuid4()
INVOICE_ID = uuid4()


def _intelligence(
    *,
    entity_type: str = "CUSTOMER",
    entity_id: UUID = CUSTOMER_ID,
    name: str = "Critical Test Account",
    score: int = 88,
    level: PriorityLevel = PriorityLevel.CRITICAL,
    broken: int = 1,
    overdue: Decimal = Decimal("450000"),
) -> IntelligenceResult:
    signal = IntelligenceSignal(
        type=SignalType.BROKEN_PROMISE,
        severity=PriorityLevel.HIGH,
        title="Broken payment promise",
        explanation="1 recorded payment promise was broken.",
        contributing_value=broken,
        calculated_at=TODAY,
    )
    factor = ContributingFactor(
        type=SignalType.BROKEN_PROMISE,
        title=signal.title,
        impact=PriorityLevel.HIGH,
        points=20,
        explanation=signal.explanation,
        contributing_value=broken,
    )
    return IntelligenceResult(
        entity_type=entity_type,
        entity_id=str(entity_id),
        entity_name=name,
        calculated_at=TODAY,
        score=score,
        level=level,
        metrics=IntelligenceMetrics(
            total_outstanding_amount=overdue,
            overdue_exposure=overdue,
            overdue_invoice_count=3 if overdue else 0,
            max_days_overdue=95 if overdue else 0,
            broken_promise_count=broken,
            active_promise_count=0,
            active_dispute_count=0,
            days_since_last_payment=70 if overdue else 1,
            active_recovery_case_count=1,
            stalled_recovery_case_count=0,
        ),
        signals=[signal] if broken else [],
        factors=[factor] if broken else [],
        recommendation=IntelligenceRecommendation(
            action=RecommendationAction.ESCALATE if level is PriorityLevel.CRITICAL else RecommendationAction.FOLLOW_UP,
            title="Escalate for review" if level is PriorityLevel.CRITICAL else "Follow up",
            explanation="Current factual conditions require operator attention.",
            priority_level=level,
            operator_confirmation_required=True,
        ),
    )


CUSTOMER_RESULT = _intelligence()
CASE_RESULT = _intelligence(
    entity_type="RECOVERY_CASE",
    entity_id=CASE_ID,
    name="Critical Test Account / TEST-INV",
    score=82,
)


def _case_candidate() -> CaseCandidate:
    customer = Customer(id=CUSTOMER_ID, name="Critical Test Account", account_reference="CMD-001")
    invoice = Invoice(
        id=INVOICE_ID,
        customer=customer,
        invoice_number="TEST-INV",
        issue_date=TODAY - timedelta(days=130),
        due_date=TODAY - timedelta(days=100),
        original_amount=Decimal("450000"),
        outstanding_amount=Decimal("450000"),
        status=InvoiceStatus.OVERDUE,
    )
    case = RecoveryCase(
        id=CASE_ID,
        customer=customer,
        invoice=invoice,
        current_state=RecoveryState.ESCALATED,
        priority=RecoveryPriority.CRITICAL,
        opened_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 31, tzinfo=UTC),
    )
    recommendation = RecoveryRecommendation(
        case_id=str(CASE_ID), customer_id=str(CUSTOMER_ID), customer_name=customer.name,
        recommended_action=RecommendedAction.PREPARE_ESCALATION,
        priority=RecommendationPriority.CRITICAL, human_approval_required=True,
        factual_reasons=["Severe overdue exposure."], communication_signals=[], blockers=[],
        relevant_exposure=Decimal("450000"), relevant_days_overdue=100,
        recovery_state=RecoveryState.ESCALATED.value,
        operator_explanation="Prepare this severe overdue case for human escalation approval.",
        operator_next_step="Create an internal escalation workflow for senior recovery review.",
        workflow_effect="Proceeding creates an internal controlled recovery workflow record for operator review.",
    )
    return CaseCandidate(case=case, intelligence=CASE_RESULT, recommendation=recommendation, risk_level=PriorityLevel.CRITICAL)


class FakeCommandTools:
    def __init__(self, _db=None):
        self.db = _db
        self.simulation_date = TODAY
        self.candidate = _case_candidate()

    def get_portfolio_intelligence(self):
        return PortfolioIntelligence(
            calculated_at=TODAY, customer_count=1, average_score=Decimal("88"),
            level_counts={level: int(level is PriorityLevel.CRITICAL) for level in PriorityLevel},
            highest_priority=[CUSTOMER_RESULT], customers=[CUSTOMER_RESULT],
        )

    def get_priority_customers(self, levels=None, top_n=None):
        results = [CUSTOMER_RESULT] if not levels or CUSTOMER_RESULT.level in levels else []
        return results[:top_n] if top_n is not None else results

    def get_customer_intelligence(self, customer_id):
        return CUSTOMER_RESULT if customer_id == CUSTOMER_ID else None

    def get_customer(self, customer_id):
        return self.candidate.case.customer if str(customer_id) == str(CUSTOMER_ID) else None

    def get_case_intelligence(self, case_id):
        return CASE_RESULT if case_id == CASE_ID else None

    def get_broken_promise_customers(self, top_n=None):
        results = [CUSTOMER_RESULT]
        return results[:top_n] if top_n is not None else results

    def get_overdue_customers(self, top_n=None):
        results = [CUSTOMER_RESULT]
        return results[:top_n] if top_n is not None else results

    def query_customer_intelligence(self, query):
        result = CUSTOMER_RESULT
        metrics = result.metrics
        matches = (
            (not query.risk_levels or result.level in query.risk_levels)
            and (query.overdue is not True or metrics.overdue_exposure > 0)
            and (query.broken_promise is not True or metrics.broken_promise_count > 0)
            and (query.active_promise is not True or metrics.active_promise_count > 0)
            and (query.active_dispute is not True or metrics.active_dispute_count > 0)
            and (query.active_dispute is not False or metrics.active_dispute_count == 0)
        )
        results = [result] if matches else []
        return results if query.count_only or query.limit is None else results[:query.limit]

    def query_recovery_candidates(self, query):
        results = self.get_recovery_candidates(levels=query.risk_levels or None, top_n=None)
        return results if query.count_only or query.limit is None else results[:query.limit]

    def execute_customer_query(self, query):
        records = self.query_customer_intelligence(query)
        return QueryExecution(records=records, inspected=1, matched=len(records), exclusions=[], scope=InspectionScope(customers=1, invoices=1, promises=1, recovery_cases=1))

    def execute_case_query(self, query):
        records = self.query_recovery_candidates(query)
        return QueryExecution(records=records, inspected=1, matched=len(records), exclusions=[], scope=InspectionScope(customers=1, invoices=1, promises=1, recovery_cases=1))

    def latest_cycle_evidence(self, _results):
        return None

    def get_recovery_candidates(self, levels=None, customer_ids=None, top_n=None):
        results = [self.candidate]
        if levels and self.candidate.risk_level not in levels:
            results = []
        if customer_ids is not None and str(CUSTOMER_ID) not in customer_ids:
            results = []
        return results[:top_n] if top_n is not None else results

    def get_case(self, case_id):
        return self.candidate.case if str(case_id) == str(CASE_ID) else None


class EmptyCommandTools(FakeCommandTools):
    def get_priority_customers(self, levels=None, top_n=None):
        return []

    def get_broken_promise_customers(self, top_n=None):
        return []

    def get_overdue_customers(self, top_n=None):
        return []

    def get_recovery_candidates(self, levels=None, customer_ids=None, top_n=None):
        return []

    def query_customer_intelligence(self, query):
        return []

    def query_recovery_candidates(self, query):
        return []


def _client(monkeypatch, tools_class=FakeCommandTools) -> TestClient:
    monkeypatch.setattr(commands_route, "CommandTools", tools_class)
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_interpreter_extracts_top_n_critical_and_handles_ambiguous_wording() -> None:
    interpreter = RuleBasedCommandInterpreter()
    intent = interpreter.interpret(CommandRequest(command="Prioritize the top 5 critical customers"))
    assert intent.intent is CommandIntentType.PRIORITIZE_CASES
    assert intent.filters.top_n == 5
    assert intent.filters.risk_levels == [PriorityLevel.CRITICAL]

    unknown = interpreter.interpret(CommandRequest(command="Handle collections for me"))
    assert unknown.intent is CommandIntentType.UNKNOWN
    assert unknown.confidence < .5
    assert unknown.guidance


@pytest.mark.parametrize(("command", "intent"), [
    ("Any followups required?", CommandIntentType.PREPARE_FOLLOW_UPS),
    ("Do I need to follow up with anyone?", CommandIntentType.PREPARE_FOLLOW_UPS),
    ("Who needs a follow-up?", CommandIntentType.PREPARE_FOLLOW_UPS),
    ("Who should I contact again?", CommandIntentType.PREPARE_FOLLOW_UPS),
    ("Any customers waiting for a response?", CommandIntentType.PREPARE_FOLLOW_UPS),
    ("Show me people I should chase", CommandIntentType.PREPARE_FOLLOW_UPS),
    ("Who should I focus on?", CommandIntentType.PRIORITIZE_CASES),
    ("What needs my attention?", CommandIntentType.PRIORITIZE_CASES),
    ("Which customers are risky?", CommandIntentType.PRIORITIZE_CASES),
    ("Who has broken their promise?", CommandIntentType.REVIEW_BROKEN_PROMISES),
    ("Who promised to pay but didn’t?", CommandIntentType.REVIEW_BROKEN_PROMISES),
    ("Prepare recovery work for critical accounts", CommandIntentType.PREPARE_RECOVERY_ACTIONS),
    ("What overdue customers need action?", CommandIntentType.PRIORITIZE_CASES),
    ("Show me the worst cases", CommandIntentType.PRIORITIZE_CASES),
    ("Who needs escalation?", CommandIntentType.PRIORITIZE_CASES),
    ("Draft payment reminders for overdue customers", CommandIntentType.PREPARE_PAYMENT_REMINDERS),
    ("Analyze portfolio health", CommandIntentType.PORTFOLIO_ANALYSIS),
])
def test_interpreter_accepts_realistic_operator_paraphrases(command: str, intent: CommandIntentType) -> None:
    assert RuleBasedCommandInterpreter().interpret(CommandRequest(command=command)).intent is intent


def test_interpreter_handles_competing_operational_intents_safely() -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command="Prepare recovery work and follow up with everyone"))
    assert result.intent is CommandIntentType.UNKNOWN
    assert result.guidance and "could mean" in result.guidance


def test_high_risk_filter_is_distinct_from_riskiest_ranking() -> None:
    interpreter = RuleBasedCommandInterpreter()
    commands = (
        "Show top 5 high-risk customers",
        "Give me the five riskiest accounts",
        "Which 5 customers have the highest current risk?",
    )
    queries = [interpreter.interpret(CommandRequest(command=command)).query for command in commands]
    assert all(query.entity is QueryEntity.CUSTOMERS for query in queries)
    assert all(query.limit == 5 and query.sort_by is QuerySort.RISK_SCORE and query.descending for query in queries)
    assert queries[0].risk_levels == [PriorityLevel.HIGH, PriorityLevel.CRITICAL]
    assert queries[1].risk_levels == []
    assert queries[2].risk_levels == []
    assert queries[1] == queries[2]


@pytest.mark.parametrize(("command", "levels", "sort_by"), [
    ("Show the 5 riskiest customers", [], QuerySort.RISK_SCORE),
    ("Show 5 high-risk customers", [PriorityLevel.HIGH, PriorityLevel.CRITICAL], QuerySort.RISK_SCORE),
    ("Show critical customers", [PriorityLevel.CRITICAL], QuerySort.RISK_SCORE),
    ("Show low-risk customers", [PriorityLevel.LOW], QuerySort.RISK_SCORE),
    ("Show customers with the highest score", [], QuerySort.RISK_SCORE),
    ("Show customers with the highest exposure", [], QuerySort.TOTAL_EXPOSURE),
])
def test_risk_and_ranking_phrases_have_explicit_semantics(command: str, levels: list[PriorityLevel], sort_by: QuerySort) -> None:
    query = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command)).query
    assert query.risk_levels == levels
    assert query.sort_by is sort_by
    assert query.descending is True


def test_ranking_ties_use_raw_score_then_stable_domain_facts() -> None:
    lower_raw = CUSTOMER_RESULT.model_copy(update={"entity_id": "b", "score": 100, "raw_score": 106})
    higher_raw = CUSTOMER_RESULT.model_copy(update={"entity_id": "c", "score": 100, "raw_score": 110})
    same_raw_lower_id = CUSTOMER_RESULT.model_copy(update={"entity_id": "a", "score": 100, "raw_score": 106})
    query = StructuredQuery(sort_by=QuerySort.RISK_SCORE, descending=True)
    ranked = sorted([lower_raw, higher_raw, same_raw_lower_id], key=lambda item: CommandTools._ranking_key(item, query))
    assert [item.entity_id for item in ranked] == ["c", "a", "b"]
    assert CommandTools.ranking_policy(query)[:2] == [
        "Displayed intelligence score (highest first)", "Raw intelligence score (highest first)",
    ]


@pytest.mark.parametrize(("command", "expected"), [
    ("Broken promises excluding disputes", {"broken_promise": True, "active_dispute": False}),
    ("Show overdue customers with active promises", {"overdue": True, "active_promise": True}),
    ("Highest exposure accounts", {"sort_by": QuerySort.TOTAL_EXPOSURE, "descending": True}),
    ("Customers with recent payment activity", {"recent_payment": True}),
    ("Actionable critical cases", {"entity": QueryEntity.RECOVERY_CASES, "actionable": True, "risk_levels": [PriorityLevel.CRITICAL]}),
    ("Top 10 overdue customers without active disputes", {"limit": 10, "overdue": True, "active_dispute": False}),
    ("Customers over 30 days overdue", {"min_days_overdue": 31, "overdue": True}),
    ("Customers with risk score over 80", {"min_score": 81}),
    ("Customers changed after latest cycle", {"time_scope": QueryTimeScope.LATEST_CYCLE}),
    ("Count customers with broken promises", {"count_only": True, "broken_promise": True}),
])
def test_interpreter_composes_independent_query_dimensions(command: str, expected: dict) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is not CommandIntentType.UNKNOWN
    for field, value in expected.items():
        assert getattr(result.query, field) == value


@pytest.mark.parametrize(("command", "expected"), [
    ("Show customers >90 days overdue", {"overdue": True, "min_days_overdue": 91}),
    ("Show customers with partial payments and no recent payments", {"partial_payment": True, "recent_payment": False}),
    ("Show blocked critical cases", {"entity": QueryEntity.RECOVERY_CASES, "blocked": True, "risk_levels": [PriorityLevel.CRITICAL]}),
    ("Show changed decisions", {"decision_changed": True, "time_scope": QueryTimeScope.LATEST_CYCLE}),
    ("Show decisions held after fact change", {"decision_held": True, "time_scope": QueryTimeScope.LATEST_CYCLE}),
])
def test_interpreter_preserves_hardening_query_semantics(command: str, expected: dict) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is not CommandIntentType.UNKNOWN
    for field, value in expected.items():
        assert getattr(result.query, field) == value


@pytest.mark.parametrize("command", [
    "Show customers with disputes and without disputes",
    "Show actionable blocked critical cases",
    "Show changed decisions and decisions held after fact change",
    "Show customers over many days overdue",
    "Show customers over 90 days overdue and under 30 days overdue",
])
def test_contradictory_or_malformed_queries_fail_without_weakening(command: str) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is CommandIntentType.UNKNOWN
    assert result.guidance


@pytest.mark.parametrize("command", [
    "Show the highest exposure investments",
    "Rank the riskiest stocks",
    "Show critical cryptocurrency positions",
    "List recent sports results",
])
def test_unrelated_domain_terms_override_accidental_financial_word_matches(command: str) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is CommandIntentType.UNKNOWN
    assert result.guidance and "unsupported domain" in result.guidance


@pytest.mark.parametrize("command", [
    "Which customers will churn next quarter?",
    "Predict who will pay next month",
    "Who improved after the latest cycle?",
    "Purple bananas dance quickly",
    "Show overdue invoices",
    "List weather forecasts for Bengaluru",
    "Write me a poem",
    "Tell me a joke",
    "What is the capital of France?",
    "Who will win the World Cup?",
    "Explain quantum mechanics",
    "Flibbertigibbet zorbles sideways",
])
def test_interpreter_rejects_unsupported_or_ungrounded_requests(command: str) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is CommandIntentType.UNKNOWN
    assert result.guidance


@pytest.mark.parametrize(("command", "constraint"), [
    ("Show critical customers in California", "geography"),
    ("Show overdue customers with credit score over 700", "credit score"),
])
def test_interpreter_rejects_unsupported_business_constraints_without_dropping_them(command: str, constraint: str) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is CommandIntentType.UNKNOWN
    assert result.guidance and constraint in result.guidance
    assert "silently dropped" in result.guidance


def test_interpreter_reports_every_unsupported_constraint_in_a_compound_request() -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(
        command="Show customers in California with credit scores under 500",
    ))
    assert result.intent is CommandIntentType.UNKNOWN
    assert result.guidance and "geography (california)" in result.guidance
    assert "credit score" in result.guidance


@pytest.mark.parametrize("command", [
    "Who should I focus on today?",
    "Which accounts need attention?",
    "Show recovery priorities",
    "What should collections work on?",
])
def test_interpreter_keeps_broad_but_grounded_focus_requests(command: str) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is CommandIntentType.PRIORITIZE_CASES


@pytest.mark.parametrize("command", [
    "Show me Bengaluru weather",
    "List the top 5 World Cup teams",
    "List critical weather alerts",
    "Find a joke",
    "Tell me the capital of France",
])
def test_generic_operations_do_not_supply_domain_evidence(command: str) -> None:
    result = RuleBasedCommandInterpreter().interpret(CommandRequest(command=command))
    assert result.intent is CommandIntentType.UNKNOWN


def test_composed_predicates_all_apply_to_the_same_grounded_result() -> None:
    query = StructuredQuery(broken_promise=True, active_dispute=False, recent_payment=True, min_days_overdue=30)
    assert CommandTools._matches(
        query, CUSTOMER_RESULT, partial=False, recent=True, blocked=False, monitoring=False, actionable=True,
    )
    disputed_metrics = CUSTOMER_RESULT.metrics.model_copy(update={"active_dispute_count": 1})
    disputed = CUSTOMER_RESULT.model_copy(update={"metrics": disputed_metrics})
    assert not CommandTools._matches(
        query, disputed, partial=False, recent=True, blocked=True, monitoring=False, actionable=False,
    )


def test_decision_transition_filters_are_independent_facts() -> None:
    changed = StructuredQuery(decision_changed=True, time_scope=QueryTimeScope.LATEST_CYCLE)
    held = StructuredQuery(decision_held=True, time_scope=QueryTimeScope.LATEST_CYCLE)
    common = {"partial": False, "recent": False, "blocked": False, "monitoring": False, "actionable": True}
    assert CommandTools._matches(changed, CUSTOMER_RESULT, decision_changed=True, decision_held=False, **common)
    assert not CommandTools._matches(changed, CUSTOMER_RESULT, decision_changed=False, decision_held=True, **common)
    assert CommandTools._matches(held, CUSTOMER_RESULT, decision_changed=False, decision_held=True, **common)


def test_latest_cycle_decision_sets_separate_changed_from_held() -> None:
    changed_id, held_id, new_id = map(str, (uuid4(), uuid4(), uuid4()))
    rows = [
        SimpleNamespace(payload={"cycle": 12, "entity_type": "CUSTOMER", "entity_id": changed_id, "previous_recommendation": "MONITOR", "classifications": ["RECOMMENDATION_CHANGED"]}),
        SimpleNamespace(payload={"cycle": 12, "entity_type": "CUSTOMER", "entity_id": held_id, "previous_recommendation": "FOLLOW_UP", "classifications": ["NO_MATERIAL_CHANGE"]}),
        SimpleNamespace(payload={"cycle": 12, "entity_type": "CUSTOMER", "entity_id": new_id, "previous_recommendation": None, "classifications": ["NO_MATERIAL_CHANGE"]}),
        SimpleNamespace(payload={"cycle": 11, "entity_type": "CUSTOMER", "entity_id": str(uuid4()), "previous_recommendation": "MONITOR", "classifications": ["RECOMMENDATION_CHANGED"]}),
    ]

    class DecisionSession:
        def scalar(self, _statement): return 12
        def scalars(self, _statement): return rows

    tools = object.__new__(CommandTools)
    tools.db = DecisionSession()
    changed_ids, held_ids = tools._latest_cycle_decision_ids("CUSTOMER")
    assert changed_ids == {changed_id}
    assert held_ids == {held_id}


def test_prioritization_command_runs_through_api(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/commands", json={"command": "Who should I focus on today?"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["interpreted_intent"]["intent"] == "PRIORITIZE_CASES"
    assert len(body["analyzed_entities"]) == 1
    assert body["outcomes"][0]["status"] == "ANALYZED"
    assert body["plan"]["execution_mode"] == "READ_ONLY"


def test_weather_request_is_unknown_through_serialized_command_endpoint(monkeypatch) -> None:
    class RejectFallbackTools(FakeCommandTools):
        def execute_customer_query(self, _query):
            raise AssertionError("Unsupported commands must not execute a customer query")

        def execute_case_query(self, _query):
            raise AssertionError("Unsupported commands must not execute a case query")

        def get_portfolio_intelligence(self):
            raise AssertionError("Unsupported commands must not inspect the portfolio")

    client = _client(monkeypatch, RejectFallbackTools)
    response = client.post("/commands", json={"command": "List weather forecasts for Bengaluru"})
    app.dependency_overrides.clear()
    body = response.json()
    assert response.status_code == 200
    assert body["interpreted_intent"]["intent"] == "UNKNOWN"
    assert body["analyzed_entities"] == []
    assert body["plan"]["proposed_actions"] == []
    assert body["query_evidence"]["records_inspected"] == 0
    assert body["query_evidence"]["records_matched"] == 0
    assert body["query_evidence"]["ranking"] == []


def test_prioritization_exposes_grounded_query_and_ranking_evidence(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/commands", json={"command": "Show top 5 high-risk customers"})
    app.dependency_overrides.clear()
    body = response.json()
    evidence = body["query_evidence"]
    assert response.status_code == 200
    assert body["interpreted_intent"]["query"]["limit"] == 5
    assert evidence["records_inspected"] == 1
    assert evidence["records_matched"] == 1
    assert evidence["records_returned"] == 1
    assert evidence["inspection_scope"] == {
        "customers": 1, "invoices": 1, "promises": 1,
        "active_disputes": 0, "recovery_cases": 1, "latest_cycle_events": 0,
    }
    assert evidence["ranking"][0]["rank"] == 1
    assert evidence["ranking"][0]["score"] == 88
    assert evidence["ranking"][0]["raw_score"] == CUSTOMER_RESULT.raw_score
    assert "INR 450000 overdue" in evidence["ranking"][0]["facts"][0]
    assert evidence["ranking"][0]["decision"] == CUSTOMER_RESULT.recommendation.title + ": " + CUSTOMER_RESULT.recommendation.explanation


def test_latest_cycle_evidence_fails_closed_across_customers_and_cases() -> None:
    other_customer_id = uuid4()
    other_case_id = uuid4()
    selected_event = SimpleNamespace(customer_id=CUSTOMER_ID, recovery_case_id=CASE_ID, invoice_id=INVOICE_ID)
    unrelated_customer_event = SimpleNamespace(customer_id=other_customer_id, recovery_case_id=other_case_id, invoice_id=uuid4())
    unrelated_case_event = SimpleNamespace(customer_id=CUSTOMER_ID, recovery_case_id=other_case_id, invoice_id=uuid4())
    customer_audit = SimpleNamespace(event_type="SIMULATION_INTELLIGENCE_TRANSITION", payload={
        "cycle": 9, "entity_type": "CUSTOMER", "entity_id": str(CUSTOMER_ID), "entity_name": "Selected customer",
        "previous_score": 68, "current_score": 88, "previous_recommendation": "FOLLOW_UP",
        "current_recommendation": "ESCALATE", "classifications": ["RECOMMENDATION_CHANGED"], "material": True,
    })
    unrelated_customer_audit = SimpleNamespace(event_type="SIMULATION_INTELLIGENCE_TRANSITION", payload={
        "cycle": 9, "entity_type": "CUSTOMER", "entity_id": str(other_customer_id), "entity_name": "Unrelated customer",
        "previous_score": 20, "current_score": 60, "previous_recommendation": "MONITOR",
        "current_recommendation": "FOLLOW_UP", "classifications": ["RECOMMENDATION_CHANGED"], "material": True,
    })
    case_audit = SimpleNamespace(event_type="SIMULATION_INTELLIGENCE_TRANSITION", payload={
        "cycle": 9, "entity_type": "RECOVERY_CASE", "entity_id": str(CASE_ID), "entity_name": "Selected case",
        "previous_score": 72, "current_score": 82, "previous_recommendation": "FOLLOW_UP",
        "current_recommendation": "ESCALATE", "classifications": ["RECOMMENDATION_CHANGED"], "material": True,
    })
    unrelated_case_audit = SimpleNamespace(event_type="SIMULATION_INTELLIGENCE_TRANSITION", payload={
        "cycle": 9, "entity_type": "RECOVERY_CASE", "entity_id": str(other_case_id), "entity_name": "Unrelated case",
        "previous_score": 30, "current_score": 70, "previous_recommendation": "MONITOR",
        "current_recommendation": "FOLLOW_UP", "classifications": ["RECOMMENDATION_CHANGED"], "material": True,
    })

    class Rows(list):
        def all(self):
            return self

    class EvidenceSession:
        def __init__(self):
            self.results = iter((Rows([selected_event, unrelated_customer_event, unrelated_case_event]), Rows([
                customer_audit, unrelated_customer_audit, case_audit, unrelated_case_audit,
            ])))

        def scalar(self, _statement):
            return 9

        def scalars(self, _statement):
            return next(self.results)

    customer_tools = object.__new__(CommandTools)
    customer_tools.db = EvidenceSession()
    customer_evidence = customer_tools.latest_cycle_evidence([CUSTOMER_RESULT])
    assert customer_evidence is not None
    assert customer_evidence.event_count == 2
    assert customer_evidence.observations == ["Selected customer: recommendation changed from FOLLOW_UP to ESCALATE."]
    assert "Unrelated customer" not in " ".join(customer_evidence.observations)

    case_tools = object.__new__(CommandTools)
    case_tools.db = EvidenceSession()
    case_tools._cases = [_case_candidate().case]
    case_evidence = case_tools.latest_cycle_evidence([CASE_RESULT])
    assert case_evidence is not None
    assert case_evidence.event_count == 1
    assert case_evidence.observations == ["Selected case: recommendation changed from FOLLOW_UP to ESCALATE."]
    assert "Unrelated case" not in " ".join(case_evidence.observations)


def test_zero_result_query_keeps_truthful_inspection_counts(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/commands", json={"command": "Overdue customers with active promises"})
    app.dependency_overrides.clear()
    evidence = response.json()["query_evidence"]
    assert response.status_code == 200
    assert evidence["records_inspected"] == 1
    assert evidence["records_matched"] == 0
    assert evidence["records_excluded"] == 1
    assert evidence["records_returned"] == 0
    assert evidence["ranking"] == []


def test_customer_case_and_explanation_context_commands(monkeypatch) -> None:
    client = _client(monkeypatch)
    customer = client.post("/commands", json={"command": "Analyze this customer", "context_customer_id": str(CUSTOMER_ID)})
    case = client.post("/commands", json={"command": "Analyze this case", "context_case_id": str(CASE_ID)})
    explanation = client.post("/commands", json={"command": "Why is this case critical?", "context_case_id": str(CASE_ID)})
    app.dependency_overrides.clear()
    assert customer.json()["interpreted_intent"]["intent"] == "CUSTOMER_ANALYSIS"
    assert case.json()["interpreted_intent"]["intent"] == "CASE_ANALYSIS"
    assert explanation.json()["interpreted_intent"]["intent"] == "EXPLAIN_RECOMMENDATION"
    assert "Score 82/100" in explanation.json()["plan"]["proposed_actions"][0]["explanation"]


def test_broken_promise_and_follow_up_commands(monkeypatch) -> None:
    client = _client(monkeypatch)
    review = client.post("/commands", json={"command": "Show me customers with broken promises"})
    follow_up = client.post("/commands", json={"command": "Follow up with customers whose promises are broken"})
    app.dependency_overrides.clear()
    assert review.json()["interpreted_intent"]["intent"] == "REVIEW_BROKEN_PROMISES"
    assert review.json()["plan"]["execution_mode"] == "READ_ONLY"
    assert follow_up.json()["interpreted_intent"]["intent"] == "PREPARE_FOLLOW_UPS"
    assert follow_up.json()["plan"]["requires_confirmation"] is True
    assert follow_up.json()["outcomes"][0]["status"] == "AWAITING_CONFIRMATION"


def test_recovery_preparation_requires_confirmation_and_does_not_auto_execute(monkeypatch) -> None:
    def forbidden_create_action(*_args, **_kwargs):
        raise AssertionError("Planning must never create a workflow action")

    monkeypatch.setattr("app.commands.executor.create_action", forbidden_create_action)
    client = _client(monkeypatch)
    response = client.post("/commands", json={"command": "Prepare recovery actions for all critical cases"})
    app.dependency_overrides.clear()
    body = response.json()
    assert response.status_code == 200
    assert body["interpreted_intent"]["intent"] == "PREPARE_RECOVERY_ACTIONS"
    assert body["plan"]["execution_mode"] == "CONFIRMATION_REQUIRED"
    assert body["outcomes"][0]["status"] == "AWAITING_CONFIRMATION"
    assert "does not contact the customer" in body["plan"]["proposed_actions"][0]["limitations"][0]
    proposal = body["plan"]["proposed_actions"][0]
    current = body["analyzed_entities"][0]
    assert proposal["risk_level"] == current["level"]
    assert proposal["current_intelligence_score"] == current["score"]
    assert proposal["current_intelligence_action"] == current["recommendation"]["action"]
    assert proposal["workflow_recommendation_action"] == RecommendedAction.PREPARE_ESCALATION.value
    assert body["query_evidence"]["records_returned"] == len(body["plan"]["proposed_actions"])


def test_recovery_preparation_never_relabels_medium_intelligence_as_critical(monkeypatch) -> None:
    class MediumTools(FakeCommandTools):
        def __init__(self, db=None):
            super().__init__(db)
            medium = self.candidate.intelligence.model_copy(update={"score": 38, "level": PriorityLevel.MEDIUM})
            self.candidate = CaseCandidate(
                case=self.candidate.case,
                intelligence=medium,
                recommendation=self.candidate.recommendation,
                risk_level=PriorityLevel.MEDIUM,
            )

    client = _client(monkeypatch, MediumTools)
    response = client.post("/commands", json={"command": "Prepare recovery actions for critical cases"})
    app.dependency_overrides.clear()
    body = response.json()
    assert body["query_evidence"]["records_inspected"] == 1
    assert body["query_evidence"]["records_matched"] == 0
    assert body["plan"]["proposed_actions"] == []
    assert body["analyzed_entities"] == []


def test_case_scoped_current_intelligence_uses_the_portfolio_customer_score() -> None:
    candidate = _case_candidate()
    tools = object.__new__(CommandTools)
    tools.simulation_date = TODAY
    expected = evaluate_customer_intelligence(candidate.case.customer, TODAY)
    scoped = tools._case_scoped_customer_intelligence(candidate.case)
    assert scoped.entity_type == "RECOVERY_CASE"
    assert scoped.entity_id == str(candidate.case.id)
    assert scoped.score == expected.score
    assert scoped.level is expected.level
    assert scoped.recommendation == expected.recommendation
    workspace = _current_workspace_intelligence(candidate.case, TODAY)
    assert workspace.model_dump() == expected.model_dump()
    assert candidate.case.priority is RecoveryPriority.CRITICAL


def test_actionable_case_query_excludes_blocked_case_before_proposal_planning() -> None:
    candidate = _case_candidate()
    candidate = CaseCandidate(
        case=candidate.case,
        intelligence=candidate.intelligence,
        recommendation=candidate.recommendation.model_copy(update={"blockers": ["ACTIVE_DISPUTE"]}),
        risk_level=candidate.risk_level,
    )
    tools = object.__new__(CommandTools)
    tools.simulation_date = TODAY
    tools.get_recovery_candidates = lambda top_n=None: [candidate]
    tools._latest_cycle_event_count = lambda: 0
    execution = tools.execute_case_query(StructuredQuery(entity=QueryEntity.RECOVERY_CASES, actionable=True))
    assert execution.inspected == 1
    assert execution.matched == 0
    assert execution.records == []
    assert execution.exclusions == [("Did not satisfy actionable recovery state = true", 1)]


def test_equivalent_active_workflow_suppresses_duplicate_proposal(monkeypatch) -> None:
    class ExistingActionTools(FakeCommandTools):
        def __init__(self, db=None):
            super().__init__(db)
            self.candidate.case.actions.append(RecoveryAction(
                id=uuid4(), status=RecoveryActionStatus.PENDING_APPROVAL,
                recommendation_action=RecommendedAction.PREPARE_ESCALATION.value,
            ))

    client = _client(monkeypatch, ExistingActionTools)
    body = client.post("/commands", json={"command": "Prepare recovery actions for critical cases"}).json()
    app.dependency_overrides.clear()
    assert body["plan"]["proposed_actions"] == []
    assert any("Existing action already pending approval" in warning for warning in body["warnings"])
    assert body["query_evidence"]["records_returned"] == 0


def test_changed_recommendation_allows_a_new_action_proposal() -> None:
    candidate = _case_candidate()
    candidate.case.actions.append(RecoveryAction(
        id=uuid4(), status=RecoveryActionStatus.PENDING_APPROVAL,
        recommendation_action=RecommendedAction.SEND_PAYMENT_REMINDER.value,
    ))
    assert CommandPlanner._active_equivalent_action(candidate) is None


def test_reminder_command_prepares_draft_without_sending(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/commands", json={"command": "Draft payment reminders for overdue customers"})
    app.dependency_overrides.clear()
    body = response.json()
    assert body["interpreted_intent"]["intent"] == "PREPARE_PAYMENT_REMINDERS"
    assert body["plan"]["execution_mode"] == "PREPARE"
    assert body["outcomes"][0]["status"] == "PREPARED"
    assert "does not send" in body["plan"]["proposed_actions"][0]["limitations"][0]
    artifact = body["plan"]["proposed_actions"][0]["reminder_artifact"]
    assert artifact["status"] == "PREPARED_FOR_REVIEW"
    assert artifact["invoices"][0]["invoice_number"] == "TEST-INV"
    assert "INR 450000.00" in artifact["body"]
    assert "payment promise has passed" in artifact["body"]


def test_reminder_artifact_is_blocked_by_current_dispute(monkeypatch) -> None:
    class DisputedTools(FakeCommandTools):
        def get_overdue_customers(self, top_n=None):
            metrics = CUSTOMER_RESULT.metrics.model_copy(update={"active_dispute_count": 1})
            return [CUSTOMER_RESULT.model_copy(update={"metrics": metrics})]

    client = _client(monkeypatch, DisputedTools)
    response = client.post("/commands", json={"command": "Draft payment reminders for overdue customers"})
    app.dependency_overrides.clear()
    artifact = response.json()["plan"]["proposed_actions"][0]["reminder_artifact"]
    assert artifact["status"] == "BLOCKED"
    assert artifact["body"] is None


def test_reminder_artifact_is_deferred_by_active_promise(monkeypatch) -> None:
    class ActivePromiseTools(FakeCommandTools):
        def get_overdue_customers(self, top_n=None):
            metrics = CUSTOMER_RESULT.metrics.model_copy(update={"active_promise_count": 1, "broken_promise_count": 0})
            return [CUSTOMER_RESULT.model_copy(update={"metrics": metrics})]

    client = _client(monkeypatch, ActivePromiseTools)
    response = client.post("/commands", json={"command": "Draft payment reminders for overdue customers"})
    app.dependency_overrides.clear()
    artifact = response.json()["plan"]["proposed_actions"][0]["reminder_artifact"]
    assert artifact["status"] == "DEFERRED"
    assert artifact["body"] is None


def test_unknown_missing_context_and_empty_results_are_honest(monkeypatch) -> None:
    client = _client(monkeypatch, EmptyCommandTools)
    unknown = client.post("/commands", json={"command": "Do something clever"})
    missing_context = client.post("/commands", json={"command": "Analyze this customer"})
    empty = client.post("/commands", json={"command": "Who should I focus on today?"})
    app.dependency_overrides.clear()
    assert unknown.json()["interpreted_intent"]["intent"] == "UNKNOWN"
    assert unknown.json()["warnings"]
    assert missing_context.json()["interpreted_intent"]["intent"] == "UNKNOWN"
    assert empty.json()["analyzed_entities"] == []
    assert empty.json()["warnings"]


def test_confirmation_creates_only_one_internal_workflow_action_and_retries_are_idempotent(monkeypatch) -> None:
    class CreatedAction:
        id = uuid4()
        status = RecoveryActionStatus.PENDING_APPROVAL
        created_at = datetime(2026, 8, 1, tzinfo=UTC)
        recommendation_context = {"workflow_effect": "Proceeding creates an internal controlled recovery workflow record for operator review."}

    calls = []

    def fake_create_action(db, case, simulation_date, expected_action, operator_note=None, idempotency_id=None):
        calls.append((db, case.id, simulation_date, expected_action, operator_note, idempotency_id))
        return CreatedAction()

    monkeypatch.setattr("app.commands.executor.create_action", fake_create_action)
    client = _client(monkeypatch)
    planned = client.post("/commands", json={"command": "Prepare recovery actions for critical cases"}).json()
    plan_id = planned["plan_id"]
    confirmed = client.post(f"/commands/{plan_id}/confirm", json={"operator_id": "operator-1", "note": "Reviewed"})
    repeated = client.post(f"/commands/{plan_id}/confirm", json={"operator_id": "operator-1"})
    app.dependency_overrides.clear()
    assert confirmed.status_code == 200
    assert confirmed.json()["execution_mode"] == "EXECUTED"
    assert confirmed.json()["outcomes"][0]["status"] == "EXECUTED"
    assert confirmed.json()["outcomes"][0]["recovery_action_id"] == str(CreatedAction.id)
    assert confirmed.json()["outcomes"][0]["recovery_action_status"] == "PENDING_APPROVAL"
    assert confirmed.json()["outcomes"][0]["workflow_effect"] == CreatedAction.recommendation_context["workflow_effect"]
    assert len(calls) == 1
    assert calls[0][3] is RecommendedAction.PREPARE_ESCALATION
    assert calls[0][5] is not None
    assert repeated.status_code == 200
    assert repeated.json() == confirmed.json()
    assert len(calls) == 1


def test_confirmation_result_survives_a_new_service_registry(monkeypatch) -> None:
    class DurableAuditDb:
        def __init__(self): self.records = {}
        def get(self, model, identity): return self.records.get((model, identity))
        def add(self, value): self.records[(type(value), value.id)] = value
        def commit(self): pass
        def scalar(self, _query): return None

    class CreatedAction:
        id = uuid4()
        status = RecoveryActionStatus.PENDING_APPROVAL
        created_at = datetime(2026, 8, 1, tzinfo=UTC)
        recommendation_context = {"workflow_effect": "Internal workflow only."}

    calls = []
    def fake_create_action(*args, **kwargs):
        calls.append(kwargs["idempotency_id"])
        return CreatedAction()

    monkeypatch.setattr("app.commands.executor.create_action", fake_create_action)
    db = DurableAuditDb()
    tools = FakeCommandTools(db)
    first_service = CommandService(registry=EphemeralPlanRegistry())
    planned = first_service.run(CommandRequest(command="Prepare recovery actions for critical cases"), tools)
    restarted_service = CommandService(registry=EphemeralPlanRegistry())
    confirmed = restarted_service.confirm(planned.plan_id, ConfirmCommandRequest(operator_id="operator-1"), tools)

    second_restart = CommandService(registry=EphemeralPlanRegistry())
    replayed = second_restart.confirm(planned.plan_id, ConfirmCommandRequest(operator_id="operator-1", note="different replay payload"), tools)

    assert replayed == confirmed
    assert len(calls) == 1
    assert db.get(AuditEvent, second_restart._audit_id(planned.plan_id, "confirmation-result")) is not None
