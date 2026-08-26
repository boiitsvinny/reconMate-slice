from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.imports import receivables
from app.imports.receivables import parse_receivables_csv, persist_receivables
from app.api.routes.portfolio import _invoice_item
from app.intelligence.operational_service import evaluate_customer_intelligence
from app.recovery.engine import evaluate_invoice
from app.models.domain import (
    AuditEvent,
    Customer,
    Invoice,
    InvoiceStatus,
    RecoveryCase,
    RecoveryPriority,
    RecoveryState,
)


TODAY = date(2026, 8, 26)
HEADER = "customer_reference,customer_name,invoice_number,original_amount,outstanding_amount,issue_date,due_date,currency,status"


def csv(*rows: str) -> str:
    return "\n".join((HEADER, *rows))


def test_valid_csv_is_previewed_without_mutation() -> None:
    parsed = parse_receivables_csv(csv(
        "EXT-001,External Trading,INV-001,125000.00,100000.00,2026-06-01,2026-07-01,INR,PARTIALLY_PAID",
    ), TODAY, [])
    assert parsed.preview.rows_detected == 1
    assert parsed.preview.valid_rows == 1
    assert parsed.preview.invalid_rows == 0
    assert parsed.preview.total_outstanding_amount == Decimal("100000.00")
    assert parsed.valid_records[0].status is InvoiceStatus.PARTIALLY_PAID


@pytest.mark.parametrize(("row", "message"), [
    ("EXT-001,,INV-001,100,100,2026-06-01,2026-07-01,INR,OVERDUE", "Missing customer name"),
    ("EXT-001,External Trading,,100,100,2026-06-01,2026-07-01,INR,OVERDUE", "Missing invoice number"),
    ("EXT-001,External Trading,INV-001,bad,100,2026-06-01,2026-07-01,INR,OVERDUE", "Invalid original amount"),
    ("EXT-001,External Trading,INV-001,100,101,2026-06-01,2026-07-01,INR,OVERDUE", "cannot exceed original"),
    ("EXT-001,External Trading,INV-001,100,100,07/01/2026,2026-07-01,INR,OVERDUE", "Invalid invoice date"),
    ("EXT-001,External Trading,INV-001,100,100,2026-06-01,2026-07-01,USD,OVERDUE", "Only INR"),
])
def test_invalid_financial_and_identity_rows_fail_safely(row: str, message: str) -> None:
    parsed = parse_receivables_csv(csv(row), TODAY, [])
    assert parsed.preview.invalid_rows == 1
    assert any(message in error for error in parsed.preview.rows[0].errors)
    assert parsed.valid_records == []


def test_existing_and_repeated_invoices_are_reported_as_duplicates() -> None:
    customer = Customer(name="External Trading", account_reference="EXT-001")
    customer.invoices.append(Invoice(
        invoice_number="INV-001", issue_date=date(2026, 6, 1), due_date=date(2026, 7, 1),
        original_amount=Decimal("100"), outstanding_amount=Decimal("100"), status=InvoiceStatus.OVERDUE,
    ))
    parsed = parse_receivables_csv(csv(
        "EXT-001,External Trading,INV-001,100,100,2026-06-01,2026-07-01,INR,OVERDUE",
        "EXT-002,Second Account,INV-002,200,200,2026-06-01,2026-07-01,INR,OVERDUE",
        "EXT-002,Second Account,INV-002,200,200,2026-06-01,2026-07-01,INR,OVERDUE",
    ), TODAY, [customer])
    assert parsed.preview.valid_rows == 1
    assert parsed.preview.duplicate_rows == 2


def test_malformed_csv_and_missing_headers_do_not_produce_records() -> None:
    malformed = parse_receivables_csv('customer_reference,customer_name\n"EXT-001,broken', TODAY, [])
    assert malformed.preview.file_errors
    assert malformed.valid_records == []


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.rolled_back = False

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    def rollback(self) -> None:
        self.rolled_back = True


