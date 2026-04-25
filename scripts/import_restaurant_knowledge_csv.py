#!/usr/bin/env python3
"""
Bulk import restaurant knowledge rows from CSV.

Expected CSV headers:
slug,name,city,neighborhood,cuisine,price_tier,address,latitude,longitude,summary,highlights,website_url,source_label,source_url,is_active

Usage:
  PYTHONPATH=. .venv/bin/python scripts/import_restaurant_knowledge_csv.py ./restaurants.csv
"""

from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import RestaurantKnowledge
from app.db.session import SessionLocal, engine


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


def _to_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    text = value.strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: import_restaurant_knowledge_csv.py <path-to-csv>")
        return 1

    csv_path = Path(argv[0]).expanduser().resolve()
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return 1

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    created = 0
    updated = 0

    with SessionLocal() as db:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                slug = str(row.get("slug") or "").strip().lower()
                name = str(row.get("name") or "").strip()
                city = str(row.get("city") or "").strip()
                cuisine = str(row.get("cuisine") or "").strip()
                summary = str(row.get("summary") or "").strip()

                if not all([slug, name, city, cuisine, summary]):
                    continue

                current = db.scalar(select(RestaurantKnowledge).where(RestaurantKnowledge.slug == slug))
                if current is None:
                    current = RestaurantKnowledge(slug=slug, name=name, city=city, cuisine=cuisine, summary=summary)
                    db.add(current)
                    created += 1
                else:
                    updated += 1

                current.name = name
                current.city = city
                current.neighborhood = (row.get("neighborhood") or "").strip() or None
                current.cuisine = cuisine
                current.price_tier = (row.get("price_tier") or "").strip() or None
                current.address = (row.get("address") or "").strip() or None
                current.latitude = _to_decimal(row.get("latitude"))
                current.longitude = _to_decimal(row.get("longitude"))
                current.summary = summary
                current.highlights = (row.get("highlights") or "").strip() or None
                current.website_url = (row.get("website_url") or "").strip() or None
                current.source_label = (row.get("source_label") or "").strip() or "CSV import"
                current.source_url = (row.get("source_url") or "").strip() or None
                current.is_active = _to_bool(row.get("is_active"), default=True)

        db.commit()

    print(f"Import complete. Created={created}, Updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
