"""Operator-controlled persistence of candidate facts extracted from communication."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.candidates import candidate_facts
from app.intelligence.operational_service import evaluate_customer_intelligence
from app.intelligence.schemas import (
    CandidateDecision,
    CandidateDecisionResponse,
    CandidateFactType,
    CommunicationAnalysisResult,
)
from app.models.domain import (
    AIProcessingStatus,
    AnalysisReviewStatus,
    AuditEvent,
    Communication,
    CommunicationAnalysis,
    Invoice,
    InvoiceStatus,
    PromiseStatus,
    PromiseToPay,
    RecoveryCase,
)
from app.recommendations.service import recommend_case
from app.recovery.engine import synchronize_recovery_states


def _operating_timestamp(operating_date, offset: int = 0) -> datetime:
    return datetime.combine(operating_date, time(18, 0), UTC) + timedelta(microseconds=offset)


def review_candidate_fact(
    db: Session,
    *,
    communication: Communication,
    analysis: CommunicationAnalysis,
    case: RecoveryCase,
    invoice: Invoice,
    candidate_id: str,
    decision: CandidateDecision,
    operator_id: str,
    operating_date,
) -> CandidateDecisionResponse:
    if communication.customer_id != case.customer_id or case.invoice_id != invoice.id or invoice.customer_id != communication.customer_id:
        raise HTTPException(status_code=409, detail="Communication, case, and invoice must belong to the same operational scope.")
    result = CommunicationAnalysisResult.model_validate(analysis.result)
    candidates = candidate_facts(communication.content, result)
    candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate fact was not found in this stored interpretation.")

    prior_audits = list(db.scalars(select(AuditEvent).where(
        AuditEvent.entity_type == "CommunicationAnalysis", AuditEvent.entity_id == analysis.id,
        AuditEvent.event_type.in_(["AI_CANDIDATE_ACCEPTED", "AI_CANDIDATE_REJECTED"]),
    )))
    for event in prior_audits:
        payload = event.payload or {}
        if payload.get("candidate_id") == candidate_id and payload.get("decision_result"):
            return CandidateDecisionResponse.model_validate(payload["decision_result"])

    before_intelligence = evaluate_customer_intelligence(case.customer, operating_date)
    before_recommendation = recommend_case(case, operating_date)
    outstanding_before = invoice.outstanding_amount
    persisted_fact: str | None = None
    fact_event_type: str | None = None
    fact_entity_type = "Invoice"
    fact_entity_id = invoice.id

    if decision is CandidateDecision.ACCEPT:
        if not candidate.persistence_eligible:
            raise HTTPException(status_code=422, detail=candidate.defer_reason or "This candidate cannot be persisted safely.")
        if candidate.fact_type is CandidateFactType.ACTIVE_DISPUTE:
            invoice.status = InvoiceStatus.DISPUTED
            persisted_fact, fact_event_type = "Active dispute opened", "DISPUTE_OPENED"
        elif candidate.fact_type is CandidateFactType.PAYMENT_PROMISE:
            amount = Decimal(str(candidate.proposed_data.get("amount") or "0"))
            promised_date_text = candidate.proposed_data.get("promised_date")
            if amount <= 0 or amount > invoice.outstanding_amount or not isinstance(promised_date_text, str):
                raise HTTPException(status_code=422, detail="Promise amount/date is incomplete or exceeds current outstanding.")
            promised_date = datetime.fromisoformat(promised_date_text).date()
            if promised_date < operating_date:
                raise HTTPException(status_code=422, detail="A new promise date cannot precede the operating date.")
            promise = PromiseToPay(
                customer=case.customer, invoice=invoice, promised_amount=amount, promised_date=promised_date,
                status=PromiseStatus.ACTIVE, source_communication=communication,
                confidence=Decimal(str(candidate.confidence)).quantize(Decimal("0.0001")),
            )
            db.add(promise)
            db.flush()
            persisted_fact, fact_event_type = "Payment promise created", "PROMISE_CREATED"
            fact_entity_type, fact_entity_id = "PromiseToPay", promise.id
        elif candidate.fact_type is CandidateFactType.BROKEN_PROMISE:
            promise = next((item for item in invoice.promises_to_pay if item.status is PromiseStatus.ACTIVE), None)
            if promise is None:
                raise HTTPException(status_code=422, detail="No active promise exists on this invoice to mark as broken.")
            promise.status = PromiseStatus.BROKEN
            promise.updated_at = _operating_timestamp(operating_date, 2)
            persisted_fact, fact_event_type = "Active payment promise marked broken", "PROMISE_BROKEN"
            fact_entity_type, fact_entity_id = "PromiseToPay", promise.id
        elif candidate.fact_type is CandidateFactType.CUSTOMER_DELAY_REASON:
            persisted_fact, fact_event_type = "Customer delay reason recorded", "CUSTOMER_DELAY_REASON_CONFIRMED"
            fact_entity_type, fact_entity_id = "Customer", case.customer.id
        elif candidate.fact_type is CandidateFactType.POSSIBLE_PAYMENT_CLAIM:
            persisted_fact, fact_event_type = "Unverified payment claim recorded for review", "PAYMENT_CLAIM_RECORDED"
            fact_entity_type, fact_entity_id = "Customer", case.customer.id
        else:
            raise HTTPException(status_code=422, detail="Unknown or deferred interpretations cannot create operational facts.")

    metadata = dict(communication.ai_processing_metadata or {})
    decision_key = "accepted_analysis_ids" if decision is CandidateDecision.ACCEPT else "rejected_analysis_ids"
    decisions = list(metadata.get(decision_key) or [])
    if str(analysis.id) not in decisions:
        decisions.append(str(analysis.id))
    metadata[decision_key] = decisions
    metadata["latest_operator_decision"] = decision.value
    communication.ai_processing_metadata = metadata
    communication.ai_processing_status = AIProcessingStatus.PROCESSED
    analysis.review_status = AnalysisReviewStatus.NOT_REQUIRED

    if decision is CandidateDecision.ACCEPT:
        synchronize_recovery_states(db, operating_date, commit=False)
    after_intelligence = evaluate_customer_intelligence(case.customer, operating_date)
    after_recommendation = recommend_case(case, operating_date)
    response = CandidateDecisionResponse(
        analysis_id=str(analysis.id), candidate=candidate, decision=decision, operator_id=operator_id,
        persisted_fact=persisted_fact,
        score_before=before_intelligence.score, score_after=after_intelligence.score,
        blockers_before=before_recommendation.blockers, blockers_after=after_recommendation.blockers,
        recommendation_before=before_recommendation.recommended_action.value,
        recommendation_after=after_recommendation.recommended_action.value,
    )
    common = {
        "source": "AI interpretation + operator confirmation", "analysis_id": str(analysis.id),
        "communication_id": str(communication.id), "candidate_id": candidate.candidate_id,
        "candidate_fact": candidate.fact_type.value, "confidence": candidate.confidence,
        "evidence_span": candidate.evidence_span, "provider": analysis.provider,
        "model_version": analysis.model_version, "customer_id": str(case.customer_id),
        "case_id": str(case.id), "invoice_id": str(invoice.id), "operator_id": operator_id,
        "financial_mutation": "NONE",
    }
    base = _operating_timestamp(operating_date)
    extraction_exists = any((event.payload or {}).get("candidate_id") == candidate_id for event in prior_audits)
    if not extraction_exists:
        db.add(AuditEvent(
            entity_type="CommunicationAnalysis", entity_id=analysis.id, event_type="AI_CANDIDATE_EXTRACTED",
            actor_type="ai_provider", actor_id=analysis.provider, payload=common, occurred_at=base,
        ))
    decision_event = "AI_CANDIDATE_ACCEPTED" if decision is CandidateDecision.ACCEPT else "AI_CANDIDATE_REJECTED"
    db.add(AuditEvent(
        entity_type="CommunicationAnalysis", entity_id=analysis.id, event_type=decision_event,
        actor_type="operator", actor_id=operator_id,
        payload={**common, "decision_result": response.model_dump(mode="json")}, occurred_at=base + timedelta(microseconds=1),
    ))
    if fact_event_type and persisted_fact:
        db.add(AuditEvent(
            entity_type=fact_entity_type, entity_id=fact_entity_id, event_type=fact_event_type,
            actor_type="operator", actor_id=operator_id,
            payload={**common, "reason": persisted_fact, "outstanding_before": str(outstanding_before), "outstanding_after": str(invoice.outstanding_amount)},
            occurred_at=base + timedelta(microseconds=2),
        ))
        db.add(AuditEvent(
            entity_type="RecoveryCase", entity_id=case.id, event_type="AI_FACT_INTELLIGENCE_REASSESSMENT",
            actor_type="system", payload={
                **common, "what_changed": f"Accepted {candidate.fact_type.value} was persisted and deterministic policy was recalculated.",
                "score_before": before_intelligence.score, "score_after": after_intelligence.score,
                "recommendation_before": before_recommendation.recommended_action.value,
                "recommendation_after": after_recommendation.recommended_action.value,
                "blockers_before": before_recommendation.blockers, "blockers_after": after_recommendation.blockers,
            }, occurred_at=base + timedelta(microseconds=3),
        ))
    db.commit()
    return response
