#!/usr/bin/env python3
"""
Seed demo merchant locations centered around Old Town Pasadena (for map pins).

This script is idempotent:
- Ensures each MerchantProfile has at least one Location.
- Updates/creates a primary location per merchant with a Pasadena address + lat/lng.
- Assigns any offers missing location_id to that merchant's primary location.

Safe to run multiple times.
"""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from random import Random

from sqlalchemy import select

# Ensure backend root is on sys.path when running this script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import Location, MerchantProfile, Offer
from app.db.session import SessionLocal, engine


OLD_TOWN_PASADENA_CENTER = (34.1456, -118.1505)

ADDRESS_POOL: list[str] = [
    "1 E Colorado Blvd, Pasadena, CA 91105",
    "55 E Colorado Blvd, Pasadena, CA 91105",
    "100 E Colorado Blvd, Pasadena, CA 91105",
    "150 E Colorado Blvd, Pasadena, CA 91105",
    "200 E Colorado Blvd, Pasadena, CA 91105",
    "30 S Fair Oaks Ave, Pasadena, CA 91105",
    "75 S Fair Oaks Ave, Pasadena, CA 91105",
    "120 S Fair Oaks Ave, Pasadena, CA 91105",
    "10 N Raymond Ave, Pasadena, CA 91105",
    "60 N Raymond Ave, Pasadena, CA 91105",
    "110 N Raymond Ave, Pasadena, CA 91105",
    "20 S Raymond Ave, Pasadena, CA 91105",
    "70 S Raymond Ave, Pasadena, CA 91105",
    "16 N De Lacey Ave, Pasadena, CA 91105",
    "64 N De Lacey Ave, Pasadena, CA 91105",
    "25 E Green St, Pasadena, CA 91105",
    "80 E Green St, Pasadena, CA 91105",
    "35 Union St, Pasadena, CA 91105",
    "90 Union St, Pasadena, CA 91105",
    "45 W Colorado Blvd, Pasadena, CA 91105",
    "95 W Colorado Blvd, Pasadena, CA 91105",
    "150 W Colorado Blvd, Pasadena, CA 91105",
    "60 S Arroyo Pkwy, Pasadena, CA 91105",
    "100 S Arroyo Pkwy, Pasadena, CA 91105",
]


def dec7(value: float) -> Decimal:
    # Numeric(10,7) in the DB: format to 7 decimals for consistent output.
    return Decimal(f"{value:.7f}")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    created_locations = 0
    updated_locations = 0
    assigned_offers = 0

    with SessionLocal() as db:
        merchants = db.scalars(select(MerchantProfile).order_by(MerchantProfile.id.asc())).all()
        if not merchants:
            print("No merchant profiles found. Seed merchants/offers first (seed_sample_offers.py).")
            return

        for idx, merchant in enumerate(merchants):
            # Deterministic jitter so pins aren't stacked on the exact same coordinate.
            rng = Random(merchant.id)
            jitter_lat = rng.uniform(-0.0040, 0.0040)
            jitter_lng = rng.uniform(-0.0045, 0.0045)
            lat = OLD_TOWN_PASADENA_CENTER[0] + jitter_lat
            lng = OLD_TOWN_PASADENA_CENTER[1] + jitter_lng

            address = ADDRESS_POOL[idx % len(ADDRESS_POOL)]
            # Add a suite to keep addresses unique-ish when we wrap.
            suite = 100 + (idx % 50)
            address_with_suite = f"{address}, Suite {suite}"

            location_name = f"{merchant.dba_name} - Old Town Pasadena"
            hours = "Daily 09:00-21:00"

            location = db.scalar(
                select(Location)
                .where(Location.merchant_id == merchant.id)
                .order_by(Location.id.asc())
            )

            if not location:
                location = Location(
                    merchant_id=merchant.id,
                    name=location_name,
                    address=address_with_suite,
                    latitude=dec7(lat),
                    longitude=dec7(lng),
                    hours=hours,
                    status="active",
                )
                db.add(location)
                db.flush()
                created_locations += 1
            else:
                # Preserve real merchant location data when it already exists.
                # This script's primary responsibility is assigning missing offer
                # locations, not rewriting existing merchant addresses.
                updated_locations += 0

            offers = db.scalars(
                select(Offer).where(
                    Offer.merchant_id == merchant.id,
                    Offer.location_id.is_(None),
                )
            ).all()

            for offer in offers:
                offer.location_id = location.id
                assigned_offers += 1

        db.commit()

    print("Pasadena location seed complete.")
    print(f"Merchants processed: {len(merchants)}")
    print(f"Locations created: {created_locations}")
    print(f"Locations updated: {updated_locations}")
    print(f"Offers assigned a location: {assigned_offers}")
    print(f"Completed at: {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
