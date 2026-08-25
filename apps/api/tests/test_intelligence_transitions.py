from datetime import date
from decimal import Decimal

from app.intelligence.operational_schemas import (
    IntelligenceMetrics, IntelligenceRecommendation, IntelligenceResult, IntelligenceSignal,
    PriorityLevel, RecommendationAction, SignalType,
)
from app.intelligence.transitions import ChangeDirection, TransitionClassification, compare_intelligence


def _result(*, score: int, level: PriorityLevel, signals: list[SignalType], recommendation: RecommendationAction) -> IntelligenceResult:
    metrics = IntelligenceMetrics(
        total_outstanding_amount=Decimal("100000"), overdue_exposure=Decimal("100000"),
        overdue_invoice_count=1, max_days_overdue=40, broken_promise_count=int(SignalType.BROKEN_PROMISE in signals),
        active_promise_count=0, active_dispute_count=int(SignalType.ACTIVE_DISPUTE in signals),
        days_since_last_payment=45, active_recovery_case_count=1, stalled_recovery_case_count=0,
    )
    return IntelligenceResult(
        entity_type="CUSTOMER", entity_id="customer-1", entity_name="Test Account",
        calculated_at=date(2026, 8, 2), score=score, level=level, metrics=metrics,
        signals=[IntelligenceSignal(type=item, severity=PriorityLevel.HIGH, title=item.value.replace("_", " ").title(), explanation=item.value.replace("_", " ").lower(), calculated_at=date(2026, 8, 2)) for item in signals],
        factors=[],
        recommendation=IntelligenceRecommendation(action=recommendation, title=recommendation.value.replace("_", " ").title(), explanation=recommendation.value.replace("_", " ").lower(), priority_level=level, operator_confirmation_required=False),
    )


def _compare(before: IntelligenceResult, after: IntelligenceResult, event_type: str = "PROMISE_BROKEN"):
    return compare_intelligence(
        before=before, after=after, previous_recommendation=before.recommendation.action.value,
        current_recommendation=after.recommendation.action.value, cycle=2, event_id="event-1", event_type=event_type,
        previous_recommendation_title=before.recommendation.title,
        current_recommendation_title=after.recommendation.title,
        current_recommendation_explanation=after.recommendation.explanation,
    )


def test_broken_promise_explains_material_risk_and_recommendation_change() -> None:
    before = _result(score=35, level=PriorityLevel.MEDIUM, signals=[], recommendation=RecommendationAction.WAIT_FOR_PROMISE)
    after = _result(score=55, level=PriorityLevel.HIGH, signals=[SignalType.BROKEN_PROMISE], recommendation=RecommendationAction.PRIORITIZE_RECOVERY)
    transition = _compare(before, after)
    assert transition.material is True
    assert transition.change_direction is ChangeDirection.WORSENED
    assert transition.signals_added == [SignalType.BROKEN_PROMISE]
    assert TransitionClassification.RISK_INCREASED in transition.classifications
    assert TransitionClassification.RECOMMENDATION_CHANGED in transition.classifications
    assert "Wait For Promise" in transition.decision_impact
    assert "BROKEN_PROMISE" not in transition.why_intelligence_changed
    assert "Broken Promise" in transition.why_intelligence_changed


def test_dispute_opened_is_a_new_blocker() -> None:
    before = _result(score=55, level=PriorityLevel.HIGH, signals=[], recommendation=RecommendationAction.PRIORITIZE_RECOVERY)
    after = _result(score=75, level=PriorityLevel.HIGH, signals=[SignalType.ACTIVE_DISPUTE], recommendation=RecommendationAction.REVIEW_DISPUTE)
    transition = _compare(before, after, "DISPUTE_OPENED")
    assert TransitionClassification.NEW_BLOCKER in transition.classifications
    assert transition.change_direction is ChangeDirection.WORSENED
    assert "constrained" in transition.operator_significance


def test_resolved_signal_is_an_improvement() -> None:
    before = _result(score=65, level=PriorityLevel.HIGH, signals=[SignalType.HIGH_VALUE_OVERDUE], recommendation=RecommendationAction.PRIORITIZE_RECOVERY)
    after = _result(score=30, level=PriorityLevel.MEDIUM, signals=[], recommendation=RecommendationAction.FOLLOW_UP)
    transition = _compare(before, after, "PARTIAL_PAYMENT_RECEIVED")
    assert TransitionClassification.RISK_DECREASED in transition.classifications
    assert TransitionClassification.SIGNAL_RESOLVED in transition.classifications
    assert transition.change_direction is ChangeDirection.IMPROVED


def test_score_only_movement_inside_band_is_not_material() -> None:
    before = _result(score=51, level=PriorityLevel.HIGH, signals=[SignalType.LONG_OVERDUE], recommendation=RecommendationAction.PRIORITIZE_RECOVERY)
    after = _result(score=53, level=PriorityLevel.HIGH, signals=[SignalType.LONG_OVERDUE], recommendation=RecommendationAction.PRIORITIZE_RECOVERY)
    transition = _compare(before, after, "INVOICE_BECAME_OVERDUE")
    assert transition.material is False
    assert transition.classifications == [TransitionClassification.NO_MATERIAL_CHANGE]
    assert "remained in the HIGH risk band" in transition.why_intelligence_changed


def test_new_entity_does_not_claim_existing_signals_were_added() -> None:
    after = _result(score=75, level=PriorityLevel.HIGH, signals=[SignalType.ACTIVE_DISPUTE], recommendation=RecommendationAction.REVIEW_DISPUTE)
    transition = compare_intelligence(
        before=None, after=after, previous_recommendation=None, current_recommendation=after.recommendation.action.value,
        cycle=4, event_id="event-4", event_type="DISPUTE_OPENED",
    )
    assert transition.material is False
    assert transition.signals_added == []
    assert "No comparable prior intelligence state existed" in transition.why_intelligence_changed
