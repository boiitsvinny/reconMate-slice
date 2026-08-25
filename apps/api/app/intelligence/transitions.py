"""Deterministic before/after explanations for simulation intelligence changes."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.intelligence.operational_schemas import IntelligenceResult, PriorityLevel, SignalType


class TransitionClassification(str, Enum):
    RISK_INCREASED = "RISK_INCREASED"
    RISK_DECREASED = "RISK_DECREASED"
    RECOMMENDATION_CHANGED = "RECOMMENDATION_CHANGED"
    NEW_BLOCKER = "NEW_BLOCKER"
    BLOCKER_RESOLVED = "BLOCKER_RESOLVED"
    NEW_SIGNAL = "NEW_SIGNAL"
    SIGNAL_RESOLVED = "SIGNAL_RESOLVED"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"


class ChangeDirection(str, Enum):
    WORSENED = "WORSENED"
    IMPROVED = "IMPROVED"
    UNCHANGED = "UNCHANGED"


class ScoreDirection(str, Enum):
    INCREASED = "INCREASED"
    DECREASED = "DECREASED"
    UNCHANGED = "UNCHANGED"


class IntelligenceTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    entity_id: str
    entity_name: str
    simulation_cycle: int
    related_event_id: str
    related_event_type: str
    previous_score: int | None = None
    current_score: int
    score_direction: ScoreDirection
    previous_risk_level: PriorityLevel | None = None
    current_risk_level: PriorityLevel
    previous_recommendation: str | None = None
    current_recommendation: str
    signals_added: list[SignalType]
    signals_removed: list[SignalType]
    classifications: list[TransitionClassification]
    change_direction: ChangeDirection
    material: bool
    what_changed: str
    why_intelligence_changed: str
    decision_impact: str
    operator_significance: str


_LEVEL_ORDER = {PriorityLevel.LOW: 0, PriorityLevel.MEDIUM: 1, PriorityLevel.HIGH: 2, PriorityLevel.CRITICAL: 3}
_BLOCKER_SIGNALS = {SignalType.ACTIVE_DISPUTE}
_EVENT_FACTS = {
    "PROMISE_BROKEN": "A recorded payment promise passed its deadline without matching payment and was marked broken.",
    "DISPUTE_OPENED": "A dispute was recorded against the affected invoice.",
    "DISPUTE_RESOLVED": "The recorded invoice dispute was resolved.",
    "FULL_PAYMENT_RECEIVED": "A payment cleared the affected invoice's remaining outstanding balance.",
    "PARTIAL_PAYMENT_RECEIVED": "A payment reduced the affected invoice's outstanding balance.",
    "PAYMENT_COMMITMENT_RECEIVED": "A new payment commitment was recorded with a future promised date.",
    "INVOICE_BECAME_OVERDUE": "The affected invoice crossed its due date with an outstanding balance.",
}


def compare_intelligence(
    *,
    before: IntelligenceResult | None,
    after: IntelligenceResult,
    previous_recommendation: str | None,
    current_recommendation: str,
    cycle: int,
    event_id: str,
    event_type: str,
) -> IntelligenceTransition:
    """Compare material decision state; score-only movement inside one band is non-material."""
    # A newly created entity has no comparable baseline. Its existing signals
    # are current state, not newly appeared signals.
    before_signals = {item.type for item in before.signals} if before else {item.type for item in after.signals}
    after_signals = {item.type for item in after.signals}
    added = sorted(after_signals - before_signals, key=lambda item: item.value)
    removed = sorted(before_signals - after_signals, key=lambda item: item.value)
    classifications: list[TransitionClassification] = []

    if before and _LEVEL_ORDER[after.level] > _LEVEL_ORDER[before.level]:
        classifications.append(TransitionClassification.RISK_INCREASED)
    elif before and _LEVEL_ORDER[after.level] < _LEVEL_ORDER[before.level]:
        classifications.append(TransitionClassification.RISK_DECREASED)
    if previous_recommendation is not None and previous_recommendation != current_recommendation:
        classifications.append(TransitionClassification.RECOMMENDATION_CHANGED)
    if any(signal in _BLOCKER_SIGNALS for signal in added):
        classifications.append(TransitionClassification.NEW_BLOCKER)
    if any(signal in _BLOCKER_SIGNALS for signal in removed):
        classifications.append(TransitionClassification.BLOCKER_RESOLVED)
    if added:
        classifications.append(TransitionClassification.NEW_SIGNAL)
    if removed:
        classifications.append(TransitionClassification.SIGNAL_RESOLVED)

    material = bool(classifications)
    if not material:
        classifications = [TransitionClassification.NO_MATERIAL_CHANGE]

    previous_score = before.score if before else None
    score_direction = (
        ScoreDirection.UNCHANGED if previous_score is None or previous_score == after.score
        else ScoreDirection.INCREASED if after.score > previous_score
        else ScoreDirection.DECREASED
    )
    direction = _change_direction(classifications, score_direction)
    fact = _EVENT_FACTS.get(event_type, f"The simulation recorded {event_type.replace('_', ' ').lower()}.")
    why = _why_changed(before, after, added, removed, material)
    decision = (
        f"The current recommended next step is {current_recommendation}; no prior intelligence state was available for comparison."
        if previous_recommendation is None
        else f"ReconMate changed the recommended next step from {previous_recommendation} to {current_recommendation}."
        if previous_recommendation != current_recommendation
        else f"The recommended next step remains {current_recommendation}."
    )

    return IntelligenceTransition(
        entity_type=after.entity_type,
        entity_id=after.entity_id,
        entity_name=after.entity_name,
        simulation_cycle=cycle,
        related_event_id=event_id,
        related_event_type=event_type,
        previous_score=previous_score,
        current_score=after.score,
        score_direction=score_direction,
        previous_risk_level=before.level if before else None,
        current_risk_level=after.level,
        previous_recommendation=previous_recommendation,
        current_recommendation=current_recommendation,
        signals_added=added,
        signals_removed=removed,
        classifications=classifications,
        change_direction=direction,
        material=material,
        what_changed=fact,
        why_intelligence_changed=why,
        decision_impact=decision,
        operator_significance=_operator_significance(direction, classifications, current_recommendation),
    )


def _why_changed(
    before: IntelligenceResult | None,
    after: IntelligenceResult,
    added: list[SignalType],
    removed: list[SignalType],
    material: bool,
) -> str:
    if before is None:
        return "No comparable prior intelligence state existed for this newly created recovery entity."
    parts: list[str] = []
    if added:
        parts.append(f"New intelligence signals: {', '.join(item.value for item in added)}.")
    if removed:
        parts.append(f"Resolved intelligence signals: {', '.join(item.value for item in removed)}.")
    if before and before.level != after.level:
        parts.append(f"The score moved from {before.score} ({before.level.value}) to {after.score} ({after.level.value}).")
    elif before and before.score != after.score:
        parts.append(f"The score moved from {before.score} to {after.score} but remained in the {after.level.value} risk band.")
    if not material:
        parts.append("The risk band, recommendation, and material signal set remained unchanged after re-evaluation.")
    return " ".join(parts)


def _change_direction(classifications: list[TransitionClassification], score_direction: ScoreDirection) -> ChangeDirection:
    if TransitionClassification.RISK_INCREASED in classifications or TransitionClassification.NEW_BLOCKER in classifications:
        return ChangeDirection.WORSENED
    if TransitionClassification.RISK_DECREASED in classifications or TransitionClassification.BLOCKER_RESOLVED in classifications:
        return ChangeDirection.IMPROVED
    if score_direction is ScoreDirection.INCREASED and TransitionClassification.NEW_SIGNAL in classifications:
        return ChangeDirection.WORSENED
    if score_direction is ScoreDirection.DECREASED and TransitionClassification.SIGNAL_RESOLVED in classifications:
        return ChangeDirection.IMPROVED
    return ChangeDirection.UNCHANGED


def _operator_significance(direction: ChangeDirection, classifications: list[TransitionClassification], recommendation: str) -> str:
    if TransitionClassification.NEW_BLOCKER in classifications:
        return "Normal recovery escalation is now constrained; the operator should review the new blocker before proceeding."
    if TransitionClassification.BLOCKER_RESOLVED in classifications:
        return f"The previous blocker no longer applies; the operator can review the current {recommendation} recommendation."
    if TransitionClassification.RECOMMENDATION_CHANGED in classifications:
        return "The previously valid next step no longer matches current facts, so the operator should review the updated recommendation."
    if direction is ChangeDirection.WORSENED:
        return "The affected record now carries greater recovery risk and may require earlier operator attention."
    if direction is ChangeDirection.IMPROVED:
        return "The affected record's recovery risk reduced; the operator should use the refreshed recommendation rather than the prior state."
    return "ReconMate re-evaluated the affected record; no material decision or attention priority changed."
