from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import Customer

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(HealthResponse):
    database: str


@router.get("/health", response_model=HealthResponse, summary="API health check")
def health_check() -> HealthResponse:
    """Return API liveness without depending on external services."""
    return HealthResponse(status="ok", service="reconmate-api")


@router.get("/health/ready", response_model=ReadinessResponse, summary="API database readiness check")
def readiness_check(db: Session = Depends(get_db)) -> ReadinessResponse:
    """Confirm the database connection and required deployed schema are usable."""
    try:
        db.execute(select(
            Customer.communication_consent_status,
            Customer.preferred_outreach_channel,
        ).limit(1))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable or the required schema migration is incomplete.",
        ) from exc
    return ReadinessResponse(status="ok", service="reconmate-api", database="ok")
