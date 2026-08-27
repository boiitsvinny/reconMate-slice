"""Read-only deterministic recovery-engine inspection endpoints."""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.timing import elapsed_ms, log_timing
from app.db.session import get_db
from app.models.domain import Communication, Customer, Invoice, PromiseToPay, RecoveryCase, SimulationState
from app.recommendations.schemas import RecoveryRecommendation
from app.recommendations.service import prioritized_recommendations, recommend_case
from app.recovery.engine import case_evaluation_dict, evaluate_case, evaluate_invoice, recovery_summary

router = APIRouter(prefix="/recovery", tags=["recovery"])
customer_recovery_router = APIRouter(tags=["recovery"])


def _simulation_date(db: Session):
    simulation_date = db.scalar(select(SimulationState.simulation_date).where(SimulationState.name == "default"))
    if simulation_date is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Synthetic simulation state has not been seeded.")
    return simulation_date


def _case_query():
    return select(RecoveryCase).options(
        selectinload(RecoveryCase.customer).selectinload(Customer.communications).selectinload(Communication.analyses),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )


@router.get("/recommendations", response_model=list[RecoveryRecommendation], summary="Return a prioritized read-only recommendation queue")
def list_recommendations(db: Session = Depends(get_db)) -> list[RecoveryRecommendation]:
    simulation_date = _simulation_date(db)
    cases = [case for case in db.scalars(_case_query()).all() if case.invoice is None or case.invoice.issue_date <= simulation_date]
    return prioritized_recommendations(cases, simulation_date)


@router.get("/cases", summary="List recovery cases with deterministic state")
def list_recovery_cases(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    simulation_date = _simulation_date(db)
    cases = [case for case in db.scalars(_case_query().order_by(RecoveryCase.opened_at)).all() if case.invoice is None or case.invoice.issue_date <= simulation_date]
    return [{
        "case_id": str(case.id), "customer_id": str(case.customer_id), "customer_name": case.customer.name,
        "invoice_id": str(case.invoice_id) if case.invoice_id else None,
        "stored_state": case.current_state.value, "evaluation": case_evaluation_dict(evaluate_case(case, simulation_date)),
    } for case in cases]


@router.get("/cases/{case_id}", summary="Inspect a recovery case")
def get_recovery_case(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    simulation_date = _simulation_date(db)
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found.")
    return {
        "case_id": str(case.id), "customer": {"id": str(case.customer_id), "name": case.customer.name},
        "invoice_id": str(case.invoice_id) if case.invoice_id else None,
        "stored_state": case.current_state.value, "priority": case.priority.value,
        "actions": [{"id": str(action.id), "type": action.action_type.value, "status": action.status.value,
                     "approval_status": action.approval_status.value, "reason": action.reason,
                     "executed_at": action.executed_at} for action in case.actions],
        "evaluation": case_evaluation_dict(evaluate_case(case, simulation_date)),
    }


@router.get("/cases/{case_id}/evaluation", summary="Evaluate a recovery case using factual rules")
def evaluate_recovery_case(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    simulation_date = _simulation_date(db)
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found.")
    return case_evaluation_dict(evaluate_case(case, simulation_date))


@router.get("/cases/{case_id}/recommendation", response_model=RecoveryRecommendation, summary="Recommend the next operator action for a recovery case")
def get_case_recommendation(case_id: UUID, db: Session = Depends(get_db)) -> RecoveryRecommendation:
    simulation_date = _simulation_date(db)
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found.")
    return recommend_case(case, simulation_date)


@customer_recovery_router.get("/customers/{customer_id}/recovery-status", summary="Evaluate customer recovery facts")
def customer_recovery_status(customer_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    simulation_date = _simulation_date(db)
    customer = db.scalar(select(Customer).where(Customer.id == customer_id).options(selectinload(Customer.invoices)))
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    cases = db.scalars(_case_query().where(RecoveryCase.customer_id == customer_id)).all()
    invoice_facts = [{"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number,
                      "facts": asdict(evaluate_invoice(invoice, simulation_date))}
                     for invoice in customer.invoices]
    return {
        "customer_id": str(customer.id), "customer_name": customer.name, "segment": customer.segment,
        "simulation_date": simulation_date, "invoices": invoice_facts,
        "cases": [case_evaluation_dict(evaluate_case(case, simulation_date)) for case in cases],
    }


@router.get("/portfolio/summary", summary="Return deterministic recovery metrics")
def portfolio_recovery_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    started_at = perf_counter()
    stage_started = perf_counter()
    simulation_date = _simulation_date(db)
    load_state_ms = elapsed_ms(stage_started)
    stage_started = perf_counter()
    summary = recovery_summary(db, simulation_date)
    calculate_summary_ms = elapsed_ms(stage_started)
    log_timing(
        "recovery_summary_timing", total_ms=elapsed_ms(started_at),
        load_state_ms=load_state_ms, calculate_summary_ms=calculate_summary_ms,
    )
    return {"simulation_date": simulation_date, **summary}
