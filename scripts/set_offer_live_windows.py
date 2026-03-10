#!/usr/bin/env python3
"""
Set current marketplace windows:
- Hollywood Sport Park offers: live now
- All other non-denied offers: coming soon (future start)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import MerchantProfile, Offer, OfferStatus
from app.db.session import SessionLocal, engine


LIVE_MERCHANT_DBA = "Hollywood Sport Park"


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    now = datetime.now(timezone.utc)
    coming_soon_start = now + timedelta(days=14)
    coming_soon_end = coming_soon_start + timedelta(days=365)
    live_end = now + timedelta(days=365)

    live_count = 0
    upcoming_count = 0

    with SessionLocal() as db:
        offers = db.scalars(
            select(Offer).join(MerchantProfile, Offer.merchant_id == MerchantProfile.id)
        ).all()

        for offer in offers:
            if offer.approval_status == OfferStatus.denied:
                continue

            merchant_name = offer.merchant.dba_name if offer.merchant else ""
            if merchant_name == LIVE_MERCHANT_DBA:
                offer.approval_status = OfferStatus.approved
                offer.starts_at = now
                offer.ends_at = live_end
                live_count += 1
            else:
                offer.approval_status = OfferStatus.approved
                offer.starts_at = coming_soon_start
                offer.ends_at = coming_soon_end
                upcoming_count += 1

        db.commit()

    print("Offer live windows updated.")
    print(f"live_offers={live_count}")
    print(f"coming_soon_offers={upcoming_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
