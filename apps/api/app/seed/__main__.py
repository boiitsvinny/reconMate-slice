from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.seed.portfolio import seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the deterministic ReconMate development portfolio.")
    parser.add_argument("--reset", action="store_true", help="Delete existing domain data before seeding.")
    args = parser.parse_args()
    with SessionLocal() as session:
        summary = seed_database(session, reset=args.reset)
    for key, value in summary.items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()
