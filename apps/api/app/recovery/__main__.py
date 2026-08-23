from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.domain import SimulationState
from app.recovery.engine import synchronize_recovery_states


def main() -> None:
    with SessionLocal() as session:
        simulation_date = session.scalar(select(SimulationState.simulation_date).where(SimulationState.name == "default"))
        if simulation_date is None:
            raise RuntimeError("No default SimulationState exists. Seed the database first.")
        print(synchronize_recovery_states(session, simulation_date))


if __name__ == "__main__":
    main()
