"""Centralized, read-only data tools used by command planning."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.intelligence.operational_schemas import IntelligenceResult, PortfolioIntelligence, PriorityLevel, SignalType
from app.intelligence.operational_service import (
    evaluate_customer_intelligence,
    evaluate_portfolio_intelligence,
)
from app.commands.schemas import DirectQueryRecord, InspectionScope, LatestCycleEvidence, QueryEntity, QuerySort, QueryTimeScope, StructuredQuery
from app.models.domain import (
    Communication,
    AuditEvent,
    Customer,
    Invoice,
    InvoiceStatus,
    Payment,
    PromiseToPay,
    RecoveryCase,
    SimulationState,
    SimulationEvent,
)
from app.intelligence.operational_schemas import RecommendationAction
from app.recommendations.schemas import RecommendedAction, RecoveryRecommendation
from app.recommendations.service import recommend_case


class CommandDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaseCandidate:
    case: RecoveryCase
    intelligence: IntelligenceResult
    recommendation: RecoveryRecommendation
    risk_level: PriorityLevel


@dataclass(frozen=True)
class QueryExecution:
    records: list[Any]
    inspected: int
    matched: int
    exclusions: list[tuple[str, int]]
    scope: InspectionScope


def _customer_query():
    return select(Customer).options(
        selectinload(Customer.invoices).selectinload(Invoice.payments),
        selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.invoice).selectinload(Invoice.payments),
        selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(Customer.recovery_cases).selectinload(RecoveryCase.actions),
        selectinload(Customer.recovery_cases).selectinload(RecoveryCase.invoice),
    )


def _case_query():
    return select(RecoveryCase).options(
        selectinload(RecoveryCase.customer).selectinload(Customer.invoices).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.customer).selectinload(Customer.communications).selectinload(Communication.analyses),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.invoice).selectinload(Invoice.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )


class CommandTools:
    """One request-scoped facade over current operational data and Phase A intelligence."""

    def __init__(self, db: Session):
        self.db = db
        self.simulation_date = db.scalar(
            select(SimulationState.simulation_date).where(SimulationState.name == "default")
        )
        if self.simulation_date is None:
            raise CommandDataError("Synthetic simulation state has not been seeded.")
        self._customers: list[Customer] | None = None
        self._cases: list[RecoveryCase] | None = None
        self._portfolio: PortfolioIntelligence | None = None
        self._customer_intelligence: dict[str, IntelligenceResult] = {}

    def customers(self) -> list[Customer]:
        if self._customers is None:
            self._customers = list(self.db.scalars(_customer_query().order_by(Customer.account_reference)).all())
        return self._customers

    def cases(self) -> list[RecoveryCase]:
        if self._cases is None:
            self._cases = list(self.db.scalars(_case_query().order_by(RecoveryCase.opened_at, RecoveryCase.id)).all())
        return self._cases

    def get_portfolio_intelligence(self) -> PortfolioIntelligence:
        if self._portfolio is None:
            self._portfolio = evaluate_portfolio_intelligence(self.customers(), self.simulation_date)
            self._customer_intelligence.update({item.entity_id: item for item in self._portfolio.customers})
        return self._portfolio

    def get_customer_intelligence(self, customer_id: UUID) -> IntelligenceResult | None:
        cache = getattr(self, "_customer_intelligence", {})
        cached = cache.get(str(customer_id))
        if cached is not None:
            return cached
        customer = next((item for item in self.customers() if item.id == customer_id), None)
        if customer is None:
            return None
        result = evaluate_customer_intelligence(customer, self.simulation_date)
        cache[str(customer_id)] = result
        self._customer_intelligence = cache
        return result

    def get_customer(self, customer_id: UUID | str) -> Customer | None:
        return next((item for item in self.customers() if str(item.id) == str(customer_id)), None)

    def get_case_intelligence(self, case_id: UUID) -> IntelligenceResult | None:
        case = self.get_case(case_id)
        return self._case_scoped_customer_intelligence(case) if case is not None else None

    def get_case(self, case_id: UUID | str) -> RecoveryCase | None:
        return next((item for item in self.cases() if str(item.id) == str(case_id)), None)

    def resolve_comparison(self, command: str) -> list[IntelligenceResult]:
        """Resolve exactly two persisted customer names without guessing a ranking fallback."""
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", command.lower()).split())
        matches: list[tuple[int, Customer]] = []
        ignored = {"office", "mart", "partners", "network", "systems", "works", "manufacturing", "infrastructure"}
        for customer in self.customers():
            name = " ".join(re.sub(r"[^a-z0-9]+", " ", customer.name.lower()).split())
            if name and name in normalized:
                matches.append((100 + len(name), customer))
                continue
            tokens = [token for token in name.split() if len(token) >= 5 and token not in ignored]
            hit = max((len(token) for token in tokens if re.search(rf"\b{re.escape(token)}\b", normalized)), default=0)
            if hit:
                matches.append((hit, customer))
        matches.sort(key=lambda item: (-item[0], item[1].name))
        unique = []
        for _, customer in matches:
            if customer.id not in {item.id for item in unique}:
                unique.append(customer)
        if len(unique) != 2:
            return []
        return [self.get_customer_intelligence(customer.id) for customer in unique if self.get_customer_intelligence(customer.id) is not None]

    def execute_direct_query(self, query: StructuredQuery, customer_id: UUID | None = None) -> QueryExecution:
        """Return persisted invoice/payment rows using only structured deterministic predicates."""
        customers = self.customers()
        invoices = [invoice for customer in customers for invoice in customer.invoices]
        payments = [payment for invoice in invoices for payment in invoice.payments]
        customer_by_id = {customer.id: customer for customer in customers}
        invoice_by_id = {invoice.id: invoice for invoice in invoices}
        scope = InspectionScope(
            customers=len(customers), invoices=len(invoices), payments=len(payments),
            promises=sum(len(customer.promises_to_pay) for customer in customers),
            active_disputes=sum(invoice.status is InvoiceStatus.DISPUTED and invoice.outstanding_amount > 0 for invoice in invoices),
            recovery_cases=sum(len(customer.recovery_cases) for customer in customers),
            latest_cycle_events=self._latest_cycle_event_count(),
        )
        exclusions: list[tuple[str, int]] = []

        if query.entity is QueryEntity.INVOICES:
            rows = list(invoices)
            predicates = [
                ("Different customer", lambda item: customer_id is None or item.customer_id == customer_id),
                ("Invoice reference did not match", lambda item: not query.exact_reference or item.invoice_number.lower() == query.exact_reference.lower() or str(item.id).lower() == query.exact_reference.lower()),
                ("Invoice is not currently unpaid", lambda item: query.overdue is not True or (item.issue_date <= self.simulation_date and item.due_date < self.simulation_date and item.outstanding_amount > 0)),
                ("Invoice is outside the requested age", lambda item: query.min_days_overdue is None or (self.simulation_date - item.due_date).days >= query.min_days_overdue),
                ("Invoice is outside the requested age", lambda item: query.max_days_overdue is None or (self.simulation_date - item.due_date).days <= query.max_days_overdue),
                ("Outstanding amount is below the requested threshold", lambda item: query.min_exposure is None or item.outstanding_amount >= query.min_exposure),
                ("Outstanding amount is above the requested threshold", lambda item: query.max_exposure is None or item.outstanding_amount <= query.max_exposure),
                ("Invoice is not partially paid", lambda item: query.partial_payment is not True or Decimal("0") < item.outstanding_amount < item.original_amount),
            ]
            matched = self._filter_direct(rows, predicates, exclusions)
            matched.sort(key=lambda item: self._invoice_sort_key(item, query), reverse=query.descending)
            returned = matched if query.count_only or query.limit is None else matched[:query.limit]
            records = [self._invoice_record(item, customer_by_id[item.customer_id]) for item in returned]
            return QueryExecution(records, len(rows), len(matched), exclusions, scope)

        rows = list(payments)
        predicates = [
            ("Different customer", lambda item: customer_id is None or invoice_by_id[item.invoice_id].customer_id == customer_id),
            ("Payment reference did not match", lambda item: not query.exact_reference or (item.reference or "").lower() == query.exact_reference.lower() or str(item.id).lower() == query.exact_reference.lower()),
            ("Payment was not recorded in the current cycle", lambda item: query.time_scope is not QueryTimeScope.LATEST_CYCLE or item.payment_date == self.simulation_date),
            ("Payment amount is below the requested threshold", lambda item: query.min_exposure is None or item.amount >= query.min_exposure),
            ("Payment amount is above the requested threshold", lambda item: query.max_exposure is None or item.amount <= query.max_exposure),
        ]
        matched = self._filter_direct(rows, predicates, exclusions)
        matched.sort(key=lambda item: (item.payment_date, item.created_at, str(item.id)), reverse=query.descending)
        returned = matched if query.count_only or query.limit is None else matched[:query.limit]
        records = [self._payment_record(item, invoice_by_id[item.invoice_id], customer_by_id[invoice_by_id[item.invoice_id].customer_id]) for item in returned]
        return QueryExecution(records, len(rows), len(matched), exclusions, scope)

    @staticmethod
    def _filter_direct(rows, predicates, exclusions):
        remaining = rows
        for reason, predicate in predicates:
            before = len(remaining)
            remaining = [item for item in remaining if predicate(item)]
            if before > len(remaining):
                exclusions.append((reason, before - len(remaining)))
        return remaining

    def _invoice_sort_key(self, invoice: Invoice, query: StructuredQuery):
        if query.sort_by in {QuerySort.TOTAL_EXPOSURE, QuerySort.OVERDUE_EXPOSURE}:
            return invoice.outstanding_amount
        if query.sort_by is QuerySort.DAYS_OVERDUE:
            return (self.simulation_date - invoice.due_date).days
        return invoice.due_date

    def _invoice_record(self, invoice: Invoice, customer: Customer) -> DirectQueryRecord:
        days = max(0, (self.simulation_date - invoice.due_date).days) if invoice.due_date < self.simulation_date else 0
        return DirectQueryRecord(
            entity_type="INVOICE", entity_id=str(invoice.id), display_name=invoice.invoice_number,
            customer_id=str(customer.id), customer_name=customer.name, invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number, status=invoice.status.value,
            original_amount=invoice.original_amount, outstanding_amount=invoice.outstanding_amount,
            issue_date=invoice.issue_date, due_date=invoice.due_date, days_overdue=days,
        )

    @staticmethod
    def _payment_record(payment: Payment, invoice: Invoice, customer: Customer) -> DirectQueryRecord:
        return DirectQueryRecord(
            entity_type="PAYMENT", entity_id=str(payment.id), display_name=payment.reference or str(payment.id),
            customer_id=str(customer.id), customer_name=customer.name, invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number, amount=payment.amount, payment_date=payment.payment_date,
            reference=payment.reference,
        )

    def _case_scoped_customer_intelligence(self, case: RecoveryCase) -> IntelligenceResult:
        """Keep case identity while using the portfolio's authoritative current score."""
        cache = getattr(self, "_customer_intelligence", {})
        current = cache.get(str(case.customer_id))
        if current is None:
            current = evaluate_customer_intelligence(case.customer, self.simulation_date)
            cache[str(case.customer_id)] = current
            self._customer_intelligence = cache
        invoice_label = case.invoice.invoice_number if case.invoice is not None else "account-level case"
        return current.model_copy(update={
            "entity_type": "RECOVERY_CASE",
            "entity_id": str(case.id),
            "entity_name": f"{case.customer.name} / {invoice_label}",
        })

    def get_priority_customers(
        self,
        levels: list[PriorityLevel] | None = None,
        top_n: int | None = None,
    ) -> list[IntelligenceResult]:
        results = self.get_portfolio_intelligence().customers
        if levels:
            results = [item for item in results if item.level in levels]
        return results[:top_n] if top_n is not None else results

    def get_broken_promise_customers(self, top_n: int | None = None) -> list[IntelligenceResult]:
        broken_types = {SignalType.BROKEN_PROMISE, SignalType.MULTIPLE_BROKEN_PROMISES}
        results = [
            item for item in self.get_portfolio_intelligence().customers
            if any(signal.type in broken_types for signal in item.signals)
        ]
        return results[:top_n] if top_n is not None else results

    def get_overdue_customers(self, top_n: int | None = None) -> list[IntelligenceResult]:
        results = [item for item in self.get_portfolio_intelligence().customers if item.metrics.overdue_exposure > 0]
        return results[:top_n] if top_n is not None else results

    def query_customer_intelligence(self, query: StructuredQuery) -> list[IntelligenceResult]:
        return self.execute_customer_query(query).records

    def execute_customer_query(self, query: StructuredQuery) -> QueryExecution:
        """Execute independently composable predicates and retain factual diagnostics."""
        results = list(self.get_portfolio_intelligence().customers)
        latest_ids = self._latest_cycle_customer_ids() if query.time_scope is QueryTimeScope.LATEST_CYCLE else None
        changed_ids, held_ids = self._latest_cycle_decision_ids("CUSTOMER") if query.decision_changed is not None or query.decision_held is not None else (set(), set())
        contexts = []
        for result in results:
            customer = self.get_customer(result.entity_id)
            metrics = result.metrics
            partial = bool(customer and any(
                invoice.status is InvoiceStatus.PARTIALLY_PAID
                or Decimal("0") < invoice.outstanding_amount < invoice.original_amount
                for invoice in customer.invoices
            ))
            recent = metrics.days_since_last_payment is not None and metrics.days_since_last_payment < 30
            blocked = metrics.active_dispute_count > 0 or metrics.active_promise_count > 0
            monitoring = result.recommendation.action in {RecommendationAction.MONITOR, RecommendationAction.WAIT_FOR_PROMISE}
            actionable = metrics.overdue_exposure > 0 and not blocked and result.recommendation.action is not RecommendationAction.MONITOR
            contexts.append((result, partial, recent, blocked, monitoring, actionable, latest_ids is None or result.entity_id in latest_ids, result.entity_id in changed_ids, result.entity_id in held_ids))
        remaining, exclusions = self._apply_predicates(query, contexts)
        matched = [item[0] for item in remaining]
        matched.sort(key=lambda item: self._ranking_key(item, query))
        returned = matched if query.count_only or query.limit is None else matched[:query.limit]
        customers = self.customers()
        scope = InspectionScope(
            customers=len(customers), invoices=sum(len(customer.invoices) for customer in customers),
            promises=sum(len(customer.promises_to_pay) for customer in customers),
            active_disputes=sum(invoice.status is InvoiceStatus.DISPUTED and invoice.outstanding_amount > 0 for customer in customers for invoice in customer.invoices),
            recovery_cases=sum(len(customer.recovery_cases) for customer in customers), latest_cycle_events=self._latest_cycle_event_count(),
        )
        return QueryExecution(returned, len(results), len(matched), exclusions, scope)

    def query_recovery_candidates(self, query: StructuredQuery) -> list[CaseCandidate]:
        return self.execute_case_query(query).records

    def execute_case_query(self, query: StructuredQuery, customer_id: UUID | None = None) -> QueryExecution:
        """Apply the same structured semantics to real recovery-case recommendations."""
        latest_ids = self._latest_cycle_customer_ids() if query.time_scope is QueryTimeScope.LATEST_CYCLE else None
        changed_ids, held_ids = self._latest_cycle_decision_ids("RECOVERY_CASE") if query.decision_changed is not None or query.decision_held is not None else (set(), set())
        candidates = (
            self.get_recovery_candidates(customer_ids={str(customer_id)}, top_n=None)
            if customer_id else self.get_recovery_candidates(top_n=None)
        )
        contexts = []
        candidate_by_entity: dict[str, CaseCandidate] = {}
        for candidate in candidates:
            result = candidate.intelligence
            customer = candidate.case.customer
            partial = any(
                invoice.status is InvoiceStatus.PARTIALLY_PAID
                or Decimal("0") < invoice.outstanding_amount < invoice.original_amount
                for invoice in customer.invoices
            )
            recent = result.metrics.days_since_last_payment is not None and result.metrics.days_since_last_payment < 30
            blocked = bool(candidate.recommendation.blockers)
            monitoring = candidate.recommendation.recommended_action is RecommendedAction.MONITOR_ACTIVE_PROMISE
            actionable = not blocked and candidate.recommendation.recommended_action not in {
                RecommendedAction.NO_ACTION_REQUIRED, RecommendedAction.MONITOR_ACTIVE_PROMISE,
                RecommendedAction.HOLD_FOR_DISPUTE,
            }
            # Stored workflow priority is historical workflow state. It must not
            # promote fresh intelligence into a different current risk band.
            contexts.append((result, partial, recent, blocked, monitoring, actionable, latest_ids is None or str(candidate.case.customer_id) in latest_ids, result.entity_id in changed_ids, result.entity_id in held_ids))
            candidate_by_entity[result.entity_id] = candidate
        remaining, exclusions = self._apply_predicates(query, contexts)
        matched = [candidate_by_entity[item[0].entity_id] for item in remaining]
        matched.sort(key=lambda item: self._ranking_key(item.intelligence, query))
        returned = matched if query.count_only or query.limit is None else matched[:query.limit]
        customers = {str(candidate.case.customer_id): candidate.case.customer for candidate in candidates}
        scope = InspectionScope(
            customers=len(customers), invoices=sum(len(customer.invoices) for customer in customers.values()),
            promises=sum(len(customer.promises_to_pay) for customer in customers.values()),
            active_disputes=sum(invoice.status is InvoiceStatus.DISPUTED and invoice.outstanding_amount > 0 for customer in customers.values() for invoice in customer.invoices),
            recovery_cases=len(candidates), latest_cycle_events=self._latest_cycle_event_count(),
        )
        return QueryExecution(returned, len(candidates), len(matched), exclusions, scope)

    def latest_cycle_evidence(self, results: list[IntelligenceResult]) -> LatestCycleEvidence | None:
        """Return latest-cycle evidence only when it belongs to the analyzed entities."""
        if not results:
            return None
        latest_cycle = self.db.scalar(select(func.max(SimulationEvent.cycle)))
        if latest_cycle is None:
            return None
        customer_ids = {item.entity_id for item in results if item.entity_type == "CUSTOMER"}
        case_ids = {item.entity_id for item in results if item.entity_type == "RECOVERY_CASE"}
        invoice_ids: set[str] = set()
        for case_id in case_ids:
            case = self.get_case(case_id)
            if case is not None and case.invoice_id is not None:
                invoice_ids.add(str(case.invoice_id))
        all_events = list(self.db.scalars(select(SimulationEvent).where(SimulationEvent.cycle == latest_cycle)))
        events = [event for event in all_events if (
            (customer_ids and str(event.customer_id) in customer_ids)
            or (case_ids and str(event.recovery_case_id) in case_ids)
            or (invoice_ids and str(event.invoice_id) in invoice_ids)
        )]
        audits = list(self.db.scalars(select(AuditEvent).where(
            AuditEvent.event_type.in_({"SIMULATION_INTELLIGENCE_SUMMARY", "SIMULATION_INTELLIGENCE_TRANSITION"})
        ).order_by(AuditEvent.occurred_at)))
        relevant = []
        for audit in audits:
            payload = audit.payload or {}
            if payload.get("cycle") != latest_cycle or audit.event_type != "SIMULATION_INTELLIGENCE_TRANSITION":
                continue
            entity_id = str(payload.get("entity_id", ""))
            entity_type = payload.get("entity_type")
            if (entity_type == "CUSTOMER" and entity_id in customer_ids) or (entity_type == "RECOVERY_CASE" and entity_id in case_ids):
                relevant.append(audit)
        if not events and not relevant:
            return None
        observations = []
        for audit in relevant:
            if audit.event_type != "SIMULATION_INTELLIGENCE_TRANSITION":
                continue
            payload = audit.payload or {}
            name = payload.get("entity_name", "Operational record")
            previous = payload.get("previous_recommendation")
            current = payload.get("current_recommendation")
            if "RECOMMENDATION_CHANGED" in payload.get("classifications", []):
                observations.append(f"{name}: recommendation changed from {previous or 'unavailable'} to {current}.")
            elif payload.get("material"):
                observations.append(f"{name}: score changed from {payload.get('previous_score')} to {payload.get('current_score')}; the recommendation remained {current}.")
            else:
                observations.append(f"{name}: event observed; no material decision change.")
        scoped_transitions = [audit.payload or {} for audit in relevant]
        return LatestCycleEvidence(
            cycle=latest_cycle, event_count=len(events),
            customers_affected=len({str(event.customer_id) for event in events if event.customer_id}),
            material_customers=len({payload.get("entity_id") for payload in scoped_transitions if payload.get("material")}),
            recommendations_changed=sum("RECOMMENDATION_CHANGED" in payload.get("classifications", []) for payload in scoped_transitions),
            recommendations_unchanged=sum("RECOMMENDATION_CHANGED" not in payload.get("classifications", []) for payload in scoped_transitions),
            observations=observations[:6],
        )

    def _latest_cycle_customer_ids(self) -> set[str]:
        latest_cycle = self.db.scalar(select(func.max(SimulationEvent.cycle)))
        if latest_cycle is None:
            return set()
        return {
            str(value) for value in self.db.scalars(
                select(SimulationEvent.customer_id).where(
                    SimulationEvent.cycle == latest_cycle,
                    SimulationEvent.customer_id.is_not(None),
                ).distinct()
            ) if value is not None
        }

    def _latest_cycle_event_count(self) -> int:
        latest_cycle = self.db.scalar(select(func.max(SimulationEvent.cycle)))
        if latest_cycle is None:
            return 0
        return int(self.db.scalar(select(func.count(SimulationEvent.id)).where(SimulationEvent.cycle == latest_cycle)) or 0)

    def _latest_cycle_decision_ids(self, entity_type: str) -> tuple[set[str], set[str]]:
        """Separate changed decisions from decisions retained after a latest-cycle fact event."""
        latest_cycle = self.db.scalar(select(func.max(SimulationEvent.cycle)))
        if latest_cycle is None:
            return set(), set()
        changed: set[str] = set()
        held: set[str] = set()
        audits = self.db.scalars(select(AuditEvent).where(AuditEvent.event_type == "SIMULATION_INTELLIGENCE_TRANSITION"))
        for audit in audits:
            payload = audit.payload or {}
            if payload.get("cycle") != latest_cycle or payload.get("entity_type") != entity_type:
                continue
            entity_id = str(payload.get("entity_id", ""))
            if not entity_id:
                continue
            if "RECOMMENDATION_CHANGED" in payload.get("classifications", []):
                changed.add(entity_id)
            elif payload.get("previous_recommendation") is not None:
                held.add(entity_id)
        return changed, held

    @classmethod
    def _apply_predicates(cls, query: StructuredQuery, contexts: list[tuple]) -> tuple[list[tuple], list[tuple[str, int]]]:
        predicates: list[tuple[str, Any]] = []
        if query.time_scope is QueryTimeScope.LATEST_CYCLE:
            predicates.append(("Not affected in the latest cycle", lambda item: item[6]))
        if query.risk_levels:
            predicates.append(("Outside requested risk level", lambda item: item[0].level in query.risk_levels))
        boolean_fields = (
            (query.overdue, "overdue exposure", lambda item: item[0].metrics.overdue_exposure > 0),
            (query.broken_promise, "broken promise", lambda item: item[0].metrics.broken_promise_count > 0),
            (query.active_promise, "active promise", lambda item: item[0].metrics.active_promise_count > 0),
            (query.active_dispute, "active dispute", lambda item: item[0].metrics.active_dispute_count > 0),
            (query.partial_payment, "partial payment", lambda item: item[1]),
            (query.recent_payment, "recent payment", lambda item: item[2]),
            (query.actionable, "actionable recovery state", lambda item: item[5]),
            (query.blocked, "blocked recovery state", lambda item: item[3]),
            (query.monitoring, "monitoring state", lambda item: item[4]),
            (query.decision_changed, "latest-cycle decision changed", lambda item: item[7]),
            (query.decision_held, "latest-cycle decision held", lambda item: item[8]),
        )
        for expected, label, predicate in boolean_fields:
            if expected is not None:
                predicates.append((f"Did not satisfy {label} = {str(expected).lower()}", lambda item, test=predicate, wanted=expected: test(item) is wanted))
        if query.min_days_overdue is not None:
            predicates.append((f"Below {query.min_days_overdue} days overdue", lambda item: item[0].metrics.max_days_overdue >= query.min_days_overdue))
        if query.max_days_overdue is not None:
            predicates.append((f"Above {query.max_days_overdue} days overdue", lambda item: item[0].metrics.max_days_overdue <= query.max_days_overdue))
        if query.min_score is not None:
            predicates.append((f"Score below {query.min_score}", lambda item: item[0].score >= query.min_score))
        if query.max_score is not None:
            predicates.append((f"Score above {query.max_score}", lambda item: item[0].score <= query.max_score))
        if query.min_exposure is not None:
            predicates.append((f"Exposure below {query.min_exposure}", lambda item: item[0].metrics.overdue_exposure >= query.min_exposure))
        if query.max_exposure is not None:
            predicates.append((f"Exposure above {query.max_exposure}", lambda item: item[0].metrics.overdue_exposure <= query.max_exposure))
        remaining = list(contexts)
        exclusions = []
        for label, predicate in predicates:
            before = len(remaining)
            remaining = [item for item in remaining if predicate(item)]
            if before > len(remaining):
                exclusions.append((label, before - len(remaining)))
        return remaining, exclusions

    @staticmethod
    def _matches(query: StructuredQuery, result: IntelligenceResult, *, partial: bool, recent: bool, blocked: bool, monitoring: bool, actionable: bool, decision_changed: bool = False, decision_held: bool = False) -> bool:
        metrics = result.metrics
        checks = (
            (query.overdue, metrics.overdue_exposure > 0),
            (query.broken_promise, metrics.broken_promise_count > 0),
            (query.active_promise, metrics.active_promise_count > 0),
            (query.active_dispute, metrics.active_dispute_count > 0),
            (query.partial_payment, partial),
            (query.recent_payment, recent),
            (query.actionable, actionable),
            (query.blocked, blocked),
            (query.monitoring, monitoring),
            (query.decision_changed, decision_changed),
            (query.decision_held, decision_held),
        )
        return (
            (not query.risk_levels or result.level in query.risk_levels)
            and (query.min_days_overdue is None or metrics.max_days_overdue >= query.min_days_overdue)
            and (query.max_days_overdue is None or metrics.max_days_overdue <= query.max_days_overdue)
            and (query.min_score is None or result.score >= query.min_score)
            and (query.max_score is None or result.score <= query.max_score)
            and (query.min_exposure is None or metrics.overdue_exposure >= query.min_exposure)
            and (query.max_exposure is None or metrics.overdue_exposure <= query.max_exposure)
            and all(expected is None or actual is expected for expected, actual in checks)
        )

    @staticmethod
    def _sort_key(result: IntelligenceResult, sort_by: QuerySort):
        if sort_by is QuerySort.TOTAL_EXPOSURE:
            return result.metrics.total_outstanding_amount
        if sort_by is QuerySort.OVERDUE_EXPOSURE:
            return result.metrics.overdue_exposure
        if sort_by is QuerySort.DAYS_OVERDUE:
            return result.metrics.max_days_overdue
        if sort_by is QuerySort.LAST_PAYMENT:
            return result.metrics.days_since_last_payment if result.metrics.days_since_last_payment is not None else 10**9
        return result.score

    @classmethod
    def _ranking_key(cls, result: IntelligenceResult, query: StructuredQuery):
        """One deterministic comparator shared by customer and case queries."""
        primary = cls._sort_key(result, query.sort_by)
        direction = Decimal("-1") if query.descending else Decimal("1")
        return (
            Decimal(primary) * direction,
            -result.raw_score,
            -result.metrics.overdue_exposure,
            -result.metrics.max_days_overdue,
            result.entity_id,
        )

    @staticmethod
    def ranking_policy(query: StructuredQuery) -> list[str]:
        primary = {
            QuerySort.RISK_SCORE: "Displayed intelligence score",
            QuerySort.TOTAL_EXPOSURE: "Total outstanding exposure",
            QuerySort.OVERDUE_EXPOSURE: "Overdue exposure",
            QuerySort.DAYS_OVERDUE: "Oldest overdue age",
            QuerySort.LAST_PAYMENT: "Payment recency",
        }[query.sort_by]
        return [
            f"{primary} ({'highest first' if query.descending else 'lowest first'})",
            "Raw intelligence score (highest first)",
            "Overdue exposure (highest first)",
            "Oldest overdue age (highest first)",
            "Stable entity identifier",
        ]

    def get_recovery_candidates(
        self,
        levels: list[PriorityLevel] | None = None,
        customer_ids: set[str] | None = None,
        top_n: int | None = None,
    ) -> list[CaseCandidate]:
        candidates: list[CaseCandidate] = []
        for case in self.cases():
            if customer_ids is not None and str(case.customer_id) not in customer_ids:
                continue
            intelligence = self._case_scoped_customer_intelligence(case)
            if levels and intelligence.level not in levels:
                continue
            recommendation = recommend_case(case, self.simulation_date)
            candidates.append(CaseCandidate(
                case=case,
                intelligence=intelligence,
                recommendation=recommendation,
                risk_level=intelligence.level,
            ))
        candidates.sort(
            key=lambda item: (
                -item.intelligence.score,
                -item.intelligence.metrics.overdue_exposure,
                str(item.case.id),
            )
        )
        return candidates[:top_n] if top_n is not None else candidates
