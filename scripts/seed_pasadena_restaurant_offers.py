#!/usr/bin/env python3
"""
Seed Pasadena restaurant merchants + coming-soon offers for app discovery/reviews.

This script is idempotent:
- User keyed by email merchant+<slug>@perknation.dev
- Merchant profile keyed by owner_user_id
- Location keyed by (merchant_id, name)
- Offer keyed by (merchant_id, title)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import Location, MerchantProfile, Offer, OfferStatus, User, UserRole
from app.db.session import SessionLocal, engine


@dataclass(frozen=True)
class PasadenaRestaurant:
    slug: str
    name: str
    legal_name: str
    domain: str
    address: str
    latitude: Decimal
    longitude: Decimal


def d(value: str) -> Decimal:
    return Decimal(value)


def favicon_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=256"


RESTAURANTS: list[PasadenaRestaurant] = [
    PasadenaRestaurant(
        slug="union_pasadena",
        name="Union",
        legal_name="Union Pasadena LLC",
        domain="unionpasadena.com",
        address="37 E Union St, Pasadena, CA 91103",
        latitude=d("34.1473556"),
        longitude=d("-118.1493598"),
    ),
    PasadenaRestaurant(
        slug="agnes_pasadena",
        name="Agnes Restaurant & Cheesery",
        legal_name="Agnes Pasadena LLC",
        domain="agnesla.com",
        address="40 W Green St, Pasadena, CA 91105",
        latitude=d("34.1459290"),
        longitude=d("-118.1509660"),
    ),
    PasadenaRestaurant(
        slug="fishwives_pasadena",
        name="Fishwives",
        legal_name="Fishwives Pasadena LLC",
        domain="fishwives.com",
        address="88 N Fair Oaks Ave, Pasadena, CA 91103",
        latitude=d("34.1477433"),
        longitude=d("-118.1502101"),
    ),
    PasadenaRestaurant(
        slug="perle_pasadena",
        name="Perle",
        legal_name="Perle Pasadena LLC",
        domain="perlerestaurant.com",
        address="43 E Union St, Pasadena, CA 91103",
        latitude=d("34.1473755"),
        longitude=d("-118.1491020"),
    ),
    PasadenaRestaurant(
        slug="bone_kettle_pasadena",
        name="Bone Kettle",
        legal_name="Bone Kettle Pasadena LLC",
        domain="bonekettle.com",
        address="67 N Raymond Ave, Pasadena, CA 91103",
        latitude=d("34.1475166"),
        longitude=d("-118.1504760"),
    ),
    PasadenaRestaurant(
        slug="osawa_pasadena",
        name="Osawa",
        legal_name="Osawa Pasadena LLC",
        domain="osawapasadena.com",
        address="77 N Raymond Ave, Pasadena, CA 91103",
        latitude=d("34.1478368"),
        longitude=d("-118.1505487"),
    ),
    PasadenaRestaurant(
        slug="panda_inn_pasadena",
        name="Panda Inn",
        legal_name="Panda Inn Pasadena LLC",
        domain="pandainn.com",
        address="3488 E Foothill Blvd, Pasadena, CA 91107",
        latitude=d("34.1516880"),
        longitude=d("-118.0782526"),
    ),
    PasadenaRestaurant(
        slug="pez_pasadena",
        name="Pez Coastal Kitchen",
        legal_name="Pez Pasadena LLC",
        domain="pezcoastalkitchen.com",
        address="61 N Raymond Ave, Pasadena, CA 91103",
        latitude=d("34.1473820"),
        longitude=d("-118.1504512"),
    ),
]


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    starts_at = datetime.now(timezone.utc) + timedelta(days=21)
    ends_at = starts_at + timedelta(days=365)

    users_created = 0
    profiles_created = 0
    locations_created = 0
    offers_created = 0
    offers_updated = 0

    with SessionLocal() as db:
        for restaurant in RESTAURANTS:
            email = f"merchant+{restaurant.slug}@perknation.dev"
            full_name = f"{restaurant.name} Merchant"

            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(
                    full_name=full_name,
                    email=email,
                    phone=None,
                    password_hash=None,
                    role=UserRole.merchant,
                    email_verified=True,
                )
                db.add(user)
                db.flush()
                users_created += 1
            else:
                user.role = UserRole.merchant
                user.email_verified = True

            profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == user.id))
            if not profile:
                profile = MerchantProfile(
                    owner_user_id=user.id,
                    legal_name=restaurant.legal_name,
                    dba_name=restaurant.name,
                    logo_url=favicon_url(restaurant.domain),
                    category="restaurant",
                    subscription_tier="growth",
                    status="approved",
                )
                db.add(profile)
                db.flush()
                profiles_created += 1
            else:
                profile.legal_name = restaurant.legal_name
                profile.dba_name = restaurant.name
                profile.logo_url = favicon_url(restaurant.domain)
                profile.category = "restaurant"
                profile.status = "approved"

            location_name = f"{restaurant.name} - Pasadena"
            location = db.scalar(
                select(Location).where(
                    Location.merchant_id == profile.id,
                    Location.name == location_name,
                )
            )
            if not location:
                location = Location(
                    merchant_id=profile.id,
                    name=location_name,
                    address=restaurant.address,
                    latitude=restaurant.latitude,
                    longitude=restaurant.longitude,
                    hours="Daily 11:00-22:00",
                    status="active",
                )
                db.add(location)
                db.flush()
                locations_created += 1
            else:
                location.address = restaurant.address
                location.latitude = restaurant.latitude
                location.longitude = restaurant.longitude
                location.hours = "Daily 11:00-22:00"
                location.status = "active"

            offer_title = f"{restaurant.name}: Early Access Dining Perk"
            offer_terms = (
                "Coming soon. Join the early bird list to get first access when this dining offer goes live. "
                "Rate and review this place now to help shape launch promotions."
            )

            offer = db.scalar(
                select(Offer).where(
                    Offer.merchant_id == profile.id,
                    Offer.title == offer_title,
                )
            )

            if not offer:
                offer = Offer(
                    merchant_id=profile.id,
                    location_id=location.id,
                    created_by_user_id=user.id,
                    title=offer_title,
                    offer_type="restaurant",
                    terms_text=offer_terms,
                    reward_rate_cash=Decimal("0.05"),
                    reward_rate_stock=Decimal("0.06"),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    schedule_rules="Daily",
                    daily_cap=Decimal("10.00"),
                    total_cap=Decimal("250.00"),
                    per_user_limit=10,
                    approval_status=OfferStatus.approved,
                )
                db.add(offer)
                offers_created += 1
            else:
                offer.location_id = location.id
                offer.offer_type = "restaurant"
                offer.terms_text = offer_terms
                offer.reward_rate_cash = Decimal("0.05")
                offer.reward_rate_stock = Decimal("0.06")
                offer.starts_at = starts_at
                offer.ends_at = ends_at
                offer.schedule_rules = "Daily"
                offer.daily_cap = Decimal("10.00")
                offer.total_cap = Decimal("250.00")
                offer.per_user_limit = 10
                offer.approval_status = OfferStatus.approved
                offers_updated += 1

        db.commit()

    print("Pasadena restaurant seed complete.")
    print(f"Users created: {users_created}")
    print(f"Profiles created: {profiles_created}")
    print(f"Locations created: {locations_created}")
    print(f"Offers created: {offers_created}")
    print(f"Offers updated: {offers_updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
