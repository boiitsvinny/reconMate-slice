"""Case-scoped projection of existing audit, simulation, workflow, and provider facts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.domain import (
    AuditEvent,
    ExternalPaymentRequest,
    ProviderEvent,
    RecoveryCase,
    SimulationEvent,
)


FACT_TITLES = {
    "SYNTHETIC_PORTFOLIO_SEEDED": "Portfolio facts seeded",
    "RECEIVABLE_IMPORTED": "Invoice imported",
    "INVOICE_OVERDUE_DETECTED": "Invoice became overdue",
    "PROMISE_CREATED": "Promise created",
    "PROMISE_BROKEN": "Promise broken",
    "PROMISE_BROKEN_DETECTED": "Broken promise detected",
    "DISPUTE_OPENED": "Dispute opened",
    "DISPUTE_RESOLVED": "Dispute resolved",
    "PARTIAL_PAYMENT": "Partial payment persisted",
    "FULL_PAYMENT": "Payment persisted",
    "RECOVERY_CASE_STATE_CHANGED": "Recovery case state changed",
}


def _source(event_type: str, payload: dict[str, Any], actor_type: str | None = None) -> str:
    explicit = payload.get("source")
    if explicit:
        return str(explicit)
    if event_type == "RECEIVABLE_IMPORTED":
        return "CSV Import"
    if event_type.startswith("PROVIDER_") or actor_type == "provider_demo":
        return "Provider Demo Mode"
    if event_type.startswith("SIMULATION_") or event_type == "SYNTHETIC_PORTFOLIO_SEEDED":
        return "Synthetic Demo Sandbox"
    return "ReconMate persisted audit"


def _category(event_type: str) -> str:
    if "INTELLIGENCE_REASSESSMENT" in event_type or event_type.startswith("SIMULATION_INTELLIGENCE"):
        return "INTELLIGENCE_REASSESSMENT"
    if event_type.startswith("RECOVERY_ACTION") or event_type == "EXTERNAL_PAYMENT_REQUEST_CREATED":
        return "OPERATOR_ACTION"
    if event_type.startswith("PROVIDER_"):
        return "PROVIDER_EVENT"
    return "FACT_EVENT"


def _title(event_type: str) -> str:
    if "INTELLIGENCE_REASSESSMENT" in event_type or event_type.startswith("SIMULATION_INTELLIGENCE"):
        return "Intelligence recalculated"
    if event_type == "EXTERNAL_PAYMENT_REQUEST_CREATED":
        return "Payment request created"
    if event_type == "PROVIDER_PAYMENT_EVENT_APPLIED":
        return "Provider payment event applied"
    if event_type == "PROVIDER_DUPLICATE_EVENT_IGNORED":
        return "Duplicate provider event ignored"
    if event_type.startswith("RECOVERY_ACTION_"):
        return event_type.removeprefix("RECOVERY_ACTION_").replace("_", " ").title()
    return FACT_TITLES.get(event_type, event_type.replace("_", " ").title())


def _changes(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in ("outstanding", "score", "recommendation", "risk_level", "state"):
        before_value = payload.get(f"{field}_before", payload.get(f"previous_{field}"))
        after_value = payload.get(f"{field}_after", payload.get(f"current_{field}"))
        if before_value is not None or after_value is not None:
            before[field] = before_value
            after[field] = after_value
    if "from" in payload or "to" in payload:
        before["state"] = payload.get("from")
        after["state"] = payload.get("to")
    return (before or None, after or None)


def _entry(
    *, event_id: Any, occurred_at: Any, event_type: str, payload: dict[str, Any],
    customer_id: Any = None, case_id: Any = None, invoice_id: Any = None,
    actor_type: str | None = None,
) -> dict[str, Any]:
    before, after = _changes(payload)
    historical = event_type.startswith("RECOVERY_ACTION_") or "INTELLIGENCE" in event_type
    detail = payload.get("what_changed") or payload.get("reason") or payload.get("financial_mutation")
    if event_type == "PROVIDER_DUPLICATE_EVENT_IGNORED":
        detail = (
            f"Original event: {payload.get('original_event', 'unavailable')} · "
            "Financial mutation: none · Outstanding unchanged"
        )
    return {
        "id": str(event_id), "occurred_at": occurred_at, "category": _category(event_type),
        "event_type": event_type, "title": _title(event_type),
        "customer_id": str(customer_id or payload.get("customer_id")) if customer_id or payload.get("customer_id") else None,
        "case_id": str(case_id or payload.get("case_id")) if case_id or payload.get("case_id") else None,
        "invoice_id": str(invoice_id or payload.get("invoice_id")) if invoice_id or payload.get("invoice_id") else None,
        "request_reference": payload.get("provider_reference"),
        "event_reference": payload.get("provider_event_id") or payload.get("replayed_event"),
        "payment_reference": payload.get("provider_payment_reference"),
        "before": before, "after": after, "provenance": _source(event_type, payload, actor_type),
        "historical": historical,
        "detail": detail,
    }


def build_case_evidence_timeline(
    db: Session,
    case: RecoveryCase,
    payment_requests: list[ExternalPaymentRequest],
    provider_events: list[ProviderEvent],
) -> list[dict[str, Any]]:
    """Return only evidence explicitly linked to this case, customer, invoice, or child record."""
    invoice_id = case.invoice_id or (case.invoice.id if case.invoice is not None else None)
    customer_id = case.customer_id or case.customer.id
    promise_ids = [item.id for item in case.invoice.promises_to_pay] if case.invoice is not None else []
    action_ids = [item.id for item in case.actions]
    request_ids = [item.id for item in payment_requests]
    payment_ids = [item.payment_id for item in provider_events]

    audit_scope = [
        and_(AuditEvent.entity_type == "RecoveryCase", AuditEvent.entity_id == case.id),
        and_(AuditEvent.entity_type == "Customer", AuditEvent.entity_id == customer_id),
    ]
    if invoice_id:
        audit_scope.append(and_(AuditEvent.entity_type == "Invoice", AuditEvent.entity_id == invoice_id))
    if promise_ids:
        audit_scope.append(and_(AuditEvent.entity_type == "PromiseToPay", AuditEvent.entity_id.in_(promise_ids)))
    if action_ids:
        audit_scope.append(and_(AuditEvent.entity_type == "RecoveryAction", AuditEvent.entity_id.in_(action_ids)))
    if request_ids:
        audit_scope.append(and_(AuditEvent.entity_type == "ExternalPaymentRequest", AuditEvent.entity_id.in_(request_ids)))
    if payment_ids:
        audit_scope.append(and_(AuditEvent.entity_type == "Payment", AuditEvent.entity_id.in_(payment_ids)))

    audits = list(db.scalars(select(AuditEvent).where(or_(*audit_scope)).order_by(AuditEvent.occurred_at)))
    entries: list[dict[str, Any]] = []
    for event in audits:
        payload = dict(event.payload or {})
        for key, expected in (("customer_id", customer_id), ("case_id", case.id), ("invoice_id", invoice_id)):
            if payload.get(key) is not None and (expected is None or str(payload[key]) != str(expected)):
                payload.pop(key)
        # ProviderEvent is the canonical payment event; avoid presenting its audit mirror twice.
        if event.event_type == "PROVIDER_PAYMENT_EVENT_APPLIED":
            continue
        linked_to_case = event.entity_type in {"RecoveryCase", "RecoveryAction", "PromiseToPay", "ExternalPaymentRequest", "Payment"}
        linked_to_invoice = event.entity_type in {"Invoice", "PromiseToPay", "RecoveryCase", "RecoveryAction", "ExternalPaymentRequest", "Payment"}
        entries.append(_entry(
            event_id=event.id, occurred_at=event.occurred_at, event_type=event.event_type,
            payload=payload, customer_id=customer_id,
            case_id=case.id if linked_to_case else None,
            invoice_id=invoice_id if linked_to_invoice else None,
            actor_type=event.actor_type,
        ))

    simulation_scope = [SimulationEvent.recovery_case_id == case.id]
    if invoice_id:
        simulation_scope.append(SimulationEvent.invoice_id == invoice_id)
    simulation_events = list(db.scalars(
        select(SimulationEvent).where(or_(*simulation_scope)).order_by(SimulationEvent.occurred_at)
    ))
    for event in simulation_events:
        entries.append(_entry(
            event_id=event.id, occurred_at=event.occurred_at, event_type=event.event_type,
            payload={**(event.metadata_ or {}), "source": "Synthetic Demo Sandbox"}, customer_id=event.customer_id,
            case_id=event.recovery_case_id, invoice_id=event.invoice_id,
        ))

    request_by_id = {item.id: item for item in payment_requests}
    for event in provider_events:
        request = request_by_id.get(event.payment_request_id)
        evidence = event.evidence or {}
        entries.append(_entry(
            event_id=event.id, occurred_at=event.received_at, event_type="PROVIDER_PAYMENT_EVENT_APPLIED",
            payload={
                **evidence, "provider_event_id": event.provider_event_id,
                "provider_payment_reference": event.provider_payment_reference,
                "provider_reference": request.provider_reference if request else evidence.get("provider_reference"),
            },
            customer_id=customer_id, case_id=case.id, invoice_id=invoice_id,
            actor_type="provider_demo" if request and request.provider_mode == "DEMO" else "provider",
        ))
        if any(evidence.get(key) is not None for key in ("score_before", "score_after", "recommendation_before", "recommendation_after")):
            entries.append(_entry(
                event_id=f"{event.id}:reassessment", occurred_at=event.received_at,
                event_type="PROVIDER_INTELLIGENCE_REASSESSMENT",
                payload={**evidence, "source": evidence.get("source") or ("Provider Demo Mode" if request and request.provider_mode == "DEMO" else "Provider evidence")},
                customer_id=customer_id, case_id=case.id, invoice_id=invoice_id,
            ))

    entries.sort(key=lambda item: (item["occurred_at"], item["id"]))
    return entries
