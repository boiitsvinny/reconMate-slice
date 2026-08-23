from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

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
    """Confirm the API can establish and use a PostgreSQL connection."""
    try:
        db.execute(select(1))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return ReadinessResponse(status="ok", service="reconmate-api", database="ok")
