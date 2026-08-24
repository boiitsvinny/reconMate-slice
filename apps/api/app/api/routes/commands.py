"""Natural-language-like command planning with bounded confirmation execution."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.commands.schemas import (
    CommandConfirmationResult,
    CommandRequest,
    CommandResult,
    ConfirmCommandRequest,
)
from app.commands.service import CommandService, PlanExpiredError, PlanNotFoundError
from app.commands.tools import CommandDataError, CommandTools
from app.db.session import get_db


router = APIRouter(prefix="/commands", tags=["commands"])
service = CommandService()


@router.post("", response_model=CommandResult, summary="Interpret, analyze, and plan a bounded operational command")
def create_command_plan(payload: CommandRequest, db: Session = Depends(get_db)) -> CommandResult:
    try:
        return service.run(payload, CommandTools(db))
    except CommandDataError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{plan_id}/confirm",
    response_model=CommandConfirmationResult,
    summary="Confirm eligible internal workflow actions from a short-lived command plan",
)
def confirm_command_plan(
    plan_id: UUID,
    payload: ConfirmCommandRequest,
    db: Session = Depends(get_db),
) -> CommandConfirmationResult:
    try:
        return service.confirm(plan_id, payload, CommandTools(db))
    except PlanExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CommandDataError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
