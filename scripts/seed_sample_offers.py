#!/usr/bin/env python3
"""
Seed known-retailer sample merchants + offers into the configured database.

This is idempotent:
- Merchants are keyed by email: merchant+<slug>@perknation.dev
- Offers are keyed by (merchant_profile_id, title)

Safe to run multiple times.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
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
from app.db.models import MerchantProfile, Offer, OfferStatus, User, UserRole
from app.db.session import SessionLocal, engine


@dataclass(frozen=True)
class SampleOffer:
    slug: str
    brand: str
    category: str
    title: str
    offer_type: str
    terms_text: str
    reward_rate_cash: Decimal
    reward_rate_stock: Decimal
    schedule_rules: str | None
    daily_cap: Decimal | None
    total_cap: Decimal | None
    per_user_limit: int | None


def d(value: str) -> Decimal:
    return Decimal(value)

def favicon_url(domain: str) -> str:
    # Google favicon service: easy, public, HTTPS, and works for well-known retailers.
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=256"


DOMAIN_BY_SLUG: dict[str, str] = {
    "starbucks": "starbucks.com",
    "dunkin": "dunkin.com",
    "chipotle": "chipotle.com",
    "mcdonalds": "mcdonalds.com",
    "panera": "panerabread.com",
    "tacobell": "tacobell.com",
    "wholefoods": "wholefoodsmarket.com",
    "traderjoes": "traderjoes.com",
    "kroger": "kroger.com",
    "target": "target.com",
    "amazon": "amazon.com",
    "bestbuy": "bestbuy.com",
    "nike": "nike.com",
    "sephora": "sephora.com",
    "homedepot": "homedepot.com",
    "lowes": "lowes.com",
    "cvs": "cvs.com",
    "shell": "shell.com",
    "chevron": "chevron.com",
    "uber": "uber.com",
}


SAMPLES: list[SampleOffer] = [
    SampleOffer(
        slug="starbucks",
        brand="Starbucks",
        category="coffee",
        title="Starbucks: Morning Boost (8% cash / 10% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $5/day.",
        reward_rate_cash=d("0.08"),
        reward_rate_stock=d("0.10"),
        schedule_rules="Mon-Fri 07:00-11:00",
        daily_cap=d("5.00"),
        total_cap=d("50.00"),
        per_user_limit=10,
    ),
    SampleOffer(
        slug="dunkin",
        brand="Dunkin'",
        category="coffee",
        title="Dunkin': Coffee Run (7% cash / 8% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $4/day.",
        reward_rate_cash=d("0.07"),
        reward_rate_stock=d("0.08"),
        schedule_rules="Daily 05:00-11:00",
        daily_cap=d("4.00"),
        total_cap=d("40.00"),
        per_user_limit=12,
    ),
    SampleOffer(
        slug="chipotle",
        brand="Chipotle",
        category="restaurant",
        title="Chipotle: Lunch & Dinner Earn (6% cash / 7% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $8/day.",
        reward_rate_cash=d("0.06"),
        reward_rate_stock=d("0.07"),
        schedule_rules="Daily 11:00-21:00",
        daily_cap=d("8.00"),
        total_cap=d("80.00"),
        per_user_limit=10,
    ),
    SampleOffer(
        slug="mcdonalds",
        brand="McDonald's",
        category="restaurant",
        title="McDonald's: Breakfast Bonus (5% cash / 6% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $3/day.",
        reward_rate_cash=d("0.05"),
        reward_rate_stock=d("0.06"),
        schedule_rules="Daily 06:00-10:59",
        daily_cap=d("3.00"),
        total_cap=d("30.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="panera",
        brand="Panera Bread",
        category="restaurant",
        title="Panera: Midday Perks (5% cash / 6% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $6/day.",
        reward_rate_cash=d("0.05"),
        reward_rate_stock=d("0.06"),
        schedule_rules="Mon-Sun 10:00-14:00",
        daily_cap=d("6.00"),
        total_cap=d("60.00"),
        per_user_limit=10,
    ),
    SampleOffer(
        slug="tacobell",
        brand="Taco Bell",
        category="restaurant",
        title="Taco Bell: Late-Night Boost (4% cash / 5% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $5/day.",
        reward_rate_cash=d("0.04"),
        reward_rate_stock=d("0.05"),
        schedule_rules="Daily 20:00-23:59",
        daily_cap=d("5.00"),
        total_cap=d("50.00"),
        per_user_limit=12,
    ),
    SampleOffer(
        slug="wholefoods",
        brand="Whole Foods Market",
        category="grocery",
        title="Whole Foods: Grocery Essentials (3% cash / 4% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $10/day.",
        reward_rate_cash=d("0.03"),
        reward_rate_stock=d("0.04"),
        schedule_rules=None,
        daily_cap=d("10.00"),
        total_cap=d("100.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="traderjoes",
        brand="Trader Joe's",
        category="grocery",
        title="Trader Joe's: Weekly Run (4% cash / 5% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $10/day.",
        reward_rate_cash=d("0.04"),
        reward_rate_stock=d("0.05"),
        schedule_rules=None,
        daily_cap=d("10.00"),
        total_cap=d("100.00"),
        per_user_limit=15,
    ),
    SampleOffer(
        slug="kroger",
        brand="Kroger",
        category="grocery",
        title="Kroger: Pantry Stock-Up (3% cash / 4% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $10/day.",
        reward_rate_cash=d("0.03"),
        reward_rate_stock=d("0.04"),
        schedule_rules=None,
        daily_cap=d("10.00"),
        total_cap=d("100.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="target",
        brand="Target",
        category="retail",
        title="Target: Everyday Items (2% cash / 3% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $10/day.",
        reward_rate_cash=d("0.02"),
        reward_rate_stock=d("0.03"),
        schedule_rules=None,
        daily_cap=d("10.00"),
        total_cap=d("100.00"),
        per_user_limit=25,
    ),
    SampleOffer(
        slug="amazon",
        brand="Amazon",
        category="retail_online",
        title="Amazon: Online Cart Bonus (1.5% cash / 2% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $7.50/day.",
        reward_rate_cash=d("0.015"),
        reward_rate_stock=d("0.02"),
        schedule_rules=None,
        daily_cap=d("7.50"),
        total_cap=d("75.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="bestbuy",
        brand="Best Buy",
        category="electronics",
        title="Best Buy: Tech Refresh (4% cash / 5% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $15/day.",
        reward_rate_cash=d("0.04"),
        reward_rate_stock=d("0.05"),
        schedule_rules=None,
        daily_cap=d("15.00"),
        total_cap=d("150.00"),
        per_user_limit=10,
    ),
    SampleOffer(
        slug="nike",
        brand="Nike",
        category="apparel",
        title="Nike: Gear Up (8% cash / 10% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $20/day.",
        reward_rate_cash=d("0.08"),
        reward_rate_stock=d("0.10"),
        schedule_rules=None,
        daily_cap=d("20.00"),
        total_cap=d("200.00"),
        per_user_limit=8,
    ),
    SampleOffer(
        slug="sephora",
        brand="Sephora",
        category="beauty",
        title="Sephora: Beauty Boost (6% cash / 8% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $15/day.",
        reward_rate_cash=d("0.06"),
        reward_rate_stock=d("0.08"),
        schedule_rules=None,
        daily_cap=d("15.00"),
        total_cap=d("150.00"),
        per_user_limit=10,
    ),
    SampleOffer(
        slug="homedepot",
        brand="The Home Depot",
        category="home_improvement",
        title="The Home Depot: Project Supplies (3% cash / 4% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $25/day.",
        reward_rate_cash=d("0.03"),
        reward_rate_stock=d("0.04"),
        schedule_rules=None,
        daily_cap=d("25.00"),
        total_cap=d("250.00"),
        per_user_limit=12,
    ),
    SampleOffer(
        slug="lowes",
        brand="Lowe's",
        category="home_improvement",
        title="Lowe's: Build & Save (3% cash / 4% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $25/day.",
        reward_rate_cash=d("0.03"),
        reward_rate_stock=d("0.04"),
        schedule_rules=None,
        daily_cap=d("25.00"),
        total_cap=d("250.00"),
        per_user_limit=12,
    ),
    SampleOffer(
        slug="cvs",
        brand="CVS Pharmacy",
        category="pharmacy",
        title="CVS: Health & Wellness (2.5% cash / 3% stock)",
        offer_type="boost",
        terms_text="Sample terms: Activate before purchase. Excludes gift cards. Max $8/day.",
        reward_rate_cash=d("0.025"),
        reward_rate_stock=d("0.03"),
        schedule_rules=None,
        daily_cap=d("8.00"),
        total_cap=d("80.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="shell",
        brand="Shell",
        category="gas_station",
        title="Shell: Fuel Saver (5% cash / 6% stock)",
        offer_type="boost",
        terms_text="Sample terms: Fuel purchases only. Excludes gift cards. Max $6/day.",
        reward_rate_cash=d("0.05"),
        reward_rate_stock=d("0.06"),
        schedule_rules=None,
        daily_cap=d("6.00"),
        total_cap=d("60.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="chevron",
        brand="Chevron",
        category="gas_station",
        title="Chevron: Fill-Up Bonus (4% cash / 5% stock)",
        offer_type="boost",
        terms_text="Sample terms: Fuel purchases only. Excludes gift cards. Max $5/day.",
        reward_rate_cash=d("0.04"),
        reward_rate_stock=d("0.05"),
        schedule_rules=None,
        daily_cap=d("5.00"),
        total_cap=d("50.00"),
        per_user_limit=20,
    ),
    SampleOffer(
        slug="uber",
        brand="Uber",
        category="transportation",
        title="Uber: Ride Rewards (2.5% cash / 3% stock)",
        offer_type="boost",
        terms_text="Sample terms: Rides only. Excludes tips and gift cards. Max $5/day.",
        reward_rate_cash=d("0.025"),
        reward_rate_stock=d("0.03"),
        schedule_rules=None,
        daily_cap=d("5.00"),
        total_cap=d("50.00"),
        per_user_limit=25,
    ),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    now = datetime.now(timezone.utc)
    # Keep these sample retailers in "coming soon" so users can early-bird opt in.
    starts_at = now + timedelta(days=14)
    ends_at = now + timedelta(days=180)

    created_users = 0
    created_profiles = 0
    created_offers = 0
    updated_offers = 0

    with SessionLocal() as db:
        for sample in SAMPLES:
            email = f"merchant+{sample.slug}@perknation.dev"
            domain = DOMAIN_BY_SLUG.get(sample.slug)

            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(
                    full_name=f"{sample.brand} Merchant",
                    email=email,
                    phone=None,
                    password_hash=None,
                    role=UserRole.merchant,
                    email_verified=True,
                )
                db.add(user)
                db.flush()
                created_users += 1

            profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == user.id))
            if not profile:
                profile = MerchantProfile(
                    owner_user_id=user.id,
                    legal_name=f"{sample.brand} Merchant LLC",
                    dba_name=sample.brand,
                    logo_url=favicon_url(domain) if domain else None,
                    category=sample.category,
                    subscription_tier="growth",
                    status="approved",
                )
                db.add(profile)
                db.flush()
                created_profiles += 1
            else:
                # Keep the profile fresh if this script is re-run.
                profile.dba_name = sample.brand
                profile.category = sample.category
                if domain:
                    profile.logo_url = favicon_url(domain)

            existing_offer = db.scalar(
                select(Offer).where(
                    Offer.merchant_id == profile.id,
                    Offer.title == sample.title,
                )
            )
            if not existing_offer:
                offer = Offer(
                    merchant_id=profile.id,
                    location_id=None,
                    created_by_user_id=user.id,
                    title=sample.title,
                    offer_type=sample.offer_type,
                    terms_text=sample.terms_text,
                    reward_rate_cash=sample.reward_rate_cash,
                    reward_rate_stock=sample.reward_rate_stock,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    schedule_rules=sample.schedule_rules,
                    daily_cap=sample.daily_cap,
                    total_cap=sample.total_cap,
                    per_user_limit=sample.per_user_limit,
                    approval_status=OfferStatus.approved,
                )
                db.add(offer)
                created_offers += 1
            else:
                existing_offer.offer_type = sample.offer_type
                existing_offer.terms_text = sample.terms_text
                existing_offer.reward_rate_cash = sample.reward_rate_cash
                existing_offer.reward_rate_stock = sample.reward_rate_stock
                existing_offer.starts_at = starts_at
                existing_offer.ends_at = ends_at
                existing_offer.schedule_rules = sample.schedule_rules
                existing_offer.daily_cap = sample.daily_cap
                existing_offer.total_cap = sample.total_cap
                existing_offer.per_user_limit = sample.per_user_limit
                existing_offer.approval_status = OfferStatus.approved
                updated_offers += 1

        db.commit()

    print("Seed complete.")
    print(f"Created users: {created_users}")
    print(f"Created merchant profiles: {created_profiles}")
    print(f"Created offers: {created_offers}")
    print(f"Updated offers: {updated_offers}")


if __name__ == "__main__":
    main()
