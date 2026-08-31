"""Read-only paired recovery experiment over deterministic shadow case snapshots.

This module never mutates persisted portfolio state.  It is deliberately kept
separate from observed payment reconciliation: its outputs are simulated
experimental estimates, not production causal claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from statistics import mean, median
from types import SimpleNamespace
from typing import Any, Iterable

from app.models.domain import (
    InvoiceStatus,
    PromiseStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCase,
    RecoveryState,
)
from app.recommendations.schemas import RecommendedAction
from app.recommendations.service import recommend_case
from app.recovery.engine import evaluate_case
from app.simulation.config import SCENARIO_CONFIG


EXPERIMENT_SEED = 20260831
EXPERIMENT_VERSION = "paired-shadow-v1"
HORIZON_DAYS = 30
BASELINE_CADENCE_DAYS = 14
RECONMATE_ACTION_CADENCE_DAYS = 7
ASSOCIATION_WINDOW_DAYS = 7
PROMISE_FULFILMENT_PROBABILITY = Decimal("0.55")
DAILY_DISPUTE_RESOLUTION_PROBABILITY = Decimal("0.04")
MATERIAL_APPROVAL_PROBABILITY = Decimal("0.80")
BASELINE_RESPONSE_INCREMENT = Decimal("0.020")
RECONMATE_RESPONSE_INCREMENT = {
    RecommendedAction.SEND_PAYMENT_REMINDER: Decimal("0.025"),
    RecommendedAction.REQUEST_PAYMENT_DATE: Decimal("0.030"),
}
HOLD_ACTIONS = {
    RecommendedAction.NO_ACTION_REQUIRED,
    RecommendedAction.HOLD_FOR_DISPUTE,
    RecommendedAction.MONITOR_ACTIVE_PROMISE,
    RecommendedAction.REVIEW_PAYMENT_CLAIM,
}


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _draw(seed: int, pair_id: str, day: int, channel: str) -> Decimal:
    digest = sha256(f"{seed}|{pair_id}|{day}|{channel}".encode()).digest()
    return Decimal(int.from_bytes(digest[:8], "big")) / Decimal(2**64)


def _natural_daily_probability(days_overdue: int) -> Decimal:
    age_component = min(max(days_overdue, 0), 180) / 180
    return Decimal("0.006") + Decimal(str(age_component)) * Decimal("0.009")


def _fraction(balance: Decimal, draw: Decimal) -> Decimal:
    minimum = Decimal(str(SCENARIO_CONFIG.payment_fraction_min))
    maximum = Decimal(str(SCENARIO_CONFIG.payment_fraction_max))
    return max(Decimal("0.01"), min(balance, (balance * (minimum + (maximum - minimum) * draw)).quantize(Decimal("0.01"))))


def _payment_amount(balance: Decimal, draw: Decimal) -> Decimal:
    return balance if draw < Decimal("0.30") else _fraction(balance, draw)


@dataclass
class _ArmState:
    name: str
    case: Any
    starting_exposure: Decimal
    recovered: Decimal = Decimal("0")
    action_attempts: int = 0
    actions_completed: int = 0
    dispute_contact_violations: int = 0
    active_promise_contact_violations: int = 0
    deferred: bool = False
    last_action_day: int | None = None
    active_response_until: int | None = None
    active_response_increment: Decimal = Decimal("0")
    active_action_reference: str | None = None
    fully_recovered_day: int | None = None
    payments: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)


def _shadow_case(source: RecoveryCase, simulation_date: date) -> Any:
    """Create an isolated minimum graph accepted by the authoritative policy."""
    invoice = source.invoice
    if invoice is None:
        raise ValueError("Recovery experiment requires an invoice-backed case.")
    customer = SimpleNamespace(
        id=source.customer.id,
        name=source.customer.name,
        account_reference=source.customer.account_reference,
        segment=source.customer.segment,
        is_strategic_account=bool(source.customer.is_strategic_account),
        communications=list(source.customer.communications),
    )
    shadow_invoice = SimpleNamespace(
        id=invoice.id,
        customer_id=source.customer.id,
        customer=customer,
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        original_amount=invoice.outstanding_amount,
        outstanding_amount=invoice.outstanding_amount,
        status=invoice.status,
        payments=[],
        promises_to_pay=[],
    )
    current_promise_facts = evaluate_case(source, simulation_date).promises
    for facts in current_promise_facts:
        if facts.state not in {"ACTIVE", "BROKEN"}:
            continue
        shadow_invoice.promises_to_pay.append(SimpleNamespace(
            id=facts.id,
            customer_id=source.customer.id,
            invoice_id=invoice.id,
            promised_amount=min(facts.promised_amount, invoice.outstanding_amount),
            promised_date=facts.promised_date,
            status=PromiseStatus.ACTIVE if facts.state == "ACTIVE" else PromiseStatus.BROKEN,
            invoice=shadow_invoice,
            source_communication=None,
        ))
    return SimpleNamespace(
        id=source.id,
        customer_id=source.customer.id,
        invoice_id=invoice.id,
        customer=customer,
        invoice=shadow_invoice,
        current_state=source.current_state,
        priority=source.priority,
        opened_at=source.opened_at,
        updated_at=source.updated_at,
        closed_at=None,
        actions=[],
    )


def _initial_exception_categories(case: RecoveryCase, simulation_date: date) -> list[str]:
    evaluation = evaluate_case(case, simulation_date)
    categories: list[str] = []
    if evaluation.active_dispute:
        categories.append("ACTIVE_DISPUTE")
    if any(item.state == "ACTIVE" for item in evaluation.promises):
        categories.append("ACTIVE_PAYMENT_PROMISE")
    if any(item.state == "BROKEN" for item in evaluation.promises):
        categories.append("BROKEN_PAYMENT_PROMISE")
    if case.customer.is_strategic_account:
        categories.append("STRATEGIC_ACCOUNT")
    if case.priority.value in {"HIGH", "CRITICAL"}:
        categories.append("ELEVATED_PRIORITY")
    return categories


def _apply_payment(
    state: _ArmState,
    *,
    pair_id: str,
    day: int,
    amount: Decimal,
    event_type: str,
    association: str,
    action_reference: str | None = None,
) -> None:
    invoice = state.case.invoice
    amount = min(amount, invoice.outstanding_amount)
    if amount <= 0:
        return
    before = invoice.outstanding_amount
    invoice.outstanding_amount -= amount
    invoice.status = InvoiceStatus.PAID if invoice.outstanding_amount == 0 else InvoiceStatus.PARTIALLY_PAID
    state.recovered += amount
    event_id = f"EXP-{pair_id}-{state.name}-{day:02d}-{len(state.payments) + 1}"
    state.payments.append({
        "event_id": event_id,
        "day": day,
        "event_type": event_type,
        "amount": _money(amount),
        "outstanding_before": _money(before),
        "outstanding_after": _money(invoice.outstanding_amount),
        "association": association,
        "action_reference": action_reference,
    })
    if invoice.outstanding_amount == 0 and state.fully_recovered_day is None:
        state.fully_recovered_day = day


def _external_events(state: _ArmState, *, seed: int, pair_id: str, day: int, current_date: date) -> None:
    invoice = state.case.invoice
    if invoice.outstanding_amount <= 0:
        return
    if invoice.status is InvoiceStatus.DISPUTED and _draw(seed, pair_id, day, "dispute-resolution") < DAILY_DISPUTE_RESOLUTION_PROBABILITY:
        invoice.status = InvoiceStatus.OVERDUE
    for promise in invoice.promises_to_pay:
        if promise.status is not PromiseStatus.ACTIVE or promise.promised_date > current_date:
            continue
        if _draw(seed, pair_id, day, f"promise-{promise.id}") < PROMISE_FULFILMENT_PROBABILITY:
            amount = min(promise.promised_amount, invoice.outstanding_amount)
            promise.status = PromiseStatus.FULFILLED
            _apply_payment(
                state, pair_id=pair_id, day=day, amount=amount,
                event_type="PROMISE_PAYMENT_EVENT", association="PROMISE_FULFILMENT",
            )
        elif promise.promised_date < current_date:
            promise.status = PromiseStatus.BROKEN


def _record_action(state: _ArmState, *, pair_id: str, day: int, current_date: date, action: str, completed: bool, effect: Decimal) -> None:
    state.action_attempts += 1
    reference = f"ACT-{pair_id}-{state.name}-{day:02d}-{state.action_attempts}"
    state.actions.append({
        "action_reference": reference,
        "day": day,
        "action": action,
        "completed": completed,
        "simulated_response_increment": str(effect if completed else Decimal("0")),
    })
    state.last_action_day = day
    if not completed:
        return
    state.actions_completed += 1
    if effect > 0:
        state.active_response_until = day + ASSOCIATION_WINDOW_DAYS - 1
        state.active_response_increment = effect
        state.active_action_reference = reference
    state.case.actions.append(SimpleNamespace(
        action_type=RecoveryActionType.FOLLOW_UP,
        status=RecoveryActionStatus.EXECUTED,
        executed_at=datetime.combine(current_date, datetime.min.time(), tzinfo=UTC),
    ))


def _baseline_policy(state: _ArmState, *, pair_id: str, day: int, current_date: date) -> None:
    if day % BASELINE_CADENCE_DAYS:
        return
    evaluation = evaluate_case(state.case, current_date)
    if evaluation.active_dispute:
        state.dispute_contact_violations += 1
    if any(item.state == "ACTIVE" for item in evaluation.promises):
        state.active_promise_contact_violations += 1
    _record_action(
        state, pair_id=pair_id, day=day, current_date=current_date, action="STANDARD_SCHEDULED_REMINDER",
        completed=True, effect=BASELINE_RESPONSE_INCREMENT,
    )


def _reconmate_policy(state: _ArmState, *, seed: int, pair_id: str, day: int, current_date: date) -> None:
    recommendation = recommend_case(state.case, current_date)
    decision = recommendation.recommended_action.value
    if not state.decisions or state.decisions[-1] != decision:
        state.decisions.append(decision)
    if recommendation.blockers or recommendation.recommended_action in HOLD_ACTIONS:
        if recommendation.blockers or recommendation.recommended_action in {
            RecommendedAction.HOLD_FOR_DISPUTE,
            RecommendedAction.MONITOR_ACTIVE_PROMISE,
        }:
            state.deferred = True
        return
    if state.last_action_day is not None and day - state.last_action_day < RECONMATE_ACTION_CADENCE_DAYS:
        return
    approved = not recommendation.human_approval_required or (
        _draw(seed, pair_id, day, "material-approval") < MATERIAL_APPROVAL_PROBABILITY
    )
    effect = RECONMATE_RESPONSE_INCREMENT.get(recommendation.recommended_action, Decimal("0"))
    _record_action(
        state, pair_id=pair_id, day=day, current_date=current_date, action=decision,
        completed=approved, effect=effect,
    )


def _simulated_payment(state: _ArmState, *, seed: int, pair_id: str, day: int, current_date: date) -> None:
    invoice = state.case.invoice
    if invoice.outstanding_amount <= 0 or invoice.status is InvoiceStatus.DISPUTED:
        return
    days_overdue = max(0, (current_date - invoice.due_date).days)
    natural = _natural_daily_probability(days_overdue)
    effect = state.active_response_increment if state.active_response_until is not None and day <= state.active_response_until else Decimal("0")
    occurrence = _draw(seed, pair_id, day, "payment-occurrence")
    if occurrence >= natural + effect:
        return
    amount = _payment_amount(invoice.outstanding_amount, _draw(seed, pair_id, day, "payment-amount"))
    if occurrence < natural:
        association = "NATURAL_SIMULATED_RECOVERY"
        action_reference = None
    elif state.name == "RECONMATE":
        association = "INTERVENTION_ASSOCIATED"
        action_reference = state.active_action_reference
    else:
        association = "STANDARD_COLLECTIONS_ASSOCIATED"
        action_reference = state.active_action_reference
    _apply_payment(
        state, pair_id=pair_id, day=day, amount=amount,
        event_type="SIMULATED_PAYMENT_EVENT", association=association,
        action_reference=action_reference,
    )


def _simulate_arm(source: RecoveryCase, *, arm: str, seed: int, simulation_date: date) -> _ArmState:
    shadow = _shadow_case(source, simulation_date)
    state = _ArmState(name=arm, case=shadow, starting_exposure=shadow.invoice.outstanding_amount)
    pair_id = str(source.id)
    for day in range(HORIZON_DAYS):
        if shadow.invoice.outstanding_amount <= 0:
            break
        current_date = simulation_date + timedelta(days=day)
        _external_events(state, seed=seed, pair_id=pair_id, day=day, current_date=current_date)
        if shadow.invoice.outstanding_amount <= 0:
            break
        if arm == "BASELINE":
            _baseline_policy(state, pair_id=pair_id, day=day, current_date=current_date)
        else:
            _reconmate_policy(state, seed=seed, pair_id=pair_id, day=day, current_date=current_date)
        _simulated_payment(state, seed=seed, pair_id=pair_id, day=day, current_date=current_date)
    return state


def _arm_metrics(states: list[_ArmState]) -> dict[str, Any]:
    starting = sum((state.starting_exposure for state in states), Decimal("0"))
    recovered = sum((state.recovered for state in states), Decimal("0"))
    remaining = starting - recovered
    recovery_rate = Decimal("0") if starting == 0 else (recovered / starting * Decimal("100")).quantize(Decimal("0.01"))
    recovery_days = [state.fully_recovered_day for state in states if state.fully_recovered_day is not None]
    associated = sum((
        Decimal(payment["amount"])
        for state in states for payment in state.payments
        if payment["association"] == "INTERVENTION_ASSOCIATED"
    ), Decimal("0"))
    return {
        "account_count": len(states),
        "starting_overdue_exposure": _money(starting),
        "recovered_amount": _money(recovered),
        "recovery_rate": str(recovery_rate),
        "remaining_overdue": _money(remaining),
        "fully_recovered_accounts": len(recovery_days),
        "median_days_to_full_recovery": str(Decimal(str(median(recovery_days))).quantize(Decimal("0.1"))) if recovery_days else None,
        "average_days_to_full_recovery": str(Decimal(str(mean(recovery_days))).quantize(Decimal("0.1"))) if recovery_days else None,
        "actions_attempted": sum(state.action_attempts for state in states),
        "actions_completed": sum(state.actions_completed for state in states),
        "accounts_intentionally_deferred": sum(state.deferred for state in states),
        "dispute_contact_violations": sum(state.dispute_contact_violations for state in states),
        "active_promise_contact_violations": sum(state.active_promise_contact_violations for state in states),
        "unrecovered_exceptions": sum(state.case.invoice.outstanding_amount > 0 for state in states),
        "intervention_associated_amount": _money(associated),
        "equation_holds": starting == recovered + remaining,
    }


def build_recovery_experiment(
    *,
    simulation_date: date,
    cases: Iterable[RecoveryCase],
    seed: int = EXPERIMENT_SEED,
) -> dict[str, Any]:
    """Build paired baseline/ReconMate shadow cohorts from current case facts."""
    candidates = sorted((
        case for case in cases
        if case.invoice is not None
        and case.invoice.due_date < simulation_date
        and case.invoice.outstanding_amount > 0
        and case.invoice.status not in {InvoiceStatus.CANCELLED, InvoiceStatus.WRITTEN_OFF, InvoiceStatus.PAID}
        and case.current_state not in {RecoveryState.RESOLVED, RecoveryState.CLOSED}
    ), key=lambda item: (item.customer.account_reference, item.invoice.invoice_number, str(item.id)))
    baseline_states: list[_ArmState] = []
    reconmate_states: list[_ArmState] = []
    evidence: list[dict[str, Any]] = []
    for case in candidates:
        baseline = _simulate_arm(case, arm="BASELINE", seed=seed, simulation_date=simulation_date)
        reconmate = _simulate_arm(case, arm="RECONMATE", seed=seed, simulation_date=simulation_date)
        baseline_states.append(baseline)
        reconmate_states.append(reconmate)
        initial = recommend_case(case, simulation_date)
        categories = _initial_exception_categories(case, simulation_date)
        evidence.append({
            "pair_id": str(case.id),
            "customer_id": str(case.customer.id),
            "customer_name": case.customer.name,
            "invoice_id": str(case.invoice.id),
            "invoice_number": case.invoice.invoice_number,
            "starting_overdue_exposure": _money(case.invoice.outstanding_amount),
            "days_overdue_at_start": (simulation_date - case.invoice.due_date).days,
            "initial_recommendation": initial.recommended_action.value,
            "initial_blockers": initial.blockers,
            "exception_categories": categories,
            "baseline": {
                "recovered_amount": _money(baseline.recovered),
                "remaining_overdue": _money(baseline.case.invoice.outstanding_amount),
                "actions": baseline.actions,
                "payments": baseline.payments,
            },
            "reconmate": {
                "recovered_amount": _money(reconmate.recovered),
                "remaining_overdue": _money(reconmate.case.invoice.outstanding_amount),
                "intentionally_deferred": reconmate.deferred,
                "decisions": reconmate.decisions,
                "actions": reconmate.actions,
                "payments": reconmate.payments,
            },
        })
    baseline_metrics = _arm_metrics(baseline_states)
    reconmate_metrics = _arm_metrics(reconmate_states)
    baseline_recovered = Decimal(baseline_metrics["recovered_amount"])
    reconmate_recovered = Decimal(reconmate_metrics["recovered_amount"])
    rate_difference = Decimal(reconmate_metrics["recovery_rate"]) - Decimal(baseline_metrics["recovery_rate"])
    starting_equal = baseline_metrics["starting_overdue_exposure"] == reconmate_metrics["starting_overdue_exposure"]
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "seed": seed,
        "horizon_days": HORIZON_DAYS,
        "methodology": {
            "design": "Paired shadow cohorts with exact case-level starting-condition twins and common random event draws.",
            "assignment": "Every eligible synthetic recovery case is copied into one isolated baseline arm and one isolated ReconMate arm; persisted data is never changed.",
            "baseline_policy": f"Standard scheduled reminder every {BASELINE_CADENCE_DAYS} days; no individualized dispute/promise reassessment.",
            "reconmate_policy": "The authoritative deterministic recommendation is recomputed daily; disputes and active promises defer contact, material actions require simulated operator approval, and only eligible outreach can alter the simulated response window.",
            "outcome_model": "Both arms share the same seeded natural-payment, promise, dispute-resolution, and payment-amount draws. Policy changes only bounded response thresholds after a completed eligible action.",
            "attribution_window_days": ASSOCIATION_WINDOW_DAYS,
        },
        "assumptions": [
            f"Natural daily payment probability is 0.6% plus an age component capped at 0.9%; identical draws are used in both arms.",
            f"A standard reminder adds 2.0 percentage points to the response threshold for {ASSOCIATION_WINDOW_DAYS} days.",
            f"Eligible ReconMate reminder/payment-date actions add 2.5/3.0 percentage points for {ASSOCIATION_WINDOW_DAYS} days; internal escalation preparation has no payment effect.",
            "Eligible non-material workflows are assumed completed by an operator at the evaluation cadence; they are not described as autonomous execution.",
            "Material operator approvals complete with a seeded 80% probability.",
            "Active promises have a seeded 55% fulfilment probability at the recorded date; disputes resolve with a seeded 4% daily probability.",
            "Payment amounts use the existing simulation's bounded partial-payment fractions; a seeded 30% branch produces full payment.",
        ],
        "cohort_construction": {
            "pair_count": len(candidates),
            "baseline_account_count": len(baseline_states),
            "reconmate_account_count": len(reconmate_states),
            "exact_starting_exposure_match": starting_equal,
            "baseline_starting_exposure": baseline_metrics["starting_overdue_exposure"],
            "reconmate_starting_exposure": reconmate_metrics["starting_overdue_exposure"],
            "matching_fields": ["case", "customer", "invoice", "starting outstanding", "days overdue", "priority", "dispute", "promise", "strategic status"],
            "exception_memberships": sum(len(row["exception_categories"]) for row in evidence),
            "unique_accounts_with_exceptions": sum(bool(row["exception_categories"]) for row in evidence),
            "exception_categories_overlap": any(len(row["exception_categories"]) > 1 for row in evidence),
        },
        "baseline": baseline_metrics,
        "reconmate": reconmate_metrics,
        "difference": {
            "recovered_amount": _money(reconmate_recovered - baseline_recovered),
            "recovery_rate_percentage_points": str(rate_difference.quantize(Decimal("0.01"))),
            "remaining_overdue": _money(Decimal(reconmate_metrics["remaining_overdue"]) - Decimal(baseline_metrics["remaining_overdue"])),
        },
        "claim_boundaries": {
            "observed_portfolio_recovery": "Persisted payments in the reconciliation above; no intervention causality is assigned.",
            "intervention_associated_outcomes": "Simulated payments occurring only inside a completed eligible-action window; association is not proof of causation.",
            "simulated_experimental_lift": "Difference between seeded paired shadow cohorts under the stated model assumptions.",
            "real_world_causal_claim": "NONE. Production causality requires a prospectively randomized or otherwise identified real-world evaluation.",
        },
        "evidence": evidence,
    }
