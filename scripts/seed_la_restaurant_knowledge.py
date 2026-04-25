#!/usr/bin/env python3
"""
Seed the LA restaurant knowledge dataset used by the AI assistant and search API.

Usage:
  python scripts/seed_la_restaurant_knowledge.py
  python scripts/seed_la_restaurant_knowledge.py --refresh
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.session import SessionLocal, engine
from app.services.la_restaurant_knowledge import seed_la_restaurant_knowledge


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    with SessionLocal() as db:
        created, updated = seed_la_restaurant_knowledge(db, force_refresh=refresh)

    print("LA restaurant knowledge seed complete.")
    print(f"Created: {created}")
    print(f"Updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
