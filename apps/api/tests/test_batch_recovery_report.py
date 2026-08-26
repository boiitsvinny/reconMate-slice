from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.domain import (
    AuditEvent,
    Customer,
    ExternalPaymentRequest,
    Invoice,
    InvoiceStatus,
    Payment,
    PromiseStatus,
    PromiseToPay,
    ProviderEvent,
    RecoveryAction,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCase,
    RecoveryPriority,
    RecoveryState,
)
from app.reporting.batch_recovery import build_batch_recovery_proof

OPERATING_DATE = date(2026, 8, 26)


def _fixture():
    recovered_customer = Customer(id=uuid4(), name="Recovered Co", account_reference="BATCH-1")
    recovered_invoice = Invoice(
        id=uuid4(), customer=recovered_customer, invoice_number="BATCH-PAID",
        issue_date=OPERATING_DATE - timedelta(days=60), due_date=OPERATING_DATE - timedelta(days=30),
        original_amount=Decimal("500"), outstanding_amount=Decimal("0"), status=InvoiceStatus.PAID,
    )
    # The pre-due payment is deliberately not recovery. Only the post-due 400 is.
    Payment(id=uuid4(), invoice=recovered_invoice, amount=Decimal("100"), payment_date=recovered_invoice.due_date, reference="pre-due")
    recovered_payment = Payment(id=uuid4(), invoice=recovered_invoice, amount=Decimal("400"), payment_date=OPERATING_DATE - timedelta(days=5), reference="persisted-full")
    recovered_case = RecoveryCase(
        id=uuid4(), customer=recovered_customer, invoice=recovered_invoice,
        current_state=RecoveryState.RESOLVED, priority=RecoveryPriority.NORMAL,
    )

    partial_customer = Customer(id=uuid4(), name="Partial Co", account_reference="BATCH-2", is_strategic_account=True)
    partial_invoice = Invoice(
        id=uuid4(), customer=partial_customer, invoice_number="BATCH-PARTIAL",
        issue_date=OPERATING_DATE - timedelta(days=70), due_date=OPERATING_DATE - timedelta(days=40),
        original_amount=Decimal("1000"), outstanding_amount=Decimal("600"), status=InvoiceStatus.PARTIALLY_PAID,
    )
    partial_payment = Payment(id=uuid4(), invoice=partial_invoice, amount=Decimal("400"), payment_date=OPERATING_DATE - timedelta(days=4), reference="provider-pay")
    PromiseToPay(
        id=uuid4(), customer=partial_customer, invoice=partial_invoice, promised_amount=Decimal("600"),
        promised_date=OPERATING_DATE + timedelta(days=3), status=PromiseStatus.ACTIVE,
    )
    partial_case = RecoveryCase(
        id=uuid4(), customer=partial_customer, invoice=partial_invoice,
        current_state=RecoveryState.PROMISE_MONITORING, priority=RecoveryPriority.HIGH,
    )

    disputed_customer = Customer(id=uuid4(), name="Disputed Co", account_reference="BATCH-3")
    disputed_invoice = Invoice(
        id=uuid4(), customer=disputed_customer, invoice_number="BATCH-DISPUTED",
        issue_date=OPERATING_DATE - timedelta(days=50), due_date=OPERATING_DATE - timedelta(days=20),
        original_amount=Decimal("300"), outstanding_amount=Decimal("300"), status=InvoiceStatus.DISPUTED,
    )
    disputed_case = RecoveryCase(
        id=uuid4(), customer=disputed_customer, invoice=disputed_invoice,
        current_state=RecoveryState.AWAITING_CUSTOMER, priority=RecoveryPriority.HIGH,
    )

    actions = [
        RecoveryAction(id=uuid4(), recovery_case_id=recovered_case.id, action_type=RecoveryActionType.CLOSE_CASE, status=RecoveryActionStatus.EXECUTED),
        RecoveryAction(id=uuid4(), recovery_case_id=partial_case.id, action_type=RecoveryActionType.FOLLOW_UP, status=RecoveryActionStatus.PENDING_APPROVAL),
        RecoveryAction(id=uuid4(), recovery_case_id=disputed_case.id, action_type=RecoveryActionType.OUTREACH, status=RecoveryActionStatus.HELD),
    ]
    request = ExternalPaymentRequest(
        id=uuid4(), recovery_case_id=partial_case.id, customer_id=partial_customer.id, invoice_id=partial_invoice.id,
        provider="PROVIDER_DEMO", provider_mode="DEMO", provider_reference="demo_req_batch",
        requested_amount=Decimal("400"), paid_amount=Decimal("400"), status="PAID",
        purpose="Invoice payment request", operator_id="operator",
    )
    provider_event = ProviderEvent(
        id=uuid4(), payment_request_id=request.id, payment_id=partial_payment.id, provider="PROVIDER_DEMO",
        provider_event_id="demo_evt_batch", provider_payment_reference="demo_pay_batch",
        event_type="payment_request.paid", payload={},
        evidence={"source": "Provider Demo Mode", "outstanding_before": "1000", "outstanding_after": "600"},
    )
    duplicate = AuditEvent(
        id=uuid4(), entity_type="ExternalPaymentRequest", entity_id=request.id,
        event_type="PROVIDER_DUPLICATE_EVENT_IGNORED", occurred_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
    proof = build_batch_recovery_proof(
        simulation_date=OPERATING_DATE,
        cycle=7,
        invoices=[recovered_invoice, partial_invoice, disputed_invoice],
        cases=[recovered_case, partial_case, disputed_case],
        actions=actions,
        payment_requests=[request],
        provider_events=[provider_event],
        imported_invoice_ids={partial_invoice.id},
        duplicate_provider_audits=[duplicate],
    )
    return proof, recovered_payment, partial_payment, partial_case, disputed_case


def test_batch_recovery_reconciles_qualifying_payments_without_double_counting() -> None:
    proof, _, partial_payment, partial_case, _ = _fixture()
    reconciliation = proof["reconciliation"]
    assert reconciliation["starting_overdue_exposure"] == "1700.00"
    assert reconciliation["observed_recovery"] == "800.00"
    assert reconciliation["remaining_overdue_exposure"] == "900.00"
    assert reconciliation["equation_holds"] is True
    assert reconciliation["qualifying_payment_count"] == 2
    assert reconciliation["recovery_rate"] == "47.06"
    assert proof["action_outcomes"]["provider_events_received"] == 1
    assert proof["action_outcomes"]["payments_persisted"] == 2
    assert proof["action_outcomes"]["duplicate_provider_events_ignored"] == 1
    provider_row = next(row for row in proof["payment_evidence"] if row["payment_id"] == str(partial_payment.id))
    assert provider_row["case_id"] == str(partial_case.id)
    assert provider_row["invoice_id"] == str(partial_case.invoice.id)
    assert provider_row["customer_id"] == str(partial_case.customer.id)
    assert provider_row["request_reference"] == "demo_req_batch"
    assert provider_row["event_reference"] == "demo_evt_batch"
    assert provider_row["provider_payment_reference"] == "demo_pay_batch"
    assert provider_row["outstanding_before"] == "1000" and provider_row["outstanding_after"] == "600"


def test_batch_recovery_classifies_full_partial_and_current_open_state() -> None:
    proof, *_ = _fixture()
    reconciliation = proof["reconciliation"]
    assert reconciliation["recovered_invoice_count"] == 1
    assert reconciliation["partially_recovered_invoice_count"] == 1
    assert reconciliation["remaining_open_overdue_invoice_count"] == 2
    assert reconciliation["fully_recovered_account_count"] == 1
    assert reconciliation["partially_recovered_account_count"] == 1
    assert proof["scope"]["provenance"] == "Mixed: CSV Import + Synthetic Demo Sandbox"
    assert proof["metric_metadata"]["observed_recovery"] == {
        "unit": "INR", "scope": "overdue cohort persisted payments", "window": "post-due through operating date",
    }
    assert {item["source"] for item in proof["payment_provenance"]} == {"Synthetic Demo Sandbox", "Provider Demo Mode"}


def test_stopping_rules_are_authoritative_and_paid_cases_are_not_targets() -> None:
    proof, _, _, partial_case, disputed_case = _fixture()
    stopping = proof["stopping_rules"]
    assert stopping["deliberate_hold_count"] == 2
    assert stopping["active_dispute_hold_count"] == 1
    assert stopping["active_promise_hold_count"] == 1
    assert stopping["resolved_or_paid_case_count"] == 1
    assert stopping["blocked_action_count"] == 1
    assert stopping["approval_required_case_count"] == 2
    assert stopping["unresolved_exception_count"] == 2
    assert stopping["unresolved_exception_categories"] == {
        "elevated_open_cases": 2, "broken_promise_cases": 0,
        "active_dispute_cases": 1, "workflow_requests_awaiting_approval": 1,
    }
    assert stopping["exception_categories_overlap"] is True
    assert stopping["other_blocked_case_count"] == 0
    assert {row["case_id"] for row in stopping["hold_evidence"]} == {str(partial_case.id), str(disputed_case.id)}


def test_baseline_uses_same_scope_and_makes_no_payment_counterfactual() -> None:
    proof, *_ = _fixture()
    baseline = proof["baseline"]
    assert baseline["same_scope"] is True
    assert baseline["same_operating_date"] == OPERATING_DATE
    assert baseline["age_only_target_count"] == 2
    assert baseline["blocker_violations_avoided"] == 2
    assert "Payment outcomes are not re-simulated" in baseline["limitation"]
    assert proof["reconciliation"]["measurement_note"].endswith("It does not claim ReconMate caused payment.")
    assert "recovery_amount" not in baseline


def test_future_invoice_is_excluded_consistently_from_report_scope() -> None:
    customer = Customer(id=uuid4(), name="Future Co", account_reference="FUTURE")
    invoice = Invoice(
        id=uuid4(), customer=customer, invoice_number="FUTURE-1",
        issue_date=OPERATING_DATE + timedelta(days=1), due_date=OPERATING_DATE - timedelta(days=10),
        original_amount=Decimal("1000"), outstanding_amount=Decimal("1000"), status=InvoiceStatus.OVERDUE,
    )
    case = RecoveryCase(id=uuid4(), customer=customer, invoice=invoice, current_state=RecoveryState.NEW, priority=RecoveryPriority.HIGH)
    proof = build_batch_recovery_proof(
        simulation_date=OPERATING_DATE, cycle=7, invoices=[invoice], cases=[case], actions=[],
        payment_requests=[], provider_events=[], imported_invoice_ids=set(),
    )
    assert proof["scope"]["invoice_count"] == 0 and proof["scope"]["case_count"] == 0
    assert proof["reconciliation"]["starting_overdue_exposure"] == "0.00"
    assert proof["reconciliation"]["remaining_overdue_exposure"] == "0.00"
