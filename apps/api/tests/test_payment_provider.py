from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.payments import apply_demo_payment_event
from app.models.domain import AuditEvent, Customer, ExternalPaymentRequest, Invoice, InvoiceStatus, Payment, ProviderEvent, RecoveryCase, RecoveryPriority, RecoveryState
from app.payments.provider import CreatedPaymentRequest, PaymentProviderError
from app.payments.schemas import CreatePaymentRequestInput, DemoPaymentEventInput
from app.payments.service import create_external_payment_request, ingest_demo_payment_event

OPERATING_DATE = date(2026, 8, 26)


class FakeSession:
    def __init__(self, scalar_results=None):
        self.added = []
        self.scalar_results = list(scalar_results or [])
        self.commits = 0
        self.rolled_back = False

    def add(self, item): self.added.append(item)
    def scalar(self, _query): return self.scalar_results.pop(0) if self.scalar_results else None
    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None: item.id = uuid4()
            if isinstance(item, Payment) and item.invoice_id is None: item.invoice_id = item.invoice.id
    def commit(self): self.commits += 1
    def refresh(self, _item): pass
    def rollback(self): self.rolled_back = True


class DemoProvider:
    name = "PROVIDER_DEMO"
    mode = "DEMO"
    def create_payment_request(self, **kwargs):
        return CreatedPaymentRequest(reference=f"demo_payreq_{kwargs['request_id'].hex}", status="ACTIVE", url=None)


class FailedProvider(DemoProvider):
    def create_payment_request(self, **_kwargs): raise PaymentProviderError("Provider unavailable.")


def case(*, disputed=False, outstanding="500", state: RecoveryState | None = None):
    customer = Customer(id=uuid4(), name="Provider Test", account_reference=f"PAY-{uuid4()}")
    invoice = Invoice(id=uuid4(), customer=customer, invoice_number="PAY-1", issue_date=OPERATING_DATE - timedelta(days=45), due_date=OPERATING_DATE - timedelta(days=15), original_amount=Decimal("500"), outstanding_amount=Decimal(outstanding), status=InvoiceStatus.DISPUTED if disputed else InvoiceStatus.OVERDUE)
    return RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=state or (RecoveryState.AWAITING_CUSTOMER if disputed else RecoveryState.IN_PROGRESS), priority=RecoveryPriority.NORMAL)


def create_payload(amount="500"):
    return CreatePaymentRequestInput(operator_id="judge-operator", requested_amount=Decimal(amount), operator_confirmed=True)


def external_request(item, amount="500"):
    return ExternalPaymentRequest(id=uuid4(), recovery_case_id=item.id, customer_id=item.customer.id, invoice_id=item.invoice.id, provider="PROVIDER_DEMO", provider_mode="DEMO", provider_reference="demo_payreq_known", requested_amount=Decimal(amount), paid_amount=Decimal("0"), status="ACTIVE", purpose="Invoice payment request", operator_id="judge-operator")


def event(amount="500", event_id="evt-1", payment_reference="demo_pay-1", event_type="payment_request.paid"):
    return DemoPaymentEventInput(event_id=event_id, provider_reference="demo_payreq_known", payment_reference=payment_reference, amount=Decimal(amount), payment_date=OPERATING_DATE, event_type=event_type)


def test_external_action_requires_explicit_operator_confirmation() -> None:
    payload = CreatePaymentRequestInput.model_construct(operator_id="operator", requested_amount=Decimal("500"), purpose="test", operator_confirmed=False)
    with pytest.raises(HTTPException, match="Explicit operator confirmation"):
        create_external_payment_request(FakeSession(), case(), OPERATING_DATE, payload, DemoProvider())


def test_blocked_recommendation_cannot_create_payment_request() -> None:
    with pytest.raises(HTTPException, match="does not support"):
        create_external_payment_request(FakeSession(), case(disputed=True, state=RecoveryState.IN_PROGRESS), OPERATING_DATE, create_payload(), DemoProvider())


