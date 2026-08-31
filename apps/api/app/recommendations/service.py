"""Deterministic, read-only recovery recommendations.

Communication analyses can supply context but never establish payments, promises,
disputes, or recovery-state transitions.  The recovery evaluator remains the
authority for every factual condition and blocker used here.
"""

from __future__ import annotations

from datetime import date

from app.intelligence.schemas import CommunicationAnalysisResult, Intent
from app.models.domain import CommunicationAnalysis, RecoveryCase
from app.recommendations.schemas import (
    ActionReadiness,
    CommunicationSignal,
    RecommendationPriority,
    RecommendedAction,
    RecoveryRecommendation,
)
from app.recovery.engine import CaseEvaluation, evaluate_case

SEVERE_EXPOSURE = 250_000
SEVERE_OVERDUE_DAYS = 90
RECENT_SIGNAL_DAYS = 14
OUTREACH_ACTIONS = {RecommendedAction.SEND_PAYMENT_REMINDER, RecommendedAction.REQUEST_PAYMENT_DATE}


def _signals(case: RecoveryCase, simulation_date: date) -> list[CommunicationSignal]:
    """Return valid, recent-or-historical stored interpretation summaries only."""
    signals: list[CommunicationSignal] = []
    for communication in case.customer.communications:
        accepted = set((communication.ai_processing_metadata or {}).get("accepted_analysis_ids") or [])
        if communication.direction.value != "INBOUND":
            continue
        for analysis in communication.analyses:
            if str(analysis.id) not in accepted:
                continue
            try:
                result = CommunicationAnalysisResult.model_validate(analysis.result)
            except Exception:
                # A malformed historical interpretation is not a factual signal.
                continue
            signals.append(CommunicationSignal(
                analysis_id=str(analysis.id), communication_id=str(communication.id),
                intent=result.intent.value, occurred_at=communication.occurred_at.isoformat(),
                confidence=analysis.confidence,
                payment_completed_claim=result.payment_completed_claim.detected,
                dispute_detected=result.dispute_signal.detected,
                has_payment_commitment=bool(result.payment_commitments),
                requires_human_review=result.requires_human_review,
            ))
    return sorted(signals, key=lambda item: item.occurred_at, reverse=True)


def _has_recent_commitment_or_delay(signals: list[CommunicationSignal], simulation_date: date) -> bool:
    for signal in signals:
        occurred = date.fromisoformat(signal.occurred_at[:10])
        if (simulation_date - occurred).days <= RECENT_SIGNAL_DAYS and (
            signal.has_payment_commitment or signal.intent == Intent.PAYMENT_DELAY.value
        ):
            return True
    return False


def _priority_for_escalation(case: RecoveryCase, evaluation: CaseEvaluation) -> RecommendationPriority:
    invoice = evaluation.invoice
    if case.priority.value == "CRITICAL" or (invoice and invoice.outstanding_amount >= SEVERE_EXPOSURE):
        return RecommendationPriority.CRITICAL
    return RecommendationPriority.HIGH


def _operator_next_step(action: RecommendedAction) -> str:
    return {
        RecommendedAction.SEND_PAYMENT_REMINDER: "Review the case evidence and create the reminder workflow only if operator-approved outreach is appropriate.",
        RecommendedAction.MONITOR_ACTIVE_PROMISE: "Monitor the recorded promise through its due date and verify payment evidence before taking further recovery action.",
        RecommendedAction.REQUEST_PAYMENT_DATE: "Review the account and create a controlled follow-up requesting a confirmed payment date.",
        RecommendedAction.REVIEW_PAYMENT_CLAIM: "Verify the payment claim against recorded payment evidence before changing the recovery response.",
        RecommendedAction.HOLD_FOR_DISPUTE: "Keep recovery work on hold while an operator reviews the active dispute and its resolution evidence.",
        RecommendedAction.ESCALATE_TO_HUMAN: "Route the case for human recovery review before any further action is approved.",
        RecommendedAction.PREPARE_ESCALATION: "Create an internal escalation workflow for senior recovery review.",
        RecommendedAction.NO_ACTION_REQUIRED: "Continue monitoring the live case facts; no recovery workflow needs to be created now.",
    }[action]


