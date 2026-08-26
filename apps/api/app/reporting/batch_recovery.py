"""Authoritative batch recovery proof assembled without mutating portfolio state."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID

from app.models.domain import (
    AuditEvent,
    ExternalPaymentRequest,
    Invoice,
    InvoiceStatus,
    ProviderEvent,
    RecoveryAction,
    RecoveryActionStatus,
    RecoveryCase,
    RecoveryState,
)
from app.recommendations.service import recommend_case
from app.recovery.engine import evaluate_case


EXCLUDED_INVOICE_STATUSES = {InvoiceStatus.CANCELLED, InvoiceStatus.WRITTEN_OFF}
TERMINAL_CASE_STATES = {RecoveryState.RESOLVED, RecoveryState.CLOSED}
BLOCKED_ACTION_STATUSES = {
    RecoveryActionStatus.HELD,
    RecoveryActionStatus.REJECTED,
    RecoveryActionStatus.CANCELLED,
    RecoveryActionStatus.FAILED,
}


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _source(imported: bool) -> str:
    return "CSV Import" if imported else "Synthetic Demo Sandbox"


def _invoice_customer_id(invoice: Invoice) -> UUID:
    return invoice.customer_id or invoice.customer.id


def _case_invoice_id(case: RecoveryCase) -> UUID | None:
    return case.invoice_id or (case.invoice.id if case.invoice else None)


def _case_customer_id(case: RecoveryCase) -> UUID:
    return case.customer_id or case.customer.id


def build_batch_recovery_proof(
    *,
    simulation_date: date,
    cycle: int,
    invoices: Iterable[Invoice],
    cases: Iterable[RecoveryCase],
    actions: Iterable[RecoveryAction],
    payment_requests: Iterable[ExternalPaymentRequest],
    provider_events: Iterable[ProviderEvent],
    imported_invoice_ids: set[UUID],
    duplicate_provider_audits: Iterable[AuditEvent] = (),
) -> dict[str, Any]:
    """Reconcile a current overdue batch from persisted invoices and payments.

    The starting exposure is reconstructed as current overdue outstanding plus
    payments observed after each invoice became overdue. Payments on/before the
    due date are intentionally outside this recovery measure.
    """
    scoped_invoices = [
        invoice for invoice in invoices
        if invoice.issue_date <= simulation_date
        and invoice.due_date < simulation_date
        and invoice.status not in EXCLUDED_INVOICE_STATUSES
        and (
            invoice.outstanding_amount > 0
            or any(invoice.due_date < payment.payment_date <= simulation_date for payment in invoice.payments)
        )
    ]
    invoice_ids = {invoice.id for invoice in scoped_invoices}
    cases_by_invoice: dict[UUID, list[RecoveryCase]] = defaultdict(list)
    scoped_cases = [case for case in cases if _case_invoice_id(case) in invoice_ids]
    for case in scoped_cases:
        case_invoice_id = _case_invoice_id(case)
        if case_invoice_id is not None:
            cases_by_invoice[case_invoice_id].append(case)
    case_ids = {case.id for case in scoped_cases}
    scoped_actions = [action for action in actions if action.recovery_case_id in case_ids]
    scoped_requests = [request for request in payment_requests if request.invoice_id in invoice_ids]
    request_by_id = {request.id: request for request in scoped_requests}
    scoped_provider_events = [event for event in provider_events if event.payment_request_id in request_by_id]
    provider_event_by_payment = {event.payment_id: event for event in scoped_provider_events}

    starting_exposure = Decimal("0")
    recovered_amount = Decimal("0")
    remaining_overdue = Decimal("0")
    recovered_invoice_count = 0
    partially_recovered_invoice_count = 0
    qualifying_payment_count = 0
    payment_evidence: list[dict[str, Any]] = []
    recovered_by_customer: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    remaining_by_customer: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))

    for invoice in scoped_invoices:
        qualifying = sorted(
            (
                payment for payment in invoice.payments
                if invoice.due_date < payment.payment_date <= simulation_date
            ),
            key=lambda payment: (payment.payment_date, str(payment.id)),
        )
        invoice_recovered = sum((payment.amount for payment in qualifying), Decimal("0"))
        current = invoice.outstanding_amount
        starting_exposure += current + invoice_recovered
        recovered_amount += invoice_recovered
        remaining_overdue += current
        customer_id = _invoice_customer_id(invoice)
        recovered_by_customer[customer_id] += invoice_recovered
        remaining_by_customer[customer_id] += current
        if invoice_recovered > 0 and current == 0:
            recovered_invoice_count += 1
        elif invoice_recovered > 0 and current > 0:
            partially_recovered_invoice_count += 1
        for payment in qualifying:
            qualifying_payment_count += 1
            event = provider_event_by_payment.get(payment.id)
            request = request_by_id.get(event.payment_request_id) if event else None
            evidence = event.evidence if event else {}
            related_case = cases_by_invoice.get(invoice.id, [None])[0]
            payment_evidence.append({
                "payment_id": str(payment.id),
                "payment_reference": payment.reference,
                "payment_date": payment.payment_date,
                "amount": _money(payment.amount),
                "customer_id": str(customer_id),
                "case_id": str(related_case.id) if related_case else None,
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "provenance": evidence.get("source") or _source(invoice.id in imported_invoice_ids),
                "provider_mode": request.provider_mode if request else None,
                "request_reference": request.provider_reference if request else None,
                "event_reference": event.provider_event_id if event else None,
                "provider_payment_reference": event.provider_payment_reference if event else None,
                "outstanding_before": evidence.get("outstanding_before"),
                "outstanding_after": evidence.get("outstanding_after"),
            })

    fully_recovered_accounts = sum(
        amount > 0 and remaining_by_customer[customer_id] == 0
        for customer_id, amount in recovered_by_customer.items()
    )
    partially_recovered_accounts = sum(
        amount > 0 and remaining_by_customer[customer_id] > 0
        for customer_id, amount in recovered_by_customer.items()
    )

    action_counts = Counter(action.status.value for action in scoped_actions)
    active_case_evidence: list[tuple[RecoveryCase, Any, str, bool]] = []
    for case in scoped_cases:
        evaluation = evaluate_case(case, simulation_date)
        current_recommendation = recommend_case(case, simulation_date)
        recommendation = current_recommendation.recommended_action.value
        approval_required = current_recommendation.human_approval_required
        active_case_evidence.append((case, evaluation, recommendation, approval_required))

    hold_rows: list[dict[str, Any]] = []
    for case, evaluation, recommendation, _ in active_case_evidence:
        if evaluation.derived_state in {state.value for state in TERMINAL_CASE_STATES}:
            continue
        reasons = list(evaluation.eligibility.blocking_reasons)
        if not reasons:
            continue
        hold_rows.append({
            "case_id": str(case.id),
            "customer_id": str(_case_customer_id(case)),
            "invoice_id": str(_case_invoice_id(case)) if _case_invoice_id(case) else None,
            "customer_name": case.customer.name,
            "invoice_number": case.invoice.invoice_number if case.invoice else None,
            "reasons": reasons,
            "current_recommendation": recommendation,
            "provenance": _source(bool(_case_invoice_id(case) in imported_invoice_ids)),
        })

    terminal_states = {state.value for state in TERMINAL_CASE_STATES}
    active_dispute_holds = sum(
        evaluation.derived_state not in terminal_states and evaluation.active_dispute
        for _, evaluation, _, _ in active_case_evidence
    )
    active_promise_holds = sum(
        evaluation.derived_state not in terminal_states
        and any(promise.state == "ACTIVE" for promise in evaluation.promises)
        for _, evaluation, _, _ in active_case_evidence
    )
    resolved_or_paid = sum(
        evaluation.derived_state in terminal_states
        for _, evaluation, _, _ in active_case_evidence
    )
    approval_required = sum(
        evaluation.derived_state not in terminal_states
        and recommendation_approval_required
        for _, evaluation, _, recommendation_approval_required in active_case_evidence
    )
    deliberate_hold_ids = {row["case_id"] for row in hold_rows}
    unresolved_exception_ids = {
        str(case.id) for case, evaluation, _, _ in active_case_evidence
        if evaluation.derived_state not in terminal_states
        and (
            case.priority.value in {"HIGH", "CRITICAL"}
            or evaluation.active_dispute
            or any(promise.state == "BROKEN" for promise in evaluation.promises)
        )
    }
    pending_case_ids = {
        str(action.recovery_case_id) for action in scoped_actions
        if action.status is RecoveryActionStatus.PENDING_APPROVAL
    }
    unresolved_exception_ids.update(pending_case_ids)
    elevated_case_ids = {
        str(case.id) for case, evaluation, _, _ in active_case_evidence
        if evaluation.derived_state not in terminal_states and case.priority.value in {"HIGH", "CRITICAL"}
    }
    broken_promise_case_ids = {
        str(case.id) for case, evaluation, _, _ in active_case_evidence
        if evaluation.derived_state not in terminal_states and any(promise.state == "BROKEN" for promise in evaluation.promises)
    }
    dispute_case_ids = {
        str(case.id) for case, evaluation, _, _ in active_case_evidence
        if evaluation.derived_state not in terminal_states and evaluation.active_dispute
    }
    exception_memberships = len(elevated_case_ids) + len(broken_promise_case_ids) + len(dispute_case_ids) + len(pending_case_ids)
    other_blocked_case_count = sum(
        not {"ACTIVE_DISPUTE", "ACTIVE_PAYMENT_PROMISE"}.intersection(row["reasons"])
        for row in hold_rows
    )

    age_only_targets = [
        (case, evaluation) for case, evaluation, _, _ in active_case_evidence
        if evaluation.invoice is not None and evaluation.invoice.state == "OVERDUE"
        and evaluation.derived_state not in terminal_states
    ]
    blocker_violations_avoided = sum(
        bool({"ACTIVE_DISPUTE", "ACTIVE_PAYMENT_PROMISE"}.intersection(evaluation.eligibility.blocking_reasons))
        for _, evaluation in age_only_targets
    )
    immediate_action_cases = sum(
        evaluation.eligibility.allowed and recommendation != "NO_ACTION_REQUIRED"
        and evaluation.derived_state not in {state.value for state in TERMINAL_CASE_STATES}
        for _, evaluation, recommendation, _ in active_case_evidence
    )

    imported_count = sum(invoice.id in imported_invoice_ids for invoice in scoped_invoices)
    if imported_count == len(scoped_invoices) and scoped_invoices:
        provenance = "CSV Import"
    elif imported_count:
        provenance = "Mixed: CSV Import + Synthetic Demo Sandbox"
    else:
        provenance = "Synthetic Demo Sandbox"

    recovery_rate = Decimal("0") if starting_exposure == 0 else (
        recovered_amount / starting_exposure * Decimal("100")
    ).quantize(Decimal("0.01"))
    duplicate_count = sum(event.entity_id in request_by_id for event in duplicate_provider_audits)
    payment_evidence.sort(key=lambda item: (item["payment_date"], item["payment_id"]), reverse=True)
    provenance_counts: dict[str, dict[str, Any]] = {}
    for row in payment_evidence:
        category = row["provenance"]
        current = provenance_counts.setdefault(category, {"payment_count": 0, "amount": Decimal("0")})
        current["payment_count"] += 1
        current["amount"] += Decimal(row["amount"])

    return {
        "scope": {
            "as_of_date": simulation_date,
            "cycle": cycle,
            "customer_count": len({_invoice_customer_id(invoice) for invoice in scoped_invoices}),
            "invoice_count": len(scoped_invoices),
            "case_count": len(scoped_cases),
            "earliest_due_date": min((invoice.due_date for invoice in scoped_invoices), default=None),
            "provenance": provenance,
            "definition": "Current overdue invoices plus invoices with a persisted post-due payment; cancelled, written-off, and never-overdue paid invoices excluded.",
        },
        "reconciliation": {
            "starting_overdue_exposure": _money(starting_exposure),
            "observed_recovery": _money(recovered_amount),
            "remaining_overdue_exposure": _money(remaining_overdue),
            "recovery_rate": str(recovery_rate),
            "equation_holds": starting_exposure == recovered_amount + remaining_overdue,
            "qualifying_payment_count": qualifying_payment_count,
            "recovered_invoice_count": recovered_invoice_count,
            "partially_recovered_invoice_count": partially_recovered_invoice_count,
            "remaining_open_overdue_invoice_count": sum(invoice.outstanding_amount > 0 for invoice in scoped_invoices),
            "fully_recovered_account_count": fully_recovered_accounts,
            "partially_recovered_account_count": partially_recovered_accounts,
            "measurement_note": "Observed recovery sums persisted payments recorded after each scoped invoice became overdue. It does not claim ReconMate caused payment.",
        },
        "metric_metadata": {
            "starting_overdue_exposure": {"unit": "INR", "scope": "overdue cohort", "window": "invoice due date through operating date"},
            "observed_recovery": {"unit": "INR", "scope": "overdue cohort persisted payments", "window": "post-due through operating date"},
            "remaining_overdue_exposure": {"unit": "INR", "scope": "current overdue invoices", "window": "operating date"},
            "recovery_rate": {"unit": "percent", "scope": "overdue cohort", "window": "observed window"},
            "accounts": {"unit": "customers", "scope": "overdue cohort", "window": "observed window"},
            "invoices": {"unit": "invoices", "scope": "overdue cohort", "window": "observed window"},
            "stopping_rules": {"unit": "cases", "scope": "current open recovery cases", "window": "operating date"},
            "workflow_outcomes": {"unit": "workflows", "scope": "overdue-cohort cases", "window": "persisted history"},
            "payments": {"unit": "payments", "scope": "qualifying overdue-cohort payments", "window": "observed window"},
        },
        "stopping_rules": {
            "deliberate_hold_count": len(deliberate_hold_ids),
            "active_dispute_hold_count": active_dispute_holds,
            "active_promise_hold_count": active_promise_holds,
            "resolved_or_paid_case_count": resolved_or_paid,
            "other_blocked_case_count": other_blocked_case_count,
            "blocked_action_count": sum(action_counts[status.value] for status in BLOCKED_ACTION_STATUSES),
            "approval_required_case_count": approval_required,
            "unresolved_exception_count": len(unresolved_exception_ids),
            "unresolved_exception_categories": {
                "elevated_open_cases": len(elevated_case_ids),
                "broken_promise_cases": len(broken_promise_case_ids),
                "active_dispute_cases": len(dispute_case_ids),
                "workflow_requests_awaiting_approval": len(pending_case_ids),
            },
            "exception_categories_overlap": exception_memberships > len(unresolved_exception_ids),
            "hold_evidence": hold_rows,
        },
        "action_outcomes": {
            "persisted_action_count": len(scoped_actions),
            "recommended": action_counts["RECOMMENDED"],
            "planned": action_counts["PLANNED"],
            "pending_approval": action_counts["PENDING_APPROVAL"],
            "approved": action_counts["APPROVED"],
            "held": action_counts["HELD"],
            "rejected": action_counts["REJECTED"],
            "executed": action_counts["EXECUTED"],
            "cancelled": action_counts["CANCELLED"],
            "failed": action_counts["FAILED"],
            "payment_requests_created": len(scoped_requests),
            "provider_events_received": len(scoped_provider_events),
            "payments_persisted": qualifying_payment_count,
            "duplicate_provider_events_ignored": duplicate_count,
        },
        "baseline": {
            "name": "Age-only action-volume baseline",
            "same_scope": True,
            "same_operating_date": simulation_date,
            "age_only_target_count": len(age_only_targets),
            "reconmate_immediate_action_count": immediate_action_cases,
            "reconmate_deliberate_hold_count": len(deliberate_hold_ids),
            "blocker_violations_avoided": blocker_violations_avoided,
            "limitation": "The baseline uses the same current portfolio and operating date. Payment outcomes are not re-simulated, so no counterfactual recovery amount is claimed.",
        },
        "payment_evidence": payment_evidence,
        "payment_provenance": [
            {"source": source, "payment_count": values["payment_count"], "amount": _money(values["amount"])}
            for source, values in sorted(provenance_counts.items())
        ],
    }
