"""Operator-approved payment requests and safe Provider Demo Mode events."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.workflow import _case_query, _simulation_date
from app.db.session import get_db
from app.models.domain import ExternalPaymentRequest, RecoveryCase
from app.payments.provider import PaymentProviderError, get_payment_request_provider
from app.payments.schemas import CreatePaymentRequestInput, DemoPaymentEventInput, ExternalPaymentRequestResponse, ProviderEventResponse, ProviderModeResponse
from app.payments.service import create_external_payment_request, ingest_demo_payment_event

router = APIRouter(prefix="/payment-provider", tags=["payment provider boundary"])


def payment_request_response(item: ExternalPaymentRequest) -> ExternalPaymentRequestResponse:
    return ExternalPaymentRequestResponse(
        id=str(item.id), case_id=str(item.recovery_case_id), customer_id=str(item.customer_id), invoice_id=str(item.invoice_id),
        provider=item.provider, provider_mode=item.provider_mode, provider_reference=item.provider_reference,
        provider_url=item.provider_url, requested_amount=item.requested_amount, paid_amount=item.paid_amount,
        status=item.status, purpose=item.purpose, operator_id=item.operator_id,
        failure_reason=item.failure_reason, created_at=item.created_at,
    )


@router.get("/mode", response_model=ProviderModeResponse)
def provider_mode() -> ProviderModeResponse:
    try:
        provider = get_payment_request_provider()
    except PaymentProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    label = "Razorpay test mode" if provider.mode == "TEST" else "Provider Demo Mode"
    return ProviderModeResponse(provider=provider.name, mode=provider.mode, label=label)


@router.get("/requests", response_model=list[ExternalPaymentRequestResponse])
def list_payment_requests(case_id: UUID | None = Query(default=None), db: Session = Depends(get_db)) -> list[ExternalPaymentRequestResponse]:
    query = select(ExternalPaymentRequest).order_by(ExternalPaymentRequest.created_at.desc())
    if case_id is not None:
        query = query.where(ExternalPaymentRequest.recovery_case_id == case_id)
    return [payment_request_response(item) for item in db.scalars(query)]


@router.post("/cases/{case_id}/requests", response_model=ExternalPaymentRequestResponse, status_code=201)
def create_payment_request(case_id: UUID, payload: CreatePaymentRequestInput, db: Session = Depends(get_db)) -> ExternalPaymentRequestResponse:
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    try:
        provider = get_payment_request_provider()
    except PaymentProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return payment_request_response(create_external_payment_request(db, case, _simulation_date(db), payload, provider))


@router.post("/events/demo", response_model=ProviderEventResponse)
def apply_demo_payment_event(payload: DemoPaymentEventInput, db: Session = Depends(get_db)) -> ProviderEventResponse:
    payment_request = db.scalar(select(ExternalPaymentRequest).where(ExternalPaymentRequest.provider_reference == payload.provider_reference))
    if payment_request is None:
        raise HTTPException(status_code=404, detail="Unknown provider payment-request reference.")
    case = db.scalar(_case_query().where(RecoveryCase.id == payment_request.recovery_case_id))
    if case is None:
        raise HTTPException(status_code=409, detail="The provider request no longer maps to a recovery case.")
    return ingest_demo_payment_event(db, payment_request, case, _simulation_date(db), payload)
