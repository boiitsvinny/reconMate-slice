from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.evidence.timeline import build_case_evidence_timeline
from app.models.domain import (
    AuditEvent, Customer, ExternalPaymentRequest, Invoice, InvoiceStatus, ProviderEvent,
    RecoveryAction, RecoveryActionStatus, RecoveryActionType, RecoveryCase,
    RecoveryPriority, RecoveryState,
)


class FakeSession:
    def __init__(self, audits): self.results = [audits, []]
    def scalars(self, _query): return self.results.pop(0)


def _records():
    customer = Customer(id=uuid4(), name="Scoped Account", account_reference="SCOPE-1")
    invoice = Invoice(
        id=uuid4(), customer=customer, invoice_number="SCOPE-INV", issue_date=date(2026, 6, 1),
        due_date=date(2026, 7, 1), original_amount=Decimal("500"), outstanding_amount=Decimal("200"),
        status=InvoiceStatus.PARTIALLY_PAID,
    )
    case = RecoveryCase(
        id=uuid4(), customer=customer, invoice=invoice, current_state=RecoveryState.IN_PROGRESS,
        priority=RecoveryPriority.HIGH, opened_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    action = RecoveryAction(
        id=uuid4(), recovery_case=case, action_type=RecoveryActionType.ESCALATE,
        status=RecoveryActionStatus.EXECUTED, recommendation_action="PREPARE_ESCALATION",
    )
    request = ExternalPaymentRequest(
        id=uuid4(), recovery_case_id=case.id, customer_id=customer.id, invoice_id=invoice.id,
        provider="PROVIDER_DEMO", provider_mode="DEMO", provider_reference="demo_req_1",
        requested_amount=Decimal("300"), paid_amount=Decimal("300"), status="PAID",
        purpose="Invoice payment request", operator_id="operator",
    )
    provider_event = ProviderEvent(
        id=uuid4(), payment_request_id=request.id, payment_id=uuid4(), provider="PROVIDER_DEMO",
        provider_event_id="demo_evt_1", provider_payment_reference="demo_pay_1",
        event_type="payment_request.paid", payload={}, received_at=datetime(2026, 8, 2, tzinfo=UTC),
        evidence={
            "source": "Provider Demo Mode", "customer_id": str(customer.id), "case_id": str(case.id),
            "invoice_id": str(invoice.id), "outstanding_before": "500", "outstanding_after": "200",
            "score_before": 80, "score_after": 55,
            "recommendation_before": "ESCALATE", "recommendation_after": "FOLLOW_UP",
        },
    )
    return case, action, request, provider_event


def test_timeline_is_scoped_and_provider_references_match_entities() -> None:
    case, action, request, provider_event = _records()
    action_audit = AuditEvent(
        id=uuid4(), entity_type="RecoveryAction", entity_id=action.id,
        event_type="RECOVERY_ACTION_EXECUTED", actor_type="operator",
        payload={"case_id": str(uuid4()), "invoice_id": str(uuid4()), "simulated": True},
        occurred_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    timeline = build_case_evidence_timeline(FakeSession([action_audit]), case, [request], [provider_event])  # type: ignore[arg-type]

    stored = next(item for item in timeline if item["event_type"] == "RECOVERY_ACTION_EXECUTED")
    provider = next(item for item in timeline if item["event_type"] == "PROVIDER_PAYMENT_EVENT_APPLIED")
    reassessment = next(item for item in timeline if item["event_type"] == "PROVIDER_INTELLIGENCE_REASSESSMENT")
    assert stored["historical"] is True
    assert stored["case_id"] == str(case.id) and stored["invoice_id"] == str(case.invoice.id)
    assert provider["customer_id"] == str(case.customer.id)
    assert provider["case_id"] == str(case.id) and provider["invoice_id"] == str(case.invoice.id)
    assert provider["request_reference"] == "demo_req_1"
    assert provider["event_reference"] == "demo_evt_1"
    assert provider["payment_reference"] == "demo_pay_1"
    assert provider["before"]["outstanding"] == "500" and provider["after"]["outstanding"] == "200"
    assert provider["provenance"] == "Provider Demo Mode"
    assert reassessment["category"] == "INTELLIGENCE_REASSESSMENT"
    assert reassessment["historical"] is True
    assert reassessment["before"]["recommendation"] == "ESCALATE"
    assert reassessment["after"]["recommendation"] == "FOLLOW_UP"


def test_duplicate_provider_audit_is_explicitly_non_financial() -> None:
    case, _, request, _ = _records()
    duplicate = AuditEvent(
        id=uuid4(), entity_type="ExternalPaymentRequest", entity_id=request.id,
        event_type="PROVIDER_DUPLICATE_EVENT_IGNORED", actor_type="provider_demo",
        payload={
            "source": "Provider Demo Mode", "original_event": "demo_evt_1",
            "provider_event_id": "demo_evt_1", "financial_mutation": "NONE",
            "outstanding_before": "200", "outstanding_after": "200",
        },
        occurred_at=datetime(2026, 8, 3, tzinfo=UTC),
    )
    timeline = build_case_evidence_timeline(FakeSession([duplicate]), case, [request], [])  # type: ignore[arg-type]
    entry = timeline[0]
    assert entry["category"] == "PROVIDER_EVENT"
    assert entry["title"] == "Duplicate provider event ignored"
    assert entry["detail"] == "Original event: demo_evt_1 · Financial mutation: none · Outstanding unchanged"
    assert entry["before"] == entry["after"] == {"outstanding": "200"}


def test_ai_interpretation_fact_and_reassessment_are_scoped_and_ordered() -> None:
    case, _, _, _ = _records()
    analysis_id = uuid4()
    other_case_id = uuid4()
    base = datetime(2026, 8, 4, 18, tzinfo=UTC)
    common = {"customer_id": str(case.customer.id), "case_id": str(case.id), "invoice_id": str(case.invoice.id), "candidate_fact": "ACTIVE_DISPUTE"}
    audits = [
        AuditEvent(id=uuid4(), entity_type="CommunicationAnalysis", entity_id=analysis_id, event_type="AI_CANDIDATE_EXTRACTED", payload=common, occurred_at=base),
        AuditEvent(id=uuid4(), entity_type="CommunicationAnalysis", entity_id=analysis_id, event_type="AI_CANDIDATE_ACCEPTED", payload=common, occurred_at=base.replace(microsecond=1)),
        AuditEvent(id=uuid4(), entity_type="Invoice", entity_id=case.invoice.id, event_type="DISPUTE_OPENED", payload=common, occurred_at=base.replace(microsecond=2)),
        AuditEvent(id=uuid4(), entity_type="RecoveryCase", entity_id=case.id, event_type="AI_FACT_INTELLIGENCE_REASSESSMENT", payload={**common, "score_before": 70, "score_after": 90, "recommendation_before": "PRIORITIZE_RECOVERY", "recommendation_after": "REVIEW_DISPUTE"}, occurred_at=base.replace(microsecond=3)),
        AuditEvent(id=uuid4(), entity_type="CommunicationAnalysis", entity_id=uuid4(), event_type="AI_CANDIDATE_ACCEPTED", payload={**common, "case_id": str(other_case_id)}, occurred_at=base.replace(microsecond=4)),
    ]
    timeline = build_case_evidence_timeline(FakeSession(audits), case, [], [])  # type: ignore[arg-type]
    ai_chain = [item for item in timeline if item["event_type"].startswith("AI_") or item["event_type"] == "DISPUTE_OPENED"]
    assert [item["event_type"] for item in ai_chain] == [
        "AI_CANDIDATE_EXTRACTED", "AI_CANDIDATE_ACCEPTED", "DISPUTE_OPENED", "AI_FACT_INTELLIGENCE_REASSESSMENT",
    ]
    assert ai_chain[0]["category"] == "AI_INTERPRETATION"
    assert ai_chain[-1]["category"] == "INTELLIGENCE_REASSESSMENT"
    assert all(item["case_id"] == str(case.id) and item["invoice_id"] == str(case.invoice.id) for item in ai_chain)
