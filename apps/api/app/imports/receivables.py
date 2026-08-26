"""Validate and persist a narrow CSV receivables import using existing domain models."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.domain import (
    AuditEvent, Customer, Invoice, InvoiceStatus, RecoveryCase, RecoveryPriority, RecoveryState,
)
from app.recovery.engine import synchronize_recovery_states

REQUIRED_COLUMNS = (
    "customer_reference", "customer_name", "invoice_number", "original_amount",
    "outstanding_amount", "issue_date", "due_date",
)
OPTIONAL_COLUMNS = ("currency", "status")
MAX_CSV_BYTES = 2_000_000


class ReceivableCsvRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(min_length=1, max_length=MAX_CSV_BYTES)


class ReceivableRowPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_number: int
    customer_reference: str
    customer_name: str
    invoice_number: str
    original_amount: Decimal | None
    outstanding_amount: Decimal | None
    issue_date: date | None
    due_date: date | None
    currency: str
    status: str | None
    validation_status: str
    errors: list[str]


class ReceivableImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows_detected: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    total_original_amount: Decimal
    total_outstanding_amount: Decimal
    required_columns: list[str]
    optional_columns: list[str]
    file_errors: list[str]
    rows: list[ReceivableRowPreview]


class ReceivableImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customers_created: int
    invoices_created: int
    recovery_cases_created: int
    duplicates_skipped: int
    total_outstanding_imported: Decimal
    evaluation_date: date
    message: str


@dataclass(frozen=True)
class ValidReceivable:
    customer_reference: str
    customer_name: str
    invoice_number: str
    original_amount: Decimal
    outstanding_amount: Decimal
    issue_date: date
    due_date: date
    status: InvoiceStatus


@dataclass(frozen=True)
class ParsedReceivables:
    preview: ReceivableImportPreview
    valid_records: list[ValidReceivable]


def portfolio_import_context(db: Session) -> tuple[list[Customer], date]:
    from app.models.domain import SimulationState

    customers = list(db.scalars(select(Customer).options(selectinload(Customer.invoices))))
    operating_date = db.scalar(select(SimulationState.simulation_date).where(SimulationState.name == "default"))
    return customers, operating_date or date.today()


def parse_receivables_csv(csv_text: str, operating_date: date, customers: list[Customer]) -> ParsedReceivables:
    file_errors: list[str] = []
    previews: list[ReceivableRowPreview] = []
    valid_records: list[ValidReceivable] = []
    customer_names = {customer.account_reference.casefold(): customer.name for customer in customers}
    existing_keys = {
        (customer.account_reference.casefold(), invoice.invoice_number.casefold())
        for customer in customers for invoice in customer.invoices
    }
    seen: dict[tuple[str, str], ValidReceivable] = {}
    seen_customer_names: dict[str, str] = {}
    text = csv_text.lstrip("\ufeff")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = [str(value).strip().lower() for value in (reader.fieldnames or [])]
        if len(headers) != len(set(headers)):
            file_errors.append("CSV headers must be unique.")
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            file_errors.append("Missing required columns: " + ", ".join(missing) + ".")
        if file_errors:
            return ParsedReceivables(_preview(previews, valid_records, file_errors), valid_records)

        for row_number, source in enumerate(reader, start=2):
            row = {str(key).strip().lower(): (value or "").strip() for key, value in source.items() if key is not None}
            preview, record = _validate_row(row_number, row, operating_date, customer_names)
            if record is not None:
                reference_key = record.customer_reference.casefold()
                previous_name = seen_customer_names.get(reference_key)
                if previous_name is not None and previous_name.casefold() != record.customer_name.casefold():
                    preview = preview.model_copy(update={"validation_status": "INVALID", "errors": ["Customer reference uses conflicting customer names in this file."]})
                    record = None
                else:
                    seen_customer_names[reference_key] = record.customer_name
            if record is not None:
                key = (record.customer_reference.casefold(), record.invoice_number.casefold())
                previous = seen.get(key)
                if key in existing_keys:
                    preview = preview.model_copy(update={"validation_status": "DUPLICATE", "errors": ["Invoice already exists for this customer and will be skipped."]})
                    record = None
                elif previous is not None:
                    if previous == record:
                        preview = preview.model_copy(update={"validation_status": "DUPLICATE", "errors": ["Duplicate invoice row in this file; only the first row will be imported."]})
                    else:
                        preview = preview.model_copy(update={"validation_status": "INVALID", "errors": ["Conflicting rows use the same customer reference and invoice number."]})
                    record = None
                else:
                    seen[key] = record
            previews.append(preview)
            if record is not None:
                valid_records.append(record)
    except (csv.Error, UnicodeError) as exc:
        file_errors.append(f"Malformed CSV: {exc}.")
    return ParsedReceivables(_preview(previews, valid_records, file_errors), valid_records)


def _validate_row(
    row_number: int,
    row: dict[str, str],
    operating_date: date,
    customer_names: dict[str, str],
) -> tuple[ReceivableRowPreview, ValidReceivable | None]:
    errors: list[str] = []
    reference = row.get("customer_reference", "").strip()
    customer_name = row.get("customer_name", "").strip()
    invoice_number = row.get("invoice_number", "").strip()
    if not reference:
        errors.append("Missing customer reference.")
    elif len(reference) > 100:
        errors.append("Customer reference exceeds 100 characters.")
    if not customer_name:
        errors.append("Missing customer name.")
    elif len(customer_name) > 255:
        errors.append("Customer name exceeds 255 characters.")
    if not invoice_number:
        errors.append("Missing invoice number.")
    elif len(invoice_number) > 100:
        errors.append("Invoice number exceeds 100 characters.")
    known_name = customer_names.get(reference.casefold()) if reference else None
    if known_name and known_name.casefold() != customer_name.casefold():
        errors.append(f"Customer reference already belongs to {known_name}.")

    original = _decimal(row.get("original_amount", ""), "original amount", errors)
    outstanding = _decimal(row.get("outstanding_amount", ""), "outstanding amount", errors)
    issue_date = _date(row.get("issue_date", ""), "invoice date", errors)
    due_date = _date(row.get("due_date", ""), "due date", errors)
    if original is not None and original <= 0:
        errors.append("Original amount must be greater than zero.")
    if outstanding is not None and outstanding < 0:
        errors.append("Outstanding amount cannot be negative.")
    if original is not None and outstanding is not None and outstanding > original:
        errors.append("Outstanding amount cannot exceed original amount.")
    if issue_date and due_date and due_date < issue_date:
        errors.append("Due date cannot be before invoice date.")

    currency = (row.get("currency") or "INR").upper()
    if currency != "INR":
        errors.append("Only INR is supported by the current portfolio model.")
    status_value = (row.get("status") or "").upper().replace(" ", "_")
    status = None
    if status_value:
        try:
            status = InvoiceStatus(status_value)
        except ValueError:
            errors.append("Unsupported invoice status.")
    if not errors and original is not None and outstanding is not None and issue_date and due_date:
        status = status or _derived_status(original, outstanding, due_date, operating_date)
        if status is InvoiceStatus.PAID and outstanding != 0:
            errors.append("Paid invoices must have zero outstanding amount.")
        if status in {InvoiceStatus.OPEN, InvoiceStatus.OVERDUE, InvoiceStatus.DISPUTED, InvoiceStatus.PARTIALLY_PAID} and outstanding <= 0:
            errors.append(f"{status.value.replace('_', ' ').title()} invoices must have a positive outstanding amount.")
        if status is InvoiceStatus.PARTIALLY_PAID and not Decimal("0") < outstanding < original:
            errors.append("Partially paid invoices require outstanding amount below original amount and above zero.")
        if status is InvoiceStatus.OVERDUE and due_date >= operating_date:
            errors.append("An overdue invoice must have a due date before the current operating date.")

    record = None
    if not errors and original is not None and outstanding is not None and issue_date and due_date and status:
        record = ValidReceivable(reference, customer_name, invoice_number, original, outstanding, issue_date, due_date, status)
    preview = ReceivableRowPreview(
        row_number=row_number, customer_reference=reference, customer_name=customer_name,
        invoice_number=invoice_number, original_amount=original, outstanding_amount=outstanding,
        issue_date=issue_date, due_date=due_date, currency=currency, status=status.value if status else status_value or None,
        validation_status="VALID" if record else "INVALID", errors=errors,
    )
    return preview, record


def _decimal(value: str, label: str, errors: list[str]) -> Decimal | None:
    if not value:
        errors.append(f"Missing {label}.")
        return None
    try:
        parsed = Decimal(value.replace(",", "")).quantize(Decimal("0.01"))
        if not parsed.is_finite():
            raise InvalidOperation
        return parsed
    except InvalidOperation:
        errors.append(f"Invalid {label}.")
        return None


def _date(value: str, label: str, errors: list[str]) -> date | None:
    if not value:
        errors.append(f"Missing {label}.")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"Invalid {label}; use YYYY-MM-DD.")
        return None


def _derived_status(original: Decimal, outstanding: Decimal, due_date: date, operating_date: date) -> InvoiceStatus:
    if outstanding == 0:
        return InvoiceStatus.PAID
    if outstanding < original:
        return InvoiceStatus.PARTIALLY_PAID
    if due_date < operating_date:
        return InvoiceStatus.OVERDUE
    return InvoiceStatus.OPEN


def _preview(
    rows: list[ReceivableRowPreview],
    records: list[ValidReceivable],
    file_errors: list[str],
) -> ReceivableImportPreview:
    return ReceivableImportPreview(
        rows_detected=len(rows), valid_rows=sum(row.validation_status == "VALID" for row in rows),
        invalid_rows=sum(row.validation_status == "INVALID" for row in rows),
        duplicate_rows=sum(row.validation_status == "DUPLICATE" for row in rows),
        total_original_amount=sum((record.original_amount for record in records), Decimal("0")),
        total_outstanding_amount=sum((record.outstanding_amount for record in records), Decimal("0")),
        required_columns=list(REQUIRED_COLUMNS), optional_columns=list(OPTIONAL_COLUMNS),
        file_errors=file_errors, rows=rows,
    )


def persist_receivables(
    db: Session,
    parsed: ParsedReceivables,
    customers: list[Customer],
    operating_date: date,
) -> ReceivableImportResult:
    if parsed.preview.file_errors or parsed.preview.invalid_rows:
        raise ValueError("The CSV contains validation errors and was not imported.")
    customer_map = {customer.account_reference.casefold(): customer for customer in customers}
    customers_created = 0
    invoices: list[Invoice] = []
    cases: list[RecoveryCase] = []
    occurred_at = datetime.now(UTC)
    try:
        for record in parsed.valid_records:
            customer = customer_map.get(record.customer_reference.casefold())
            if customer is None:
                customer = Customer(
                    name=record.customer_name, account_reference=record.customer_reference,
                    segment="Imported portfolio", is_strategic_account=False,
                )
                db.add(customer)
                customer_map[record.customer_reference.casefold()] = customer
                customers_created += 1
            invoice = Invoice(
                customer=customer, invoice_number=record.invoice_number,
                issue_date=record.issue_date, due_date=record.due_date,
                original_amount=record.original_amount, outstanding_amount=record.outstanding_amount,
                status=record.status,
            )
            db.add(invoice)
            invoices.append(invoice)
            if record.outstanding_amount > 0 and record.status not in {InvoiceStatus.CANCELLED, InvoiceStatus.WRITTEN_OFF}:
                recovery_case = RecoveryCase(
                    customer=customer, invoice=invoice, current_state=RecoveryState.NEW,
                    priority=RecoveryPriority.NORMAL, opened_at=occurred_at, updated_at=occurred_at,
                )
                db.add(recovery_case)
                cases.append(recovery_case)
        db.flush()
        for invoice in invoices:
            db.add(AuditEvent(
                entity_type="Invoice", entity_id=invoice.id, event_type="RECEIVABLE_IMPORTED",
                actor_type="operator", actor_id="csv-import",
                payload={"source": "CSV Import", "invoice_number": invoice.invoice_number},
                occurred_at=occurred_at,
            ))
        synchronize_recovery_states(db, operating_date)
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("The import conflicts with an existing customer or invoice identifier.") from exc
    return ReceivableImportResult(
        customers_created=customers_created, invoices_created=len(invoices),
        recovery_cases_created=len(cases), duplicates_skipped=parsed.preview.duplicate_rows,
        total_outstanding_imported=sum((invoice.outstanding_amount for invoice in invoices), Decimal("0")),
        evaluation_date=operating_date,
        message="Receivables were persisted. Existing intelligence and recommendation endpoints now evaluate the imported facts.",
    )
