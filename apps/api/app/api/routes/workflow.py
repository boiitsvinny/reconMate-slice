"""Operator-controlled recovery action workflow endpoints."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.evidence.timeline import build_case_evidence_timeline
from app.intelligence.candidates import candidate_facts
from app.intelligence.schemas import CommunicationAnalysisResult
from app.intelligence.operational_service import evaluate_customer_intelligence
from app.models.domain import AuditEvent, Communication, Customer, ExternalPaymentRequest, Invoice, PromiseToPay, ProviderEvent, RecoveryAction, RecoveryCase, SimulationState
from app.recommendations.service import recommend_case
from app.workflow.schemas import CreateActionRequest, OperatorDecisionRequest, RecoveryActionResponse
from app.workflow.service import approve_action, cancel_action, create_action, execute_action, hold_action, reject_action

router = APIRouter(prefix="/recovery", tags=["recovery workflow"])


def _simulation_date(db: Session):
    value = db.scalar(select(SimulationState.simulation_date).where(SimulationState.name == "default"))
    if value is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Synthetic simulation state has not been seeded.")
    return value


def _current_workspace_intelligence(case: RecoveryCase, simulation_date):
    """Authoritative current intelligence shared with portfolio consumers."""
    return evaluate_customer_intelligence(case.customer, simulation_date)


def _case_query():
    return select(RecoveryCase).options(
        selectinload(RecoveryCase.customer).selectinload(Customer.communications).selectinload(Communication.analyses),
        selectinload(RecoveryCase.customer).selectinload(Customer.invoices).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.customer).selectinload(Customer.recovery_cases).selectinload(RecoveryCase.actions),
        selectinload(RecoveryCase.customer).selectinload(Customer.recovery_cases).selectinload(RecoveryCase.invoice),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )


def _action_response(action: RecoveryAction) -> RecoveryActionResponse:
    return RecoveryActionResponse(
        id=str(action.id), case_id=str(action.recovery_case_id), action_type=action.action_type.value,
        recommended_action=action.recommendation_action, status=action.status.value,
        approval_status=action.approval_status.value, human_approval_required=bool(action.human_approval_required),
        recommendation_context=action.recommendation_context, reason=action.reason,
        decision_by=action.decision_by, decision_reason=action.decision_reason, decision_at=action.decision_at,
        executed_at=action.executed_at, executed_by=action.executed_by, operator_note=action.operator_note,
        created_at=action.created_at,
    )


def _action_or_404(db: Session, action_id: UUID) -> RecoveryAction:
    action = db.scalar(select(RecoveryAction).where(RecoveryAction.id == action_id).options(selectinload(RecoveryAction.recovery_case)))
    if action is None:
        raise HTTPException(status_code=404, detail="Recovery action not found.")
    return action


@router.post("/cases/{case_id}/actions", response_model=RecoveryActionResponse, status_code=status.HTTP_201_CREATED)
def create_recovery_action(case_id: UUID, payload: CreateActionRequest, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    return _action_response(create_action(db, case, _simulation_date(db), payload.expected_recommended_action, payload.operator_note))


@router.get("/actions", response_model=list[RecoveryActionResponse])
def list_actions(
    status_filter: str | None = Query(default=None, alias="status"), action_type: str | None = Query(default=None),
    case_id: UUID | None = Query(default=None), approval_required: bool | None = Query(default=None), db: Session = Depends(get_db),
) -> list[RecoveryActionResponse]:
    query = select(RecoveryAction).order_by(RecoveryAction.created_at.desc())
    if status_filter: query = query.where(RecoveryAction.status == status_filter)
    if action_type: query = query.where(RecoveryAction.action_type == action_type)
    if case_id: query = query.where(RecoveryAction.recovery_case_id == case_id)
    if approval_required is not None: query = query.where(RecoveryAction.human_approval_required == approval_required)
    return [_action_response(action) for action in db.scalars(query)]


@router.get("/actions/{action_id}", response_model=RecoveryActionResponse)
def get_action(action_id: UUID, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    return _action_response(_action_or_404(db, action_id))


@router.get("/cases/{case_id}/actions", response_model=list[RecoveryActionResponse])
def list_case_actions(case_id: UUID, db: Session = Depends(get_db)) -> list[RecoveryActionResponse]:
    if db.get(RecoveryCase, case_id) is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    return [_action_response(action) for action in db.scalars(select(RecoveryAction).where(RecoveryAction.recovery_case_id == case_id).order_by(RecoveryAction.created_at.desc()))]


@router.post("/actions/{action_id}/approve", response_model=RecoveryActionResponse)
def approve_recovery_action(action_id: UUID, payload: OperatorDecisionRequest, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    return _action_response(approve_action(db, _action_or_404(db, action_id), payload.operator_id, payload.reason, payload.operator_note))


@router.post("/actions/{action_id}/reject", response_model=RecoveryActionResponse)
def reject_recovery_action(action_id: UUID, payload: OperatorDecisionRequest, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    if not payload.reason: raise HTTPException(status_code=422, detail="A rejection reason is required.")
    return _action_response(reject_action(db, _action_or_404(db, action_id), payload.operator_id, payload.reason, payload.operator_note))


@router.post("/actions/{action_id}/hold", response_model=RecoveryActionResponse)
def hold_recovery_action(action_id: UUID, payload: OperatorDecisionRequest, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    if not payload.reason: raise HTTPException(status_code=422, detail="A hold reason is required.")
    return _action_response(hold_action(db, _action_or_404(db, action_id), payload.operator_id, payload.reason, payload.operator_note))


@router.post("/actions/{action_id}/cancel", response_model=RecoveryActionResponse)
def cancel_recovery_action(action_id: UUID, payload: OperatorDecisionRequest, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    if not payload.reason: raise HTTPException(status_code=422, detail="A cancellation reason is required.")
    return _action_response(cancel_action(db, _action_or_404(db, action_id), payload.operator_id, payload.reason, payload.operator_note))


@router.post("/actions/{action_id}/execute", response_model=RecoveryActionResponse)
def execute_recovery_action(action_id: UUID, payload: OperatorDecisionRequest, db: Session = Depends(get_db)) -> RecoveryActionResponse:
    action = _action_or_404(db, action_id)
    case = db.scalar(_case_query().where(RecoveryCase.id == action.recovery_case_id))
    if case is None: raise HTTPException(status_code=409, detail="The action no longer has a recoverable case.")
    return _action_response(execute_action(db, action, case, _simulation_date(db), payload.operator_id, payload.operator_note))


@router.get("/cases/{case_id}/workspace")
def case_workspace(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None: raise HTTPException(status_code=404, detail="Recovery case not found.")
    simulation_date = _simulation_date(db)
    events = db.scalars(select(AuditEvent).where((AuditEvent.entity_type == "RecoveryCase") & (AuditEvent.entity_id == case.id)).order_by(AuditEvent.occurred_at.desc())).all()
    payment_requests = list(db.scalars(select(ExternalPaymentRequest).where(ExternalPaymentRequest.recovery_case_id == case.id).order_by(ExternalPaymentRequest.created_at.desc())))
    provider_events = list(db.scalars(select(ProviderEvent).where(ProviderEvent.payment_request_id.in_([item.id for item in payment_requests])).order_by(ProviderEvent.received_at.desc()))) if payment_requests else []
    analysis_ids = [analysis.id for communication in case.customer.communications for analysis in communication.analyses]
    review_events = list(db.scalars(select(AuditEvent).where(
        AuditEvent.entity_type == "CommunicationAnalysis", AuditEvent.entity_id.in_(analysis_ids),
        AuditEvent.event_type.in_(["AI_CANDIDATE_ACCEPTED", "AI_CANDIDATE_REJECTED"]),
    ).order_by(AuditEvent.occurred_at))) if analysis_ids else []
    decisions = {
        (str(event.entity_id), str((event.payload or {}).get("candidate_id"))): (event.payload or {}).get("decision_result")
        for event in review_events
    }
    evidence_timeline = build_case_evidence_timeline(db, case, payment_requests, provider_events)
    return {
        "case_id": str(case.id), "customer": {"id": str(case.customer.id), "name": case.customer.name, "strategic": bool(case.customer.is_strategic_account)},
        "workflow": {"stored_priority": case.priority.value, "recovery_state": case.current_state.value, "opened_at": case.opened_at, "updated_at": case.updated_at},
        "recommendation": recommend_case(case, simulation_date).model_dump(mode="json"),
        # Use the same customer-level current intelligence as Home, Reports, and
        # Analyze. Case recommendation and stored workflow remain separate.
        "intelligence": _current_workspace_intelligence(case, simulation_date).model_dump(mode="json"),
        "invoice": None if case.invoice is None else {"id": str(case.invoice.id), "number": case.invoice.invoice_number, "status": case.invoice.status.value, "outstanding_amount": case.invoice.outstanding_amount, "due_date": case.invoice.due_date},
        "promises": [{"id": str(item.id), "status": item.status.value, "promised_amount": item.promised_amount, "promised_date": item.promised_date} for item in case.invoice.promises_to_pay] if case.invoice else [],
        "payments": [{"id": str(item.id), "amount": item.amount, "payment_date": item.payment_date, "reference": item.reference} for item in sorted(case.invoice.payments, key=lambda item: item.payment_date, reverse=True)] if case.invoice else [],
        "communications": [{
            "id": str(item.id), "direction": item.direction.value, "content": item.content, "occurred_at": item.occurred_at,
            "analyses": [{
                "id": str(analysis.id), "provider": analysis.provider, "model_version": analysis.model_version,
                "runtime_mode": "LIVE MODEL" if analysis.provider == "openai" else "MOCK / DEV MODE",
                "analyzed_at": analysis.analyzed_at, "result": analysis.result,
                "candidates": [
                    {**candidate.model_dump(mode="json"), "decision_result": decisions.get((str(analysis.id), candidate.candidate_id))}
                    for candidate in candidate_facts(item.content, CommunicationAnalysisResult.model_validate(analysis.result))
                ],
            } for analysis in sorted(item.analyses, key=lambda value: value.analyzed_at or item.occurred_at, reverse=True)],
        } for item in sorted(case.customer.communications, key=lambda item: item.occurred_at, reverse=True)],
        "actions": [_action_response(item).model_dump(mode="json") for item in case.actions],
        "external_payment_requests": [{"id": str(item.id), "case_id": str(item.recovery_case_id), "customer_id": str(item.customer_id), "invoice_id": str(item.invoice_id), "provider": item.provider, "provider_mode": item.provider_mode, "provider_reference": item.provider_reference, "provider_url": item.provider_url, "requested_amount": item.requested_amount, "paid_amount": item.paid_amount, "status": item.status, "purpose": item.purpose, "operator_id": item.operator_id, "failure_reason": item.failure_reason, "created_at": item.created_at} for item in payment_requests],
        "provider_events": [{"id": str(item.id), "payment_request_id": str(item.payment_request_id), "provider_event_id": item.provider_event_id, "provider_payment_reference": item.provider_payment_reference, "event_type": item.event_type, "evidence": item.evidence, "received_at": item.received_at} for item in provider_events],
        "evidence_timeline": evidence_timeline,
        "audit_events": [{"id": str(item.id), "event_type": item.event_type, "payload": item.payload, "occurred_at": item.occurred_at} for item in events],
    }
