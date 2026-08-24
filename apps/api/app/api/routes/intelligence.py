"""Communication interpretation and read-only operational intelligence endpoints."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload
from app.db.session import get_db
from app.intelligence.operational_schemas import IntelligenceResult, PortfolioIntelligence
from app.intelligence.operational_service import (
    evaluate_case_intelligence,
    evaluate_customer_intelligence,
    evaluate_portfolio_intelligence,
)
from app.intelligence.provider import ProviderError
from app.intelligence.schemas import AnalysisResponse, CommunicationAnalysisResult, PreviewRequest
from app.intelligence.service import analyze_text, persist_analysis
from app.models.domain import (
    AIProcessingStatus,
    Communication,
    CommunicationAnalysis,
    Customer,
    Invoice,
    PromiseToPay,
    RecoveryCase,
    SimulationState,
)

router = APIRouter(tags=["intelligence"])


def _simulation_date(db: Session):
    value = db.scalar(select(SimulationState.simulation_date).where(SimulationState.name == "default"))
    if value is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Synthetic simulation state has not been seeded.")
    return value


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
        selectinload(RecoveryCase.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.invoices).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.invoice).selectinload(Invoice.payments),
        selectinload(RecoveryCase.customer).selectinload(Customer.promises_to_pay).selectinload(PromiseToPay.source_communication),
        selectinload(RecoveryCase.actions),
    )

def _response(record: CommunicationAnalysis) -> AnalysisResponse:
    return AnalysisResponse(analysis_id=str(record.id), provider=record.provider, model_version=record.model_version,
        analyzed_at=record.analyzed_at.isoformat() if record.analyzed_at else None,
        result=CommunicationAnalysisResult.model_validate(record.result))

@router.post("/intelligence/analyze-preview", response_model=AnalysisResponse, summary="Interpret draft text without storing it")
def analyze_preview(payload: PreviewRequest) -> AnalysisResponse:
    try:
        provider, result = analyze_text(payload.content, payload.reference_date)
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return AnalysisResponse(provider=provider.name, model_version=provider.model_version, result=result)

@router.get("/communications", summary="List source communications")
def list_communications(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Communication).order_by(Communication.occurred_at.desc())).all()
    return [{"id": str(item.id), "customer_id": str(item.customer_id), "direction": item.direction.value,
             "channel": item.channel.value, "content": item.content, "occurred_at": item.occurred_at,
             "ai_processing_status": item.ai_processing_status.value} for item in rows]

@router.get("/communications/{communication_id}", summary="Get immutable communication source")
def get_communication(communication_id: UUID, db: Session = Depends(get_db)) -> dict:
    item = db.get(Communication, communication_id)
    if item is None: raise HTTPException(status_code=404, detail="Communication not found.")
    return {"id": str(item.id), "customer_id": str(item.customer_id), "direction": item.direction.value,
            "channel": item.channel.value, "content": item.content, "occurred_at": item.occurred_at,
            "ai_processing_status": item.ai_processing_status.value}

@router.post("/communications/{communication_id}/analyze", response_model=AnalysisResponse, summary="Store a fresh interpretation")
def analyze_communication(communication_id: UUID, db: Session = Depends(get_db)) -> AnalysisResponse:
    item = db.get(Communication, communication_id)
    if item is None: raise HTTPException(status_code=404, detail="Communication not found.")
    try:
        record = persist_analysis(item)
        db.add(record); db.commit(); db.refresh(record)
        return _response(record)
    except ProviderError as exc:
        item.ai_processing_status = AIProcessingStatus.FAILED
        item.ai_processing_metadata = {"error": str(exc)}
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Communication analysis failed safely: " + str(exc)) from exc

@router.get("/communications/{communication_id}/analysis", response_model=list[AnalysisResponse], summary="List stored interpretations")
def get_communication_analysis(communication_id: UUID, db: Session = Depends(get_db)) -> list[AnalysisResponse]:
    if db.get(Communication, communication_id) is None: raise HTTPException(status_code=404, detail="Communication not found.")
    records = db.scalars(select(CommunicationAnalysis).where(CommunicationAnalysis.communication_id == communication_id)
                         .order_by(CommunicationAnalysis.analyzed_at.desc())).all()
    return [_response(record) for record in records]


@router.get(
    "/intelligence/customers/{customer_id}",
    response_model=IntelligenceResult,
    summary="Evaluate current customer priority and contributing factors",
)
def get_customer_intelligence(customer_id: UUID, db: Session = Depends(get_db)) -> IntelligenceResult:
    customer = db.scalar(_customer_query().where(Customer.id == customer_id))
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return evaluate_customer_intelligence(customer, _simulation_date(db))


@router.get(
    "/intelligence/cases/{case_id}",
    response_model=IntelligenceResult,
    summary="Evaluate current recovery-case priority and contributing factors",
)
def get_case_intelligence(case_id: UUID, db: Session = Depends(get_db)) -> IntelligenceResult:
    case = db.scalar(_case_query().where(RecoveryCase.id == case_id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery case not found.")
    return evaluate_case_intelligence(case, _simulation_date(db))


@router.get(
    "/intelligence/portfolio",
    response_model=PortfolioIntelligence,
    summary="Evaluate and rank current customer intelligence",
)
def get_portfolio_intelligence(db: Session = Depends(get_db)) -> PortfolioIntelligence:
    customers = list(db.scalars(_customer_query().order_by(Customer.account_reference)).all())
    return evaluate_portfolio_intelligence(customers, _simulation_date(db))
