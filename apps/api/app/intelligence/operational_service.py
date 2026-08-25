"""Fresh, explainable and read-only intelligence over established domain facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from app.intelligence.operational_schemas import (
    ContributingFactor,
    IntelligenceMetrics,
    IntelligenceRecommendation,
    IntelligenceResult,
    IntelligenceSignal,
    PortfolioIntelligence,
    PriorityLevel,
    RecommendationAction,
    SignalType,
)
from app.models.domain import (
    Customer,
    Invoice,
    InvoiceStatus,
    PromiseToPay,
    RecoveryCase,
    RecoveryState,
)
from app.recovery.engine import evaluate_invoice, evaluate_promise


@dataclass(frozen=True)
class IntelligencePolicy:
    """All tunable scoring thresholds and weights live in one place."""

    high_value_overdue_amount: Decimal = Decimal("250000")
    high_recovery_exposure_amount: Decimal = Decimal("400000")
    long_overdue_days: int = 30
    severe_overdue_days: int = 90
    critical_overdue_days: int = 120
    stalled_payment_days: int = 30
    severely_stalled_payment_days: int = 60
    stalled_recovery_days: int = 21
    medium_score: int = 20
    high_score: int = 45
    critical_score: int = 80
    high_value_overdue_points: int = 16
    high_recovery_exposure_points: int = 22
    long_overdue_points: int = 8
    severe_overdue_points: int = 18
    critical_overdue_points: int = 22
    multiple_overdue_points: int = 6
    several_overdue_points: int = 10
    many_overdue_points: int = 14
    broken_promise_points: int = 20
    multiple_broken_promises_points: int = 30
    stalled_payment_points: int = 10
    severely_stalled_payment_points: int = 14
    active_dispute_points: int = 20
    stalled_recovery_points: int = 10


POLICY = IntelligencePolicy()
_INACTIVE_CASE_STATES = {RecoveryState.RESOLVED, RecoveryState.CLOSED}


@dataclass(frozen=True)
class _Scope:
    invoices: list[Invoice]
    promises: list[PromiseToPay]
    cases: list[RecoveryCase]


def priority_level(score: int, policy: IntelligencePolicy = POLICY) -> PriorityLevel:
    """Map a bounded score to the centralized operational priority bands."""
    if score >= policy.critical_score:
        return PriorityLevel.CRITICAL
    if score >= policy.high_score:
        return PriorityLevel.HIGH
    if score >= policy.medium_score:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


def _severity(points: int, policy: IntelligencePolicy) -> PriorityLevel:
    if points >= policy.multiple_broken_promises_points:
        return PriorityLevel.CRITICAL
    if points >= policy.high_value_overdue_points:
        return PriorityLevel.HIGH
    if points >= policy.long_overdue_points:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


def _same_invoice(left: Invoice | None, right: Invoice) -> bool:
    if left is right:
        return True
    return left is not None and left.id is not None and right.id is not None and left.id == right.id


def _latest_case_activity(case: RecoveryCase) -> date | None:
    values: list[date] = []
    for value in (case.updated_at, case.opened_at):
        if isinstance(value, datetime):
            values.append(value.date())
    for action in case.actions:
        for value in (action.executed_at, action.created_at):
            if isinstance(value, datetime):
                values.append(value.date())
    return max(values, default=None)


def _metrics(scope: _Scope, calculated_at: date, policy: IntelligencePolicy) -> IntelligenceMetrics:
    invoice_facts = [(invoice, evaluate_invoice(invoice, calculated_at)) for invoice in scope.invoices]
    overdue = [(invoice, facts) for invoice, facts in invoice_facts if facts.state == "OVERDUE"]
    payments = [payment for invoice in scope.invoices for payment in invoice.payments if payment.payment_date <= calculated_at]
    last_payment = max((payment.payment_date for payment in payments), default=None)
    promise_facts = [evaluate_promise(promise, calculated_at) for promise in scope.promises]
    active_cases = [case for case in scope.cases if case.current_state not in _INACTIVE_CASE_STATES and case.closed_at is None]
    stalled_cases = []
    for case in active_cases:
        activity = _latest_case_activity(case)
        if activity is None or (calculated_at - activity).days >= policy.stalled_recovery_days:
            stalled_cases.append(case)
    return IntelligenceMetrics(
        total_outstanding_amount=sum((facts.outstanding_amount for _, facts in invoice_facts), Decimal("0")),
        overdue_exposure=sum((facts.outstanding_amount for _, facts in overdue), Decimal("0")),
        overdue_invoice_count=len(overdue),
        max_days_overdue=max((facts.days_overdue for _, facts in overdue), default=0),
        broken_promise_count=sum(facts.state == "BROKEN" for facts in promise_facts),
        active_promise_count=sum(facts.state == "ACTIVE" for facts in promise_facts),
        active_dispute_count=sum(
            invoice.status is InvoiceStatus.DISPUTED and invoice.outstanding_amount > 0 for invoice in scope.invoices
        ),
        days_since_last_payment=(calculated_at - last_payment).days if last_payment is not None else None,
        active_recovery_case_count=len(active_cases),
        stalled_recovery_case_count=len(stalled_cases),
    )


def _signal(
    signal_type: SignalType,
    points: int,
    title: str,
    explanation: str,
    value: Decimal | int | str | None,
    calculated_at: date,
    policy: IntelligencePolicy,
) -> tuple[IntelligenceSignal, ContributingFactor]:
    impact = _severity(points, policy)
    return (
        IntelligenceSignal(
            type=signal_type,
            severity=impact,
            title=title,
            explanation=explanation,
            contributing_value=value,
            calculated_at=calculated_at,
        ),
        ContributingFactor(
            type=signal_type,
            title=title,
            impact=impact,
            points=points,
            explanation=explanation,
            contributing_value=value,
        ),
    )


def _signals_and_factors(
    metrics: IntelligenceMetrics,
    calculated_at: date,
    policy: IntelligencePolicy,
) -> tuple[list[IntelligenceSignal], list[ContributingFactor]]:
    entries: list[tuple[IntelligenceSignal, ContributingFactor]] = []

    if metrics.overdue_exposure >= policy.high_value_overdue_amount:
        entries.append(_signal(
            SignalType.HIGH_VALUE_OVERDUE,
            policy.high_value_overdue_points,
            "High-value overdue exposure",
            f"{metrics.overdue_exposure} is currently overdue.",
            metrics.overdue_exposure,
            calculated_at,
            policy,
        ))
    if metrics.max_days_overdue >= policy.long_overdue_days:
        if metrics.max_days_overdue >= policy.critical_overdue_days:
            points = policy.critical_overdue_points
        elif metrics.max_days_overdue >= policy.severe_overdue_days:
            points = policy.severe_overdue_points
        else:
            points = policy.long_overdue_points
        entries.append(_signal(
            SignalType.LONG_OVERDUE,
            points,
            "Long-overdue receivables",
            f"The oldest outstanding invoice is {metrics.max_days_overdue} days overdue.",
            metrics.max_days_overdue,
            calculated_at,
            policy,
        ))
    if metrics.overdue_invoice_count >= 2:
        if metrics.overdue_invoice_count >= 5:
            points = policy.many_overdue_points
        elif metrics.overdue_invoice_count >= 3:
            points = policy.several_overdue_points
        else:
            points = policy.multiple_overdue_points
        entries.append(_signal(
            SignalType.MULTIPLE_OVERDUE_INVOICES,
            points,
            "Multiple overdue invoices",
            f"{metrics.overdue_invoice_count} invoices currently have overdue balances.",
            metrics.overdue_invoice_count,
            calculated_at,
            policy,
        ))
    if metrics.broken_promise_count:
        multiple = metrics.broken_promise_count >= 2
        entries.append(_signal(
            SignalType.MULTIPLE_BROKEN_PROMISES if multiple else SignalType.BROKEN_PROMISE,
            policy.multiple_broken_promises_points if multiple else policy.broken_promise_points,
            "Repeated broken promises" if multiple else "Broken payment promise",
            f"{metrics.broken_promise_count} recorded payment promise{'s were' if multiple else ' was'} broken.",
            metrics.broken_promise_count,
            calculated_at,
            policy,
        ))
    if metrics.overdue_exposure > 0 and (
        metrics.days_since_last_payment is None or metrics.days_since_last_payment >= policy.stalled_payment_days
    ):
        severely_stalled = (
            metrics.days_since_last_payment is None
            or metrics.days_since_last_payment >= policy.severely_stalled_payment_days
        )
        if metrics.days_since_last_payment is None:
            explanation = "No payment activity is recorded while overdue exposure remains open."
            value: int | str = "NO_PAYMENT_RECORDED"
        else:
            explanation = f"No payment has been recorded for {metrics.days_since_last_payment} days."
            value = metrics.days_since_last_payment
        entries.append(_signal(
            SignalType.PAYMENT_ACTIVITY_STALLED,
            policy.severely_stalled_payment_points if severely_stalled else policy.stalled_payment_points,
            "Payment activity stalled",
            explanation,
            value,
            calculated_at,
            policy,
        ))
    if metrics.active_dispute_count:
        entries.append(_signal(
            SignalType.ACTIVE_DISPUTE,
            policy.active_dispute_points,
            "Active dispute requires review",
            f"{metrics.active_dispute_count} outstanding invoice{'s have' if metrics.active_dispute_count != 1 else ' has'} an active dispute.",
            metrics.active_dispute_count,
            calculated_at,
            policy,
        ))
    if metrics.stalled_recovery_case_count:
        entries.append(_signal(
            SignalType.RECOVERY_STALLED,
            policy.stalled_recovery_points,
            "Recovery work appears stalled",
            f"{metrics.stalled_recovery_case_count} active recovery case{'s have' if metrics.stalled_recovery_case_count != 1 else ' has'} no recent activity.",
            metrics.stalled_recovery_case_count,
            calculated_at,
            policy,
        ))
    if metrics.total_outstanding_amount >= policy.high_recovery_exposure_amount:
        entries.append(_signal(
            SignalType.HIGH_RECOVERY_EXPOSURE,
            policy.high_recovery_exposure_points,
            "High recovery exposure",
            f"Total outstanding exposure is {metrics.total_outstanding_amount}.",
            metrics.total_outstanding_amount,
            calculated_at,
            policy,
        ))

    return [entry[0] for entry in entries], [entry[1] for entry in entries]


def _recommendation(
    level: PriorityLevel,
    metrics: IntelligenceMetrics,
) -> IntelligenceRecommendation:
    if metrics.active_dispute_count:
        return IntelligenceRecommendation(
            action=RecommendationAction.REVIEW_DISPUTE,
            title="Review the active dispute",
            explanation="Keep collection outreach on hold and have an operator review the recorded dispute before recovery continues.",
            priority_level=level,
            operator_confirmation_required=True,
        )
    if metrics.active_promise_count:
        return IntelligenceRecommendation(
            action=RecommendationAction.WAIT_FOR_PROMISE,
            title="Monitor the active payment promise",
            explanation="Wait for the recorded promise deadline or matching payment evidence before taking another recovery action.",
            priority_level=level,
            operator_confirmation_required=False,
        )
    if level is PriorityLevel.CRITICAL:
        return IntelligenceRecommendation(
            action=RecommendationAction.ESCALATE,
            title="Escalate for senior collections review",
            explanation="The combined factual risk signals exceed the critical operational threshold and require human escalation review.",
            priority_level=level,
            operator_confirmation_required=True,
        )
    if metrics.broken_promise_count or level is PriorityLevel.HIGH:
        return IntelligenceRecommendation(
            action=RecommendationAction.PRIORITIZE_RECOVERY,
            title="Prioritize this recovery work",
            explanation="Material overdue conditions or broken commitments make this account a high-priority operator task.",
            priority_level=level,
            operator_confirmation_required=True,
        )
    if metrics.overdue_exposure > 0 or metrics.stalled_recovery_case_count:
        return IntelligenceRecommendation(
            action=RecommendationAction.FOLLOW_UP,
            title="Schedule an operator follow-up",
            explanation="Outstanding overdue exposure requires a deliberate follow-up using the existing approval-controlled workflow.",
            priority_level=level,
            operator_confirmation_required=True,
        )
    return IntelligenceRecommendation(
        action=RecommendationAction.MONITOR,
        title="Continue routine monitoring",
        explanation="No material overdue or recovery-risk condition currently requires operator intervention.",
        priority_level=level,
        operator_confirmation_required=False,
    )


def _evaluate(
    *,
    entity_type: str,
    entity_id: str,
    entity_name: str,
    scope: _Scope,
    calculated_at: date,
    policy: IntelligencePolicy,
) -> IntelligenceResult:
    metrics = _metrics(scope, calculated_at, policy)
    signals, factors = _signals_and_factors(metrics, calculated_at, policy)
    raw_score = max(0, sum(factor.points for factor in factors))
    score = min(100, raw_score)
    level = priority_level(score, policy)
    return IntelligenceResult(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        calculated_at=calculated_at,
        score=score,
        raw_score=raw_score,
        level=level,
        metrics=metrics,
        signals=signals,
        factors=factors,
        recommendation=_recommendation(level, metrics),
    )


def evaluate_customer_intelligence(
    customer: Customer,
    calculated_at: date,
    policy: IntelligencePolicy = POLICY,
) -> IntelligenceResult:
    """Evaluate the customer's current persisted portfolio without mutating it."""
    return _evaluate(
        entity_type="CUSTOMER",
        entity_id=str(customer.id),
        entity_name=customer.name,
        scope=_Scope(list(customer.invoices), list(customer.promises_to_pay), list(customer.recovery_cases)),
        calculated_at=calculated_at,
        policy=policy,
    )