@pytest.mark.parametrize("state", [RecoveryState.AWAITING_CUSTOMER, RecoveryState.PROMISE_MONITORING, RecoveryState.RESOLVED, RecoveryState.CLOSED])
def test_blocked_monitoring_resolved_or_closed_case_cannot_create_payment_request(state: RecoveryState) -> None:
    with pytest.raises(HTTPException, match="cannot create"):
        create_external_payment_request(FakeSession(), case(state=state), OPERATING_DATE, create_payload(), DemoProvider())


def test_paid_invoice_cannot_create_payment_request() -> None:
    item = case(outstanding="0")
    item.invoice.status = InvoiceStatus.PAID
    with pytest.raises(HTTPException, match="positive invoice outstanding"):
        create_external_payment_request(FakeSession(), item, OPERATING_DATE, create_payload(), DemoProvider())


def test_provider_reference_and_demo_provenance_persist() -> None:
    db = FakeSession()
    item = case()
    before = (item.invoice.outstanding_amount, item.invoice.status, len(item.invoice.payments))
    request = create_external_payment_request(db, item, OPERATING_DATE, create_payload(), DemoProvider())
    assert request.provider_reference.startswith("demo_payreq_")
    assert request.provider == "PROVIDER_DEMO" and request.provider_mode == "DEMO"
    assert request.status == "ACTIVE" and db.commits == 1
    assert (item.invoice.outstanding_amount, item.invoice.status, len(item.invoice.payments)) == before
    audit = next(value for value in db.added if isinstance(value, AuditEvent))
    assert audit.payload["source"] == "Provider Demo Mode"
    assert audit.payload["financial_mutation"] == "NONE"
    assert audit.payload["outstanding_before"] == audit.payload["outstanding_after"] == "500"
    assert audit.payload["customer_id"] == str(item.customer.id)


def test_provider_failure_is_persisted_safely() -> None:
    db = FakeSession()
    with pytest.raises(HTTPException, match="Provider unavailable"):
        create_external_payment_request(db, case(), OPERATING_DATE, create_payload(), FailedProvider())
    request = next(item for item in db.added if isinstance(item, ExternalPaymentRequest))
    assert request.status == "FAILED" and request.failure_reason == "Provider unavailable."
    assert db.commits == 1


def test_malformed_demo_event_fails_schema_validation() -> None:
    with pytest.raises(ValidationError):
        DemoPaymentEventInput.model_validate({"event_id": "", "provider_reference": "x", "payment_reference": "p", "amount": -1, "payment_date": "bad", "event_type": "unknown"})


def test_unknown_provider_reference_is_rejected() -> None:
    with pytest.raises(HTTPException, match="Unknown provider"):
        apply_demo_payment_event(event(), FakeSession())


def test_cancelled_request_fails_without_financial_change() -> None:
    item = case()
    request = external_request(item)
    request.status = "CANCELLED"
    with pytest.raises(HTTPException, match="CANCELLED"):
        ingest_demo_payment_event(FakeSession(), request, item, OPERATING_DATE, event())
    assert item.invoice.outstanding_amount == Decimal("500") and not item.invoice.payments


def test_event_reference_and_domain_identity_must_match() -> None:
    item = case()
    request = external_request(item)
    mismatched_reference = event().model_copy(update={"provider_reference": "another-request"})
    with pytest.raises(HTTPException, match="does not match"):
        ingest_demo_payment_event(FakeSession(), request, item, OPERATING_DATE, mismatched_reference)
    request.customer_id = uuid4()
    with pytest.raises(HTTPException, match="recovery case and customer"):
        ingest_demo_payment_event(FakeSession(), request, item, OPERATING_DATE, event())


def test_payment_cannot_exceed_outstanding(monkeypatch) -> None:
    item = case(outstanding="500")
    with pytest.raises(HTTPException, match="cannot exceed"):
        ingest_demo_payment_event(FakeSession(), external_request(item, "600"), item, OPERATING_DATE, event("600"),)