def test_confirm_builds_existing_domain_records_and_provenance(monkeypatch) -> None:
    parsed = parse_receivables_csv(csv(
        "EXT-001,External Trading,INV-001,125000,125000,2026-06-01,2026-07-01,INR,OVERDUE",
    ), TODAY, [])
    session = FakeSession()
    monkeypatch.setattr(receivables, "synchronize_recovery_states", lambda _db, _date: {"cases_evaluated": 1, "cases_changed": 1})
    result = persist_receivables(session, parsed, [], TODAY)  # type: ignore[arg-type]
    assert result.customers_created == 1
    assert result.invoices_created == 1
    assert result.recovery_cases_created == 1
    assert any(isinstance(value, Customer) for value in session.added)
    assert any(isinstance(value, Invoice) for value in session.added)
    assert any(isinstance(value, RecoveryCase) for value in session.added)
    audits = [value for value in session.added if isinstance(value, AuditEvent)]
    assert len(audits) == 1 and audits[0].event_type == "RECEIVABLE_IMPORTED"
    assert audits[0].payload["source"] == "CSV Import"

    imported_invoice = next(value for value in session.added if isinstance(value, Invoice))
    imported_invoice.customer_id = imported_invoice.customer.id
    assert _invoice_item(imported_invoice, {imported_invoice.id}).source == "CSV_IMPORT"


def test_future_invoice_is_imported_as_scheduled_without_recovery_case(monkeypatch) -> None:
    parsed = parse_receivables_csv(csv(
        "EXT-FUTURE,Scheduled Trading,INV-FUTURE,1000,1000,2026-09-01,2026-09-30,INR,OPEN",
    ), TODAY, [])
    session = FakeSession()
    monkeypatch.setattr(receivables, "synchronize_recovery_states", lambda _db, _date: {"cases_evaluated": 0, "cases_changed": 0})
    result = persist_receivables(session, parsed, [], TODAY)  # type: ignore[arg-type]
    invoice = next(value for value in session.added if isinstance(value, Invoice))
    assert result.invoices_created == 1 and result.recovery_cases_created == 0
    assert not any(isinstance(value, RecoveryCase) for value in session.added)
    assert evaluate_invoice(invoice, TODAY).state == "SCHEDULED"


def test_imported_facts_use_the_same_intelligence_engine_as_seeded_facts(monkeypatch) -> None:
    parsed = parse_receivables_csv(csv(
        "EXT-001,External Trading,INV-001,125000,125000,2026-06-01,2026-07-01,INR,OVERDUE",
    ), TODAY, [])
    session = FakeSession()
    monkeypatch.setattr(receivables, "synchronize_recovery_states", lambda _db, _date: {"cases_evaluated": 1, "cases_changed": 1})
    persist_receivables(session, parsed, [], TODAY)  # type: ignore[arg-type]
    imported_customer = next(value for value in session.added if isinstance(value, Customer))

    seeded_customer = Customer(id=uuid4(), name="Equivalent Seed", account_reference="SEED-001")
    seeded_invoice = Invoice(
        id=uuid4(), customer=seeded_customer, invoice_number="SEED-INV-001",
        original_amount=Decimal("125000"), outstanding_amount=Decimal("125000"),
        issue_date=date(2026, 6, 1), due_date=date(2026, 7, 1), status=InvoiceStatus.OVERDUE,
    )
    RecoveryCase(
        id=uuid4(), customer=seeded_customer, invoice=seeded_invoice,
        current_state=RecoveryState.NEW, priority=RecoveryPriority.NORMAL,
        opened_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )

    imported_result = evaluate_customer_intelligence(imported_customer, TODAY)
    seeded_result = evaluate_customer_intelligence(seeded_customer, TODAY)
    assert imported_result.score == seeded_result.score
    assert imported_result.raw_score == seeded_result.raw_score
    assert imported_result.level == seeded_result.level
    assert imported_result.recommendation.action == seeded_result.recommendation.action
    assert imported_result.metrics == seeded_result.metrics


def test_invalid_preview_cannot_be_persisted() -> None:
    parsed = parse_receivables_csv(csv(
        "EXT-001,External Trading,INV-001,100,200,2026-06-01,2026-07-01,INR,OVERDUE",
    ), TODAY, [])
    with pytest.raises(ValueError, match="validation errors"):
        persist_receivables(FakeSession(), parsed, [], TODAY)  # type: ignore[arg-type]