def evaluate_case_intelligence(
    case: RecoveryCase,
    calculated_at: date,
    policy: IntelligencePolicy = POLICY,
) -> IntelligenceResult:
    """Evaluate one case, including the customer's factual promise history."""
    invoices = [case.invoice] if case.invoice is not None else list(case.customer.invoices)
    promises = [
        promise for promise in case.customer.promises_to_pay
        if case.invoice is None or promise.invoice is None or _same_invoice(promise.invoice, case.invoice)
    ]
    invoice_label = f" / {case.invoice.invoice_number}" if case.invoice is not None else ""
    return _evaluate(
        entity_type="RECOVERY_CASE",
        entity_id=str(case.id),
        entity_name=f"{case.customer.name}{invoice_label}",
        scope=_Scope(invoices, promises, [case]),
        calculated_at=calculated_at,
        policy=policy,
    )


def evaluate_portfolio_intelligence(
    customers: list[Customer],
    calculated_at: date,
    policy: IntelligencePolicy = POLICY,
) -> PortfolioIntelligence:
    """Evaluate and rank every customer using fresh current-state facts."""
    results = [evaluate_customer_intelligence(customer, calculated_at, policy) for customer in customers]
    results.sort(key=lambda item: (-item.score, -item.metrics.overdue_exposure, item.entity_name, item.entity_id))
    counts = {level: sum(result.level is level for result in results) for level in PriorityLevel}
    average = (
        Decimal(sum(result.score for result in results)) / Decimal(len(results))
        if results else Decimal("0")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return PortfolioIntelligence(
        calculated_at=calculated_at,
        customer_count=len(results),
        average_score=average,
        level_counts=counts,
        highest_priority=results[:10],
        customers=results,
    )
