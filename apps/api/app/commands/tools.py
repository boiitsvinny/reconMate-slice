"""Centralized, read-only data tools used by command planning."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.intelligence.operational_schemas import IntelligenceResult, PortfolioIntelligence, PriorityLevel, SignalType
from app.intelligence.operational_service import (
    evaluate_case_intelligence,
    evaluate_customer_intelligence,
    evaluate_portfolio_intelligence,
)
from app.models.domain import (
    Communication,
    Customer,
    Invoice,
    PromiseToPay,
    RecoveryCase,
    RecoveryPriority,
    SimulationState,
)
from app.recommendations.schemas import RecoveryRecommendation
from app.recommendations.service import recommend_case


class CommandDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaseCandidate:
    case: RecoveryCase
    intelligence: IntelligenceResult
    recommendation: RecoveryRecommendation
    risk_level: PriorityLevel


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


_STORED_PRIORITY_LEVEL = {
    RecoveryPriority.LOW: PriorityLevel.LOW,
    RecoveryPriority.NORMAL: PriorityLevel.MEDIUM,
    RecoveryPriority.HIGH: PriorityLevel.HIGH,
    RecoveryPriority.CRITICAL: PriorityLevel.CRITICAL,
}


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
        return self._portfolio

    def get_customer_intelligence(self, customer_id: UUID) -> IntelligenceResult | None:
        customer = next((item for item in self.customers() if item.id == customer_id), None)
        return evaluate_customer_intelligence(customer, self.simulation_date) if customer is not None else None

    def get_customer(self, customer_id: UUID | str) -> Customer | None:
        return next((item for item in self.customers() if str(item.id) == str(customer_id)), None)

    def get_case_intelligence(self, case_id: UUID) -> IntelligenceResult | None:
        case = self.get_case(case_id)
        return evaluate_case_intelligence(case, self.simulation_date) if case is not None else None

    def get_case(self, case_id: UUID | str) -> RecoveryCase | None:
        return next((item for item in self.cases() if str(item.id) == str(case_id)), None)

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
            intelligence = evaluate_case_intelligence(case, self.simulation_date)
            effective_level = max(
                (intelligence.level, _STORED_PRIORITY_LEVEL[case.priority]),
                key=lambda level: list(PriorityLevel).index(level),
            )
            if levels and effective_level not in levels:
                continue
            recommendation = recommend_case(case, self.simulation_date)
            candidates.append(CaseCandidate(
                case=case,
                intelligence=intelligence,
                recommendation=recommendation,
                risk_level=effective_level,
            ))
        candidates.sort(
            key=lambda item: (
                -max(item.intelligence.score, _priority_floor(item.case.priority)),
                -item.intelligence.metrics.overdue_exposure,
                str(item.case.id),
            )
        )
        return candidates[:top_n] if top_n is not None else candidates


def _priority_floor(priority: RecoveryPriority) -> int:
    return {
        RecoveryPriority.LOW: 0,
        RecoveryPriority.NORMAL: 20,
        RecoveryPriority.HIGH: 45,
        RecoveryPriority.CRITICAL: 80,
    }[priority]
