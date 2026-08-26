"""Preview-first CSV receivables intake."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.imports.receivables import (
    ReceivableCsvRequest, ReceivableImportPreview, ReceivableImportResult,
    parse_receivables_csv, persist_receivables, portfolio_import_context,
)

router = APIRouter(prefix="/imports/receivables", tags=["receivables import"])


@router.post("/preview", response_model=ReceivableImportPreview, summary="Validate a receivables CSV without mutation")
def preview_receivables(payload: ReceivableCsvRequest, db: Session = Depends(get_db)) -> ReceivableImportPreview:
    customers, operating_date = portfolio_import_context(db)
    return parse_receivables_csv(payload.csv_text, operating_date, customers).preview


@router.post("/confirm", response_model=ReceivableImportResult, status_code=status.HTTP_201_CREATED, summary="Persist a validated receivables CSV")
def confirm_receivables(payload: ReceivableCsvRequest, db: Session = Depends(get_db)) -> ReceivableImportResult:
    customers, operating_date = portfolio_import_context(db)
    parsed = parse_receivables_csv(payload.csv_text, operating_date, customers)
    if parsed.preview.file_errors or parsed.preview.invalid_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "The CSV contains validation errors; no rows were imported.", "preview": parsed.preview.model_dump(mode="json")},
        )
    try:
        return persist_receivables(db, parsed, customers, operating_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
