"""Safe, simulated action lifecycle over persisted recovery recommendations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    ApprovalStatus, AuditEvent, RecoveryAction, RecoveryActionStatus,
    RecoveryActionType, RecoveryCase,
)
from app.recommendations.schemas import RecommendedAction, RecoveryRecommendation
from app.recommendations.service import recommend_case


ACTION_TYPE_BY_RECOMMENDATION = {
    RecommendedAction.SEND_PAYMENT_REMINDER: RecoveryActionType.OUTREACH,
    RecommendedAction.REQUEST_PAYMENT_DATE: RecoveryActionType.FOLLOW_UP,
    RecommendedAction.MONITOR_ACTIVE_PROMISE: RecoveryActionType.NOTE,
    RecommendedAction.REVIEW_PAYMENT_CLAIM: RecoveryActionType.NOTE,
    RecommendedAction.HOLD_FOR_DISPUTE: RecoveryActionType.NOTE,
    RecommendedAction.PREPARE_ESCALATION: RecoveryActionType.ESCALATE,
    RecommendedAction.ESCALATE_TO_HUMAN: RecoveryActionType.ESCALATE,
}
OUTREACH_RECOMMENDATIONS = {RecommendedAction.SEND_PAYMENT_REMINDER, RecommendedAction.REQUEST_PAYMENT_DATE}
ACTIVE_STATUSES = {RecoveryActionStatus.RECOMMENDED, RecoveryActionStatus.PENDING_APPROVAL, RecoveryActionStatus.APPROVED, RecoveryActionStatus.HELD}


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(message: str, code: int = status.HTTP_409_CONFLICT) -> None:
    raise HTTPException(status_code=code, detail=message)


def _audit(db: Session, action: RecoveryAction, event_type: str, payload: dict[str, Any], actor_type: str, actor_id: str | None = None) -> None:
    db.add(AuditEvent(entity_type="RecoveryAction", entity_id=action.id, event_type=event_type,
                      actor_type=actor_type, actor_id=actor_id, payload=payload, occurred_at=_now()))


def _snapshot(recommendation: RecoveryRecommendation) -> dict[str, Any]:
    return recommendation.model_dump(mode="json")


def _ensure_facts_allow_execution(case: RecoveryCase, recommendation: RecoveryRecommendation) -> None:
    action = recommendation.recommended_action
    if action is RecommendedAction.NO_ACTION_REQUIRED:
        _fail("The current factual recovery evaluation requires no executable action.")
    if recommendation.recovery_state in {"CLOSED", "RESOLVED"}:
        _fail("Closed, resolved, or paid cases cannot execute recovery work.")
    if "ACTIVE_DISPUTE" in recommendation.blockers and action in OUTREACH_RECOMMENDATIONS:
        _fail("An active dispute blocks simulated outreach.")


def create_action(
    db: Session,
    case: RecoveryCase,
    simulation_date,
    expected_action: RecommendedAction | None,
    operator_note: str | None = None,
    idempotency_id: UUID | None = None,
) -> RecoveryAction:
    if idempotency_id is not None:
        existing = db.get(RecoveryAction, idempotency_id)
        if existing is not None:
            if existing.recovery_case_id != case.id or (
                expected_action is not None and existing.recommendation_action != expected_action.value
            ):
                _fail("The confirmation identity is already bound to different workflow work.")
            return existing
    recommendation = recommend_case(case, simulation_date)
    if expected_action is not None and recommendation.recommended_action is not expected_action:
        _fail(f"Recommendation is stale: current action is {recommendation.recommended_action.value}.")
    _ensure_facts_allow_execution(case, recommendation)
    action_type = ACTION_TYPE_BY_RECOMMENDATION.get(recommendation.recommended_action)
    if action_type is None:
        _fail("The current recommendation is advisory only and should not create workflow work.")
    duplicate = db.scalar(select(RecoveryAction.id).where(
        RecoveryAction.recovery_case_id == case.id,
        RecoveryAction.recommendation_action == recommendation.recommended_action.value,
        RecoveryAction.status.in_(ACTIVE_STATUSES | {RecoveryActionStatus.EXECUTED}),
    ))
    if duplicate is not None:
        _fail("An active or executed action already exists for this exact recommendation.")
    approval_required = bool(recommendation.human_approval_required)
    action = RecoveryAction(
        id=idempotency_id,
        recovery_case=case, action_type=action_type,
        status=RecoveryActionStatus.PENDING_APPROVAL if approval_required else RecoveryActionStatus.RECOMMENDED,
        approval_status=ApprovalStatus.PENDING if approval_required else ApprovalStatus.NOT_REQUIRED,
        recommendation_action=recommendation.recommended_action.value,
        recommendation_context=_snapshot(recommendation), human_approval_required=approval_required,
        reason=recommendation.operator_explanation, operator_note=operator_note,
    )
    db.add(action)
    db.flush()
    _audit(db, action, "RECOVERY_ACTION_RECOMMENDED", {"recommendation": action.recommendation_context}, "system")
    db.commit()
    db.refresh(action)
    return action


def approve_action(db: Session, action: RecoveryAction, operator_id: str, reason: str | None, note: str | None) -> RecoveryAction:
    if action.status is not RecoveryActionStatus.PENDING_APPROVAL:
        _fail("Only actions pending approval can be approved.")
    action.status, action.approval_status = RecoveryActionStatus.APPROVED, ApprovalStatus.APPROVED
    action.decision_by, action.decision_reason, action.decision_at = operator_id, reason, _now()
    action.operator_note = note or action.operator_note
    _audit(db, action, "RECOVERY_ACTION_APPROVED", {"reason": reason}, "operator", operator_id)
    db.commit(); db.refresh(action)
    return action


def reject_action(db: Session, action: RecoveryAction, operator_id: str, reason: str, note: str | None) -> RecoveryAction:
    if action.status not in {RecoveryActionStatus.RECOMMENDED, RecoveryActionStatus.PENDING_APPROVAL, RecoveryActionStatus.APPROVED}:
        _fail("Only unexecuted workflow actions can be rejected.")
    action.status, action.approval_status = RecoveryActionStatus.REJECTED, ApprovalStatus.REJECTED
    action.decision_by, action.decision_reason, action.decision_at = operator_id, reason, _now()
    action.operator_note = note or action.operator_note
    _audit(db, action, "RECOVERY_ACTION_REJECTED", {"reason": reason}, "operator", operator_id)
    db.commit(); db.refresh(action)
    return action


def hold_action(db: Session, action: RecoveryAction, operator_id: str, reason: str, note: str | None) -> RecoveryAction:
    if action.status not in {RecoveryActionStatus.RECOMMENDED, RecoveryActionStatus.PENDING_APPROVAL, RecoveryActionStatus.APPROVED}:
        _fail("Only unexecuted workflow actions can be held.")
    action.status = RecoveryActionStatus.HELD
    action.decision_by, action.decision_reason, action.decision_at = operator_id, reason, _now()
    action.operator_note = note or action.operator_note
    _audit(db, action, "RECOVERY_ACTION_HELD", {"reason": reason}, "operator", operator_id)
    db.commit(); db.refresh(action)
    return action


def cancel_action(db: Session, action: RecoveryAction, operator_id: str, reason: str, note: str | None) -> RecoveryAction:
    if action.status in {RecoveryActionStatus.EXECUTED, RecoveryActionStatus.CANCELLED}:
        _fail("Executed or cancelled actions cannot be cancelled.")
    action.status = RecoveryActionStatus.CANCELLED
    action.decision_by, action.decision_reason, action.decision_at = operator_id, reason, _now()
    action.operator_note = note or action.operator_note
    _audit(db, action, "RECOVERY_ACTION_CANCELLED", {"reason": reason}, "operator", operator_id)
    db.commit(); db.refresh(action)
    return action


def _execution_blocked(db: Session, action: RecoveryAction, message: str, payload: dict[str, Any] | None = None) -> None:
    _audit(db, action, "RECOVERY_ACTION_EXECUTION_BLOCKED", {"reason": message, **(payload or {})}, "system")
    db.commit()
    _fail(message)


def execute_action(db: Session, action: RecoveryAction, case: RecoveryCase, simulation_date, operator_id: str, note: str | None) -> RecoveryAction:
    if action.status is RecoveryActionStatus.EXECUTED:
        _execution_blocked(db, action, "This action was already executed; duplicate execution is blocked.")
    if action.status in {RecoveryActionStatus.REJECTED, RecoveryActionStatus.HELD, RecoveryActionStatus.CANCELLED}:
        _execution_blocked(db, action, f"An action in {action.status.value} state cannot execute.")
    if action.human_approval_required and action.status is not RecoveryActionStatus.APPROVED:
        _execution_blocked(db, action, "Human approval is required before this action can execute.")
    if action.status not in {RecoveryActionStatus.RECOMMENDED, RecoveryActionStatus.APPROVED}:
        _execution_blocked(db, action, "Only recommended no-approval actions or approved actions can execute.")
    recommendation = recommend_case(case, simulation_date)
    try:
        _ensure_facts_allow_execution(case, recommendation)
        if "ACTIVE_DISPUTE" in recommendation.blockers and action.recommendation_action in {item.value for item in OUTREACH_RECOMMENDATIONS}:
            _fail("An active dispute blocks simulated outreach, including a previously created action.")
    except HTTPException as exc:
        _execution_blocked(db, action, str(exc.detail), {"current_recommendation": recommendation.model_dump(mode="json")})
    # Simulated only: no payment, invoice, promise, state, or external communication is changed.
    action.status, action.executed_at, action.executed_by = RecoveryActionStatus.EXECUTED, _now(), operator_id
    action.operator_note = note or action.operator_note
    _audit(db, action, "RECOVERY_ACTION_EXECUTED", {"simulated": True, "recommended_action": action.recommendation_action}, "operator", operator_id)
    db.commit(); db.refresh(action)
    return action