def _workflow_effect(action: RecommendedAction) -> str:
    if action is RecommendedAction.NO_ACTION_REQUIRED:
        return "This remains an advisory decision. No workflow record is created and no operational fact is changed."
    return "Proceeding creates an internal controlled recovery workflow record for operator review. It does not contact the customer or change invoices, payments, promises, disputes, or case state."


def recommend_case(case: RecoveryCase, simulation_date: date) -> RecoveryRecommendation:
    """Compute one advisory recommendation without mutating any domain record."""
    evaluation = evaluate_case(case, simulation_date)
    invoice = evaluation.invoice
    exposure = invoice.outstanding_amount if invoice else 0
    days_overdue = invoice.days_overdue if invoice else 0
    signals = _signals(case, simulation_date)
    factual_reasons: list[str] = []
    blockers = list(evaluation.eligibility.blocking_reasons)
    action: RecommendedAction
    priority: RecommendationPriority
    # Keep the API contract total even for unflushed ORM objects whose column
    # defaults have not yet been materialized in Python.
    approval_required = False
    explanation: str

    # Ordered facts take precedence over all interpretation signals.
    if evaluation.derived_state in {"CLOSED", "RESOLVED"} or (invoice and invoice.state == "PAID"):
        action, priority, approval_required = RecommendedAction.NO_ACTION_REQUIRED, RecommendationPriority.LOW, False
        factual_reasons.append("Case is closed, resolved, or invoice is fully paid.")
        explanation = "No recovery action is required because the case has no outstanding recoverable balance."
    elif evaluation.active_dispute:
        action, priority, approval_required = RecommendedAction.HOLD_FOR_DISPUTE, RecommendationPriority.HIGH, True
        factual_reasons.append("An active invoice dispute factually blocks recovery automation.")
        explanation = "Keep recovery on hold until the recorded dispute is resolved; communication analysis cannot remove this blocker."
    elif any(signal.payment_completed_claim for signal in signals):
        action, priority, approval_required = RecommendedAction.REVIEW_PAYMENT_CLAIM, RecommendationPriority.HIGH, True
        factual_reasons.append("Invoice remains outstanding; no matching payment fact has been recorded.")
        explanation = "Verify the customer's payment-completed claim against payment evidence before changing any invoice or case state."
    elif any(promise.state == "ACTIVE" for promise in evaluation.promises):
        action, priority, approval_required = RecommendedAction.MONITOR_ACTIVE_PROMISE, RecommendationPriority.MEDIUM, bool(case.customer.is_strategic_account)
        factual_reasons.append("A recorded payment promise is active and has not reached its promised date.")
        explanation = "Monitor the recorded promise deadline and payment evidence; do not create or alter a promise from communication interpretation."
    elif any(promise.state == "BROKEN" for promise in evaluation.promises):
        priority = _priority_for_escalation(case, evaluation)
        significant = priority is RecommendationPriority.CRITICAL or days_overdue >= SEVERE_OVERDUE_DAYS
        action = RecommendedAction.ESCALATE_TO_HUMAN if significant else RecommendedAction.PREPARE_ESCALATION
        approval_required = True
        factual_reasons.append("A recorded payment promise is broken.")
        factual_reasons.append(f"Outstanding exposure is {exposure} and the invoice is {days_overdue} days overdue.")
        explanation = "A factual promise was missed; prepare escalation materials or obtain human escalation approval based on the deterministic severity threshold."
    elif invoice and invoice.state == "OVERDUE" and (case.priority.value == "CRITICAL" or exposure >= SEVERE_EXPOSURE or days_overdue >= SEVERE_OVERDUE_DAYS) and not _has_recent_commitment_or_delay(signals, simulation_date):
        action, priority, approval_required = RecommendedAction.PREPARE_ESCALATION, _priority_for_escalation(case, evaluation), True
        factual_reasons.append(f"Severe overdue exposure: {exposure} outstanding for {days_overdue} days.")
        explanation = "Prepare the case for human escalation because overdue severity exceeds the portfolio threshold and there is no recent commitment or delay signal."
    elif invoice and invoice.state == "OVERDUE" and _has_recent_commitment_or_delay(signals, simulation_date):
        action, priority, approval_required = RecommendedAction.REQUEST_PAYMENT_DATE, RecommendationPriority.MEDIUM, False
        factual_reasons.append("Invoice is overdue and has no recorded active payment promise.")
        explanation = "Request a confirmed payment date. A recent communication signal provides context only and has not created a factual promise."
    elif invoice and invoice.state == "OVERDUE":
        action, priority, approval_required = RecommendedAction.SEND_PAYMENT_REMINDER, RecommendationPriority.MEDIUM, False
        factual_reasons.append("Invoice is overdue with no active promise, dispute, or payment claim requiring review.")
        explanation = "Send an operator-approved payment reminder; this recommendation does not send communication automatically."
    else:
        action, priority, approval_required = RecommendedAction.NO_ACTION_REQUIRED, RecommendationPriority.LOW, False
        factual_reasons.append("No overdue factual condition currently requires recovery action.")
        explanation = "No action is required from the current factual recovery evaluation."

    communication = evaluation.communication_eligibility
    communication_required = action in OUTREACH_ACTIONS
    if communication_required and not communication.permitted:
        blockers.extend(communication.blocking_reasons)
        if "COMMUNICATION_OPTED_OUT" in communication.blocking_reasons:
            operator_next_step = "Do not contact this customer; recorded communication consent is opted out."
        else:
            approval_required = True
            operator_next_step = "Resolve communication consent and channel eligibility through human review before outreach."
        workflow_effect = "No outreach workflow or external request can execute until communication eligibility is permitted."
    else:
        operator_next_step = _operator_next_step(action)
        workflow_effect = _workflow_effect(action)
    blockers = list(dict.fromkeys(blockers))
    financially_actionable = action is not RecommendedAction.NO_ACTION_REQUIRED and evaluation.derived_state not in {"CLOSED", "RESOLVED"}
    no_active_blocker = not evaluation.eligibility.blocking_reasons and (
        not communication_required or communication.permitted
    )
    if not financially_actionable:
        external_execution = "UNAVAILABLE"
    elif communication_required and not communication.permitted:
        external_execution = "BLOCKED"
    elif communication_required:
        external_execution = "OPERATOR_CONTROLLED"
    else:
        external_execution = "INTERNAL_WORKFLOW_ONLY"
    readiness_reasons = list(dict.fromkeys([
        *evaluation.eligibility.blocking_reasons,
        *(communication.blocking_reasons if communication_required else []),
    ]))
    if not readiness_reasons:
        readiness_reasons.append("CURRENT_FACTS_AND_COMMUNICATION_ELIGIBILITY_VERIFIED")
    readiness = ActionReadiness(
        financially_actionable=financially_actionable,
        no_active_blocker=no_active_blocker,
        communication_required=communication_required,
        communication_permitted=communication.permitted,
        consent_status=communication.consent_status,
        channel=communication.channel,
        channel_available=communication.channel_available,
        current_decision_valid=True,
        operator_approval="REQUIRED" if approval_required else "NOT_REQUIRED",
        external_execution=external_execution,
        reasons=readiness_reasons,
    )
    return RecoveryRecommendation(
        case_id=str(case.id), customer_id=str(case.customer_id), customer_name=case.customer.name,
        recommended_action=action, priority=priority, human_approval_required=approval_required,
        factual_reasons=factual_reasons, communication_signals=signals, blockers=blockers,
        relevant_exposure=exposure, relevant_days_overdue=days_overdue,
        recovery_state=evaluation.derived_state, operator_explanation=explanation,
        operator_next_step=operator_next_step, workflow_effect=workflow_effect,
        action_readiness=readiness,
    )


_PRIORITY_ORDER = {
    RecommendationPriority.CRITICAL: 0, RecommendationPriority.HIGH: 1,
    RecommendationPriority.MEDIUM: 2, RecommendationPriority.LOW: 3,
}


def prioritized_recommendations(cases: list[RecoveryCase], simulation_date: date) -> list[RecoveryRecommendation]:
    return sorted(
        (recommend_case(case, simulation_date) for case in cases),
        key=lambda item: (_PRIORITY_ORDER[item.priority], -item.relevant_days_overdue, -item.relevant_exposure, item.case_id),
    )
