"""Communication analysis endpoints. They only persist interpretation records."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.intelligence.provider import ProviderError
from app.intelligence.schemas import AnalysisResponse, CommunicationAnalysisResult, PreviewRequest
from app.intelligence.service import analyze_text, persist_analysis
from app.models.domain import AIProcessingStatus, Communication, CommunicationAnalysis

router = APIRouter(tags=["intelligence"])

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
