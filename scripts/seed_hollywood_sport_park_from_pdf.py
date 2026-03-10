#!/usr/bin/env python3
"""
Seed merchant + locations + offer from:
/Users/nation/Downloads/Promotion for Gio.pdf

This script is idempotent:
- Merchant user keyed by email
- Merchant profile keyed by owner_user_id
- Locations keyed by (merchant_id, name)
- Offers keyed by (merchant_id, location_id, title)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

# Ensure backend root is on sys.path when running this script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import (
    Location,
    MerchantProfile,
    Offer,
    OfferStatus,
    RewardPreference,
    User,
    UserRole,
)
from app.db.session import SessionLocal, engine
from app.services.security import hash_password


MERCHANT_EMAIL = "merchant+hollywoodsportpark@perknation.dev"
MERCHANT_PASSWORD = "MerchantPass123!"
MERCHANT_FULL_NAME = "Gio Merchant"

MERCHANT_LEGAL_NAME = "Hollywood Sport Park LLC"
MERCHANT_DBA_NAME = "Hollywood Sport Park"
MERCHANT_CATEGORY = "entertainment"
MERCHANT_STATUS = "active"
MERCHANT_LOGO_URL = "https://www.google.com/s2/favicons?domain=hollywoodsports.com&sz=256"

# Parsed from handwritten PDF text ("Good at ..."):
LOCATIONS = [
    {
        "name": "Hollywood Sports - Bellflower",
        "address": "9030 Somerset Blvd, Bellflower, CA 90706",
        "latitude": Decimal("33.8964490"),
        "longitude": Decimal("-118.1409020"),
    },
    {
        "name": "SC Village - Chino",
        "address": "8900 McCarty Rd, Chino, CA 91710",
        "latitude": Decimal("33.9332060"),
        "longitude": Decimal("-117.6180379"),
    },
    {
        "name": "SC Village - San Diego",
        "address": "1800 Wildcat Canyon Rd, Lakeside, CA 92040",
        "latitude": Decimal("32.9469652"),
        "longitude": Decimal("-116.8452219"),
    },
    {
        "name": "Combat Paintball - Castaic",
        "address": "31050 Charlie Canyon Rd, Castaic, CA 91384",
        "latitude": Decimal("34.4838593"),
        "longitude": Decimal("-118.6070105"),
    },
    {
        "name": "Giant Party Sports - Allen (Dallas)",
        "address": "4404 Dillehay Dr, Allen, TX 75002",
        "latitude": Decimal("33.0606585"),
        "longitude": Decimal("-96.6189145"),
    },
]

OFFER_TITLE = "$5 Admission & Rental (Save $60)"
OFFER_TYPE = "promo"
OFFER_TERMS = (
    "One-year expiration. Weekend only. Not valid for private groups. "
    "Must buy 500 paintballs and all-day air. "
    "Valid at participating locations: Hollywood Sports Bellflower, "
    "SC Village Chino, SC Village San Diego, Combat Paintball Castaic, "
    "and Giant Party Sports Allen (Dallas)."
)
OFFER_REWARD_RATE_CASH = Decimal("0.0000")
OFFER_REWARD_RATE_STOCK = Decimal("0.0000")
OFFER_SCHEDULE = "Weekend only"


def ensure_user(db) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == MERCHANT_EMAIL))
    created = False

    if not user:
        user = User(
            full_name=MERCHANT_FULL_NAME,
            email=MERCHANT_EMAIL,
            phone=None,
            password_hash=hash_password(MERCHANT_PASSWORD),
            role=UserRole.merchant,
            reward_preference=RewardPreference.cash,
            email_verified=True,
        )
        db.add(user)
        db.flush()
        created = True
    else:
        # Ensure this account can operate merchant endpoints.
        user.role = UserRole.merchant
        user.email_verified = True
        if not user.password_hash:
            user.password_hash = hash_password(MERCHANT_PASSWORD)

    return user, created


def ensure_profile(db, user: User) -> tuple[MerchantProfile, bool]:
    profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == user.id))
    created = False

    if not profile:
        profile = MerchantProfile(
            owner_user_id=user.id,
            legal_name=MERCHANT_LEGAL_NAME,
            dba_name=MERCHANT_DBA_NAME,
            logo_url=MERCHANT_LOGO_URL,
            category=MERCHANT_CATEGORY,
            status=MERCHANT_STATUS,
        )
        db.add(profile)
        db.flush()
        created = True
    else:
        profile.legal_name = MERCHANT_LEGAL_NAME
        profile.dba_name = MERCHANT_DBA_NAME
        profile.logo_url = MERCHANT_LOGO_URL
        profile.category = MERCHANT_CATEGORY
        profile.status = MERCHANT_STATUS

    return profile, created


def ensure_locations(db, profile: MerchantProfile) -> tuple[list[Location], int, int]:
    created = 0
    updated = 0
    results: list[Location] = []

    for item in LOCATIONS:
        location = db.scalar(
            select(Location).where(
                Location.merchant_id == profile.id,
                Location.name == item["name"],
            )
        )
        if not location:
            location = Location(
                merchant_id=profile.id,
                name=item["name"],
                address=item["address"],
                latitude=item["latitude"],
                longitude=item["longitude"],
                hours="Weekend only",
                status="active",
            )
            db.add(location)
            db.flush()
            created += 1
        else:
            location.address = item["address"]
            location.latitude = item["latitude"]
            location.longitude = item["longitude"]
            location.hours = "Weekend only"
            location.status = "active"
            updated += 1

        results.append(location)

    return results, created, updated


def ensure_offers(
    db,
    user: User,
    profile: MerchantProfile,
    locations: list[Location],
) -> tuple[int, int]:
    created = 0
    updated = 0
    starts_at = datetime.now(timezone.utc)
    ends_at = starts_at + timedelta(days=365)

    for location in locations:
        offer = db.scalar(
            select(Offer).where(
                Offer.merchant_id == profile.id,
                Offer.location_id == location.id,
                Offer.title == OFFER_TITLE,
            )
        )
        if not offer:
            offer = Offer(
                merchant_id=profile.id,
                location_id=location.id,
                created_by_user_id=user.id,
                title=OFFER_TITLE,
                offer_type=OFFER_TYPE,
                terms_text=OFFER_TERMS,
                reward_rate_cash=OFFER_REWARD_RATE_CASH,
                reward_rate_stock=OFFER_REWARD_RATE_STOCK,
                starts_at=starts_at,
                ends_at=ends_at,
                schedule_rules=OFFER_SCHEDULE,
                daily_cap=None,
                total_cap=None,
                per_user_limit=None,
                approval_status=OfferStatus.approved,
            )
            db.add(offer)
            created += 1
        else:
            offer.title = OFFER_TITLE
            offer.offer_type = OFFER_TYPE
            offer.terms_text = OFFER_TERMS
            offer.reward_rate_cash = OFFER_REWARD_RATE_CASH
            offer.reward_rate_stock = OFFER_REWARD_RATE_STOCK
            offer.starts_at = starts_at
            offer.ends_at = ends_at
            offer.schedule_rules = OFFER_SCHEDULE
            offer.daily_cap = None
            offer.total_cap = None
            offer.per_user_limit = None
            offer.approval_status = OfferStatus.approved
            updated += 1

    return created, updated


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    with SessionLocal() as db:
        user, user_created = ensure_user(db)
        profile, profile_created = ensure_profile(db, user)
        locations, locations_created, locations_updated = ensure_locations(db, profile)
        offers_created, offers_updated = ensure_offers(db, user, profile, locations)

        db.commit()

    print("Hollywood Sport Park seed complete.")
    print(f"user_created={user_created}")
    print(f"profile_created={profile_created}")
    print(f"locations_created={locations_created}")
    print(f"locations_updated={locations_updated}")
    print(f"offers_created={offers_created}")
    print(f"offers_updated={offers_updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
