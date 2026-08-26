"""Operator-controlled external request creation and idempotent payment ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intelligence.operational_service import evaluate_case_intelligence
from app.models.domain import (
    AuditEvent, ExternalPaymentRequest, InvoiceStatus, Payment, ProviderEvent, RecoveryCase, RecoveryState,
)
from app.payments.provider import PaymentProviderError, PaymentRequestProvider
from app.payments.schemas import CreatePaymentRequestInput, DemoPaymentEventInput, ProviderEventResponse
from app.recommendations.schemas import RecommendedAction
from app.recommendations.service import recommend_case
from app.recovery.engine import evaluate_case, synchronize_recovery_states

SUPPORTED_PAYMENT_REQUEST_ACTIONS = {RecommendedAction.SEND_PAYMENT_REMINDER, RecommendedAction.REQUEST_PAYMENT_DATE}


def _fail(message: str, code: int = status.HTTP_409_CONFLICT) -> None:
    raise HTTPException(status_code=code, detail=message)


def create_external_payment_request(db: Session, case: RecoveryCase, operating_date, payload: CreatePaymentRequestInput, provider: PaymentRequestProvider) -> ExternalPaymentRequest:
    if payload.operator_confirmed is not True:
        _fail("Explicit operator confirmation is required.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if case.invoice is None:
        _fail("A payment request requires a related invoice.")
    if case.current_state in {RecoveryState.AWAITING_CUSTOMER, RecoveryState.PROMISE_MONITORING, RecoveryState.RESOLVED, RecoveryState.CLOSED}:
        _fail(f"A recovery case in {case.current_state.value} state cannot create a payment request.")
    if case.invoice.outstanding_amount <= 0 or case.invoice.status is InvoiceStatus.PAID:
        _fail("A payment request requires a positive invoice outstanding amount.")
    recommendation = recommend_case(case, operating_date)
    evaluation = evaluate_case(case, operating_date)
    if recommendation.recommended_action not in SUPPORTED_PAYMENT_REQUEST_ACTIONS:
        _fail(f"{recommendation.recommended_action.value} does not support an external payment request.")
    if recommendation.blockers or not evaluation.eligibility.allowed:
        _fail("Current recovery blockers do not allow a payment request.")
    if payload.requested_amount > case.invoice.outstanding_amount:
        _fail("Requested amount cannot exceed the current invoice outstanding amount.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    duplicate = db.scalar(select(ExternalPaymentRequest.id).where(
        ExternalPaymentRequest.recovery_case_id == case.id,
        ExternalPaymentRequest.status.in_(["PENDING_PROVIDER", "ACTIVE", "PARTIALLY_PAID"]),
    ))
    if duplicate is not None:
        _fail("An active payment request already exists for this case.")
    record = ExternalPaymentRequest(
        recovery_case_id=case.id, customer_id=case.customer.id, invoice_id=case.invoice.id,
        provider=provider.name, provider_mode=provider.mode, requested_amount=payload.requested_amount,
        status="PENDING_PROVIDER", purpose=payload.purpose, operator_id=payload.operator_id,
    )
    db.add(record)
    db.flush()
    try:
        created = provider.create_payment_request(
            request_id=record.id, amount=payload.requested_amount, customer_name=case.customer.name,
            invoice_number=case.invoice.invoice_number, purpose=payload.purpose,
        )
        record.provider_reference, record.provider_url, record.status = created.reference, created.url, created.status
        db.add(AuditEvent(
            entity_type="ExternalPaymentRequest", entity_id=record.id, event_type="EXTERNAL_PAYMENT_REQUEST_CREATED",
            actor_type="operator", actor_id=payload.operator_id,
            payload={"source": "Provider Demo Mode" if provider.mode == "DEMO" else "Razorpay Test Mode",
                     "provider": provider.name, "provider_mode": provider.mode, "provider_reference": created.reference,
                     "customer_id": str(case.customer.id), "case_id": str(case.id), "invoice_id": str(case.invoice.id),
                     "requested_amount": str(payload.requested_amount),
                     "financial_mutation": "NONE", "outstanding_before": str(case.invoice.outstanding_amount),
                     "outstanding_after": str(case.invoice.outstanding_amount)},
            occurred_at=datetime.now(UTC),
        ))
        db.commit(); db.refresh(record)
        return record
    except PaymentProviderError as exc:
        record.status, record.failure_reason = "FAILED", str(exc)
        db.add(AuditEvent(
            entity_type="ExternalPaymentRequest", entity_id=record.id, event_type="EXTERNAL_PAYMENT_REQUEST_FAILED",
            actor_type="system", payload={"provider": provider.name, "provider_mode": provider.mode, "reason": str(exc)},
            occurred_at=datetime.now(UTC),
        ))
        db.commit()
        _fail(str(exc), status.HTTP_502_BAD_GATEWAY)


def ingest_demo_payment_event(db: Session, request: ExternalPaymentRequest, case: RecoveryCase, operating_date, payload: DemoPaymentEventInput) -> ProviderEventResponse:
    if request.provider_mode != "DEMO" or request.provider != "PROVIDER_DEMO":
        _fail("The demo event endpoint only accepts Provider Demo Mode requests.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    existing = db.scalar(select(ProviderEvent).where(or_(
        (ProviderEvent.provider == request.provider) & (ProviderEvent.provider_event_id == payload.event_id),
        (ProviderEvent.provider == request.provider) & (ProviderEvent.provider_payment_reference == payload.payment_reference),
    )))
    if existing is not None:
        duplicate_evidence = _record_duplicate_event(db, request, existing, payload, case)
        return ProviderEventResponse(
            duplicate=True, provider_event_id=existing.provider_event_id, payment_id=str(existing.payment_id),
            payment_request_id=str(existing.payment_request_id), evidence=duplicate_evidence,
        )
    if request.status not in {"ACTIVE", "PARTIALLY_PAID"}:
        _fail(f"A payment event cannot be applied to a request in {request.status} state.")
    if payload.provider_reference != request.provider_reference:
        _fail("The provider event does not match the payment-request reference.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if request.recovery_case_id != case.id or request.customer_id != case.customer.id:
        _fail("The payment request no longer maps to its recovery case and customer.")
    invoice = case.invoice
    if invoice is None or invoice.id != request.invoice_id:
        _fail("The payment request no longer maps to its invoice.")
    if payload.payment_date > operating_date:
        _fail("Payment date cannot be after the current operating date.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    remaining_request_amount = request.requested_amount - request.paid_amount
    if invoice.outstanding_amount <= 0 or remaining_request_amount <= 0:
        _fail("The payment request has no remaining payable amount.")
    if payload.amount > invoice.outstanding_amount or payload.amount > remaining_request_amount:
        _fail("Payment amount cannot exceed the valid outstanding or requested amount.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if payload.event_type == "payment_request.paid" and payload.amount != remaining_request_amount:
        _fail("A paid event must clear the remaining payment-request amount.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if payload.event_type == "payment_request.partially_paid" and payload.amount >= remaining_request_amount:
        _fail("A partial-payment event must leave a positive request balance.", status.HTTP_422_UNPROCESSABLE_CONTENT)
    before_intelligence = evaluate_case_intelligence(case, operating_date)
    before_recommendation = recommend_case(case, operating_date)
    before_outstanding = invoice.outstanding_amount
    payment = Payment(invoice=invoice, amount=payload.amount, payment_date=payload.payment_date, reference=payload.payment_reference)
    db.add(payment)
    invoice.outstanding_amount -= payload.amount
    request.paid_amount += payload.amount
    invoice.status = InvoiceStatus.PAID if invoice.outstanding_amount == 0 else InvoiceStatus.PARTIALLY_PAID
    request.status = "PAID" if request.paid_amount == request.requested_amount else "PARTIALLY_PAID"
    db.flush()
    synchronization = synchronize_recovery_states(db, operating_date, commit=False)
    after_intelligence = evaluate_case_intelligence(case, operating_date)
    after_recommendation = recommend_case(case, operating_date)
    evidence = {
        "source": "Provider Demo Mode", "provider": request.provider, "provider_mode": request.provider_mode,
        "chronology": "Provider payment event received after payment request creation; processing order does not prove causation.",
        "customer_id": str(request.customer_id), "case_id": str(request.recovery_case_id),
        "invoice_id": str(request.invoice_id), "payment_request_id": str(request.id),
        "payment_id": str(payment.id), "provider_event_id": payload.event_id,
        "provider_reference": request.provider_reference, "provider_payment_reference": payload.payment_reference,
        "event_type": payload.event_type, "financial_mutation": "PAYMENT_PERSISTED",
        "outstanding_before": str(before_outstanding), "outstanding_after": str(invoice.outstanding_amount),
        "score_before": before_intelligence.score, "score_after": after_intelligence.score,
        "recommendation_before": before_recommendation.recommended_action.value,
        "recommendation_after": after_recommendation.recommended_action.value,
        "recovery_synchronization": synchronization,
    }
    event = ProviderEvent(
        payment_request_id=request.id, payment_id=payment.id, provider=request.provider,
        provider_event_id=payload.event_id, provider_payment_reference=payload.payment_reference,
        event_type=payload.event_type, payload=payload.model_dump(mode="json"), evidence=evidence,
    )
    db.add(event)
    db.add(AuditEvent(
        entity_type="ExternalPaymentRequest", entity_id=request.id, event_type="PROVIDER_PAYMENT_EVENT_APPLIED",
        actor_type="provider_demo", actor_id=payload.event_id,
        payload={"provider": request.provider, "payment_id": str(payment.id), **evidence}, occurred_at=datetime.now(UTC),
    ))
    try:
        db.commit(); db.refresh(event)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ProviderEvent).where(or_(
            (ProviderEvent.provider == request.provider) & (ProviderEvent.provider_event_id == payload.event_id),
            (ProviderEvent.provider == request.provider) & (ProviderEvent.provider_payment_reference == payload.payment_reference),
        )))
        if existing is None:
            raise
        duplicate_evidence = _record_duplicate_event(db, request, existing, payload, case)
        return ProviderEventResponse(duplicate=True, provider_event_id=existing.provider_event_id, payment_id=str(existing.payment_id), payment_request_id=str(existing.payment_request_id), evidence=duplicate_evidence)
    return ProviderEventResponse(duplicate=False, provider_event_id=event.provider_event_id, payment_id=str(payment.id), payment_request_id=str(request.id), evidence=evidence)


def _record_duplicate_event(
    db: Session,
    request: ExternalPaymentRequest,
    existing: ProviderEvent,
    payload: DemoPaymentEventInput,
    case: RecoveryCase,
) -> dict:
    """Persist proof that a provider replay was observed without applying it twice."""
    outstanding = str(case.invoice.outstanding_amount) if case.invoice is not None else None
    replay = {
        "ignored": True,
        "original_event": existing.provider_event_id,
        "replayed_event": payload.event_id,
        "financial_mutation": "NONE",
        "outstanding_before": outstanding,
        "outstanding_after": outstanding,
    }
    db.add(AuditEvent(
        entity_type="ExternalPaymentRequest", entity_id=request.id,
        event_type="PROVIDER_DUPLICATE_EVENT_IGNORED", actor_type="provider_demo", actor_id=payload.event_id,
        payload={
            "source": "Provider Demo Mode", "provider": request.provider, "provider_mode": request.provider_mode,
            "customer_id": str(request.customer_id), "case_id": str(request.recovery_case_id),
            "invoice_id": str(request.invoice_id), "payment_request_id": str(request.id),
            "provider_reference": request.provider_reference,
            "provider_event_id": payload.event_id, "provider_payment_reference": payload.payment_reference,
            **replay,
        },
        occurred_at=datetime.now(UTC),
    ))
    db.commit()
    return {**existing.evidence, "duplicate_replay": replay}
