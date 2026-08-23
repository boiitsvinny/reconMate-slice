"""Read-only inspection endpoints for the seeded receivables portfolio."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.domain import Communication, Customer, Invoice, Payment, PromiseToPay, RecoveryCase, SimulationState
from app.seed.portfolio import portfolio_summary

router = APIRouter(tags=["portfolio"])


class CustomerItem(BaseModel):
    id: UUID
    name: str
    account_reference: str
    segment: str | None
    is_strategic_account: bool
    invoice_count: int
    outstanding_amount: Decimal


class InvoiceItem(BaseModel):
    id: UUID
    invoice_number: str
    issue_date: date
    due_date: date
    original_amount: Decimal
    outstanding_amount: Decimal
    status: str
    customer_id: UUID


class PaymentItem(BaseModel):
    id: UUID
    amount: Decimal
    payment_date: date
    reference: str | None


class PromiseItem(BaseModel):
    id: UUID
    invoice_id: UUID | None
    promised_amount: Decimal
    promised_date: date
    status: str
    confidence: Decimal | None


class CommunicationItem(BaseModel):
    id: UUID
    direction: str
    channel: str
    content: str
    occurred_at: datetime


class RecoveryCaseItem(BaseModel):
    id: UUID
    invoice_id: UUID | None
    current_state: str
    priority: str
    opened_at: datetime
    closed_at: datetime | None


class CustomerDetail(BaseModel):
    id: UUID
    name: str
    account_reference: str
    segment: str | None
    is_strategic_account: bool
    invoices: list[InvoiceItem]
    promises_to_pay: list[PromiseItem]
    communications: list[CommunicationItem]
    recovery_cases: list[RecoveryCaseItem]


class PortfolioSummary(BaseModel):
    simulation_date: date | None
    total_customers: int
    total_invoices: int
    open_invoices: int
    overdue_invoices: int
    total_outstanding_amount: Decimal
    total_overdue_amount: Decimal
    total_recovered_amount: Decimal
    total_payments: int
    total_promises: int
    broken_promises: int
    active_disputes: int
    recovery_cases: int


def _invoice_item(invoice: Invoice) -> InvoiceItem:
    return InvoiceItem(id=invoice.id, invoice_number=invoice.invoice_number, issue_date=invoice.issue_date,
                       due_date=invoice.due_date, original_amount=invoice.original_amount,
                       outstanding_amount=invoice.outstanding_amount, status=invoice.status.value,
                       customer_id=invoice.customer_id)


@router.get("/customers", response_model=list[CustomerItem], summary="List portfolio customers")
def list_customers(db: Session = Depends(get_db)) -> list[CustomerItem]:
    rows = db.execute(
        select(Customer, func.count(Invoice.id), func.coalesce(func.sum(Invoice.outstanding_amount), 0))
        .outerjoin(Invoice)
        .group_by(Customer.id)
        .order_by(Customer.account_reference)
    ).all()
    return [CustomerItem(id=customer.id, name=customer.name, account_reference=customer.account_reference,
                         segment=customer.segment, is_strategic_account=customer.is_strategic_account,
                         invoice_count=count, outstanding_amount=outstanding) for customer, count, outstanding in rows]


@router.get("/customers/{customer_id}", response_model=CustomerDetail, summary="Inspect a customer history")
def get_customer(customer_id: UUID, db: Session = Depends(get_db)) -> CustomerDetail:
    customer = db.scalar(
        select(Customer).where(Customer.id == customer_id).options(
            selectinload(Customer.invoices), selectinload(Customer.promises_to_pay),
            selectinload(Customer.communications), selectinload(Customer.recovery_cases),
        )
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return CustomerDetail(
        id=customer.id, name=customer.name, account_reference=customer.account_reference,
        segment=customer.segment, is_strategic_account=customer.is_strategic_account,
        invoices=[_invoice_item(invoice) for invoice in sorted(customer.invoices, key=lambda item: item.due_date)],
        promises_to_pay=[PromiseItem(id=item.id, invoice_id=item.invoice_id, promised_amount=item.promised_amount,
                                     promised_date=item.promised_date, status=item.status.value, confidence=item.confidence)
                         for item in sorted(customer.promises_to_pay, key=lambda item: item.promised_date)],
        communications=[CommunicationItem(id=item.id, direction=item.direction.value, channel=item.channel.value,
                                          content=item.content, occurred_at=item.occurred_at)
                        for item in sorted(customer.communications, key=lambda item: item.occurred_at)],
        recovery_cases=[RecoveryCaseItem(id=item.id, invoice_id=item.invoice_id, current_state=item.current_state.value,
                                         priority=item.priority.value, opened_at=item.opened_at, closed_at=item.closed_at)
                        for item in customer.recovery_cases],
    )


@router.get("/invoices", response_model=list[InvoiceItem], summary="List invoices")
def list_invoices(customer_id: UUID | None = Query(default=None), db: Session = Depends(get_db)) -> list[InvoiceItem]:
    query = select(Invoice).order_by(Invoice.due_date, Invoice.invoice_number)
    if customer_id is not None:
        query = query.where(Invoice.customer_id == customer_id)
    return [_invoice_item(invoice) for invoice in db.scalars(query)]


@router.get("/portfolio/summary", response_model=PortfolioSummary, summary="Return factual portfolio metrics")
def get_portfolio_summary(db: Session = Depends(get_db)) -> PortfolioSummary:
    metrics = portfolio_summary(db)
    simulation_date = db.scalar(select(SimulationState.simulation_date).where(SimulationState.name == "default"))
    total_original = db.scalar(select(func.coalesce(func.sum(Invoice.original_amount), 0))) or Decimal("0")
    return PortfolioSummary(
        simulation_date=simulation_date, total_customers=int(metrics["customers"]), total_invoices=int(metrics["invoices"]),
        open_invoices=int(metrics["open_invoices"]), overdue_invoices=int(metrics["overdue_invoices"]),
        total_outstanding_amount=Decimal(metrics["outstanding_amount"]), total_overdue_amount=Decimal(metrics["overdue_amount"]),
        total_recovered_amount=total_original - Decimal(metrics["outstanding_amount"]), total_payments=int(metrics["payments"]),
        total_promises=int(metrics["promises"]), broken_promises=int(metrics["broken_promises"]),
        active_disputes=int(metrics["active_disputes"]), recovery_cases=int(metrics["recovery_cases"]),
    )