def test_payment_cannot_exceed_remaining_request_amount() -> None:
    item = case(outstanding="500")
    with pytest.raises(HTTPException, match="cannot exceed"):
        ingest_demo_payment_event(FakeSession(), external_request(item, "300"), item, OPERATING_DATE, event("400"))


def test_successful_event_uses_payment_model_updates_financial_state_and_evidence(monkeypatch) -> None:
    item = case()
    request = external_request(item)
    db = FakeSession()
    monkeypatch.setattr("app.payments.service.synchronize_recovery_states", lambda _db, _date, commit=False: {"cases_evaluated": 1, "cases_changed": 1})
    result = ingest_demo_payment_event(db, request, item, OPERATING_DATE, event())
    payment = next(value for value in db.added if isinstance(value, Payment))
    provider_event = next(value for value in db.added if isinstance(value, ProviderEvent))
    assert payment.amount == Decimal("500") and item.invoice.outstanding_amount == 0
    assert item.invoice.status is InvoiceStatus.PAID and request.status == "PAID"
    assert result.evidence["outstanding_before"] == "500"
    assert result.evidence["outstanding_after"] == "0"
    assert result.evidence["score_before"] > result.evidence["score_after"]
    assert result.evidence["recommendation_after"] == "NO_ACTION_REQUIRED"
    assert result.evidence["customer_id"] == str(request.customer_id)
    assert result.evidence["case_id"] == str(item.id)
    assert result.evidence["invoice_id"] == str(item.invoice.id)
    assert result.evidence["payment_request_id"] == str(request.id)
    assert result.evidence["payment_id"] == str(payment.id)
    assert result.evidence["provider_event_id"] == "evt-1"
    assert result.evidence["source"] == "Provider Demo Mode"
    assert result.evidence["provider_reference"] == request.provider_reference
    assert result.evidence["provider_payment_reference"] == "demo_pay-1"
    assert result.evidence["financial_mutation"] == "PAYMENT_PERSISTED"
    assert provider_event.provider == "PROVIDER_DEMO" and result.duplicate is False


def test_duplicate_event_and_payment_reference_are_idempotent() -> None:
    item = case()
    request = external_request(item)
    prior = ProviderEvent(id=uuid4(), payment_request_id=request.id, payment_id=uuid4(), provider="PROVIDER_DEMO", provider_event_id="evt-1", provider_payment_reference="demo_pay-1", event_type="payment_request.paid", payload={}, evidence={"outstanding_after": "0"})
    db = FakeSession([prior])
    result = ingest_demo_payment_event(db, request, item, OPERATING_DATE, event())
    assert result.duplicate is True
    assert item.invoice.outstanding_amount == Decimal("500")
    assert result.evidence["duplicate_replay"]["financial_mutation"] == "NONE"
    assert result.evidence["duplicate_replay"]["outstanding_before"] == result.evidence["duplicate_replay"]["outstanding_after"] == "500"
    replay_audit = next(value for value in db.added if isinstance(value, AuditEvent))
    assert replay_audit.event_type == "PROVIDER_DUPLICATE_EVENT_IGNORED"
    assert replay_audit.payload["original_event"] == "evt-1"


def test_partial_event_preserves_remaining_request_balance(monkeypatch) -> None:
    item = case()
    request = external_request(item)
    monkeypatch.setattr("app.payments.service.synchronize_recovery_states", lambda _db, _date, commit=False: {"cases_evaluated": 1, "cases_changed": 0})
    ingest_demo_payment_event(FakeSession(), request, item, OPERATING_DATE, event("200", event_type="payment_request.partially_paid"))
    assert item.invoice.outstanding_amount == Decimal("300")
    assert request.paid_amount == Decimal("200") and request.status == "PARTIALLY_PAID"
