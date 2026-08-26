"""Read-only report projections for judge-verifiable recovery evidence."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.domain import (
    AuditEvent,
    Communication,
    Customer,
    ExternalPaymentRequest,
    Invoice,
    PromiseToPay,
    ProviderEvent,
    RecoveryAction,
    RecoveryCase,
    SimulationState,
)
from app.reporting.batch_recovery import build_batch_recovery_proof

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/batch-recovery", summary="Reconcile persisted recovery evidence across the current overdue batch")
def batch_recovery_report(db: Session = Depends(get_db)):
    state = db.scalar(select(SimulationState).where(SimulationState.name == "default"))
    if state is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Synthetic simulation state has not been seeded.")
    invoices = list(db.scalars(select(Invoice).options(
        selectinload(Invoice.customer),
        selectinload(Invoice.payments),
        selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
    )))
    cases = list(db.scalars(select(RecoveryCase).options(
        selectinload(RecoveryCase.customer).selectinload(Customer.communications).selectinload(Communication.analyses),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )))
    actions = list(db.scalars(select(RecoveryAction)))
    requests = list(db.scalars(select(ExternalPaymentRequest)))
    provider_events = list(db.scalars(select(ProviderEvent)))
    import_events = list(db.scalars(select(AuditEvent).where(AuditEvent.event_type == "RECEIVABLE_IMPORTED")))
    duplicate_events = list(db.scalars(select(AuditEvent).where(AuditEvent.event_type == "PROVIDER_DUPLICATE_EVENT_IGNORED")))
    return build_batch_recovery_proof(
        simulation_date=state.simulation_date,
        cycle=state.cycle,
        invoices=invoices,
        cases=cases,
        actions=actions,
        payment_requests=requests,
        provider_events=provider_events,
        imported_invoice_ids={event.entity_id for event in import_events if event.entity_type == "Invoice"},
        duplicate_provider_audits=duplicate_events,
    )
