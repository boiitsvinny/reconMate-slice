from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.routes import commands as commands_route
from app.commands.interpreter import RuleBasedCommandInterpreter
from app.commands.schemas import CommandIntentType, CommandRequest, ExecutionMode, ProposalStatus
from app.commands.tools import CaseCandidate
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
from app.main import app
from app.models.domain import Customer, Invoice, InvoiceStatus, RecoveryActionStatus, RecoveryCase, RecoveryPriority, RecoveryState
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

    def get_case_intelligence(self, case_id):
        return CASE_RESULT if case_id == CASE_ID else None

    def get_broken_promise_customers(self, top_n=None):
        results = [CUSTOMER_RESULT]
        return results[:top_n] if top_n is not None else results

    def get_overdue_customers(self, top_n=None):
        results = [CUSTOMER_RESULT]
        return results[:top_n] if top_n is not None else results

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


def test_reminder_command_prepares_draft_without_sending(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/commands", json={"command": "Draft payment reminders for overdue customers"})
    app.dependency_overrides.clear()
    body = response.json()
    assert body["interpreted_intent"]["intent"] == "PREPARE_PAYMENT_REMINDERS"
    assert body["plan"]["execution_mode"] == "PREPARE"
    assert body["outcomes"][0]["status"] == "PREPARED"
    assert "does not send" in body["plan"]["proposed_actions"][0]["limitations"][0]


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


def test_confirmation_creates_only_internal_workflow_action_and_is_single_use(monkeypatch) -> None:
    class CreatedAction:
        id = uuid4()
        status = RecoveryActionStatus.PENDING_APPROVAL
        created_at = datetime(2026, 8, 1, tzinfo=UTC)
        recommendation_context = {"workflow_effect": "Proceeding creates an internal controlled recovery workflow record for operator review."}

    calls = []

    def fake_create_action(db, case, simulation_date, expected_action, operator_note=None):
        calls.append((db, case.id, simulation_date, expected_action, operator_note))
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
    assert repeated.status_code == 404
