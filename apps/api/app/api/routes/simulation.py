"""Explicit simulation inspection and manual tick controls."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.simulation.service import recent_events, reset_simulation, run_tick, simulation_state

router = APIRouter(prefix="/simulation", tags=["simulation"])


class ResetSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["RESET_DEMO_SIMULATION"]

@router.get("/state")
def get_state(db: Session = Depends(get_db)) -> dict:
    try: return simulation_state(db)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.post("/tick")
def tick(db: Session = Depends(get_db)) -> dict:
    try: return run_tick(db)
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reset")
def reset(_payload: ResetSimulationRequest, db: Session = Depends(get_db)) -> dict:
    try: return reset_simulation(db)
    except (RuntimeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/events")
def list_events(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return recent_events(db, limit)
