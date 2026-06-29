#!/usr/bin/env python3
"""
Seed the Bond Collective merchant profile and initial PerkNation promo.

Idempotent:
- Merchant owner is keyed by billy@neonflux.net.
- Merchant profile is keyed by owner_user_id.
- Offer is keyed by (merchant_id, title).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import MerchantProfile, Offer, OfferStatus, RewardPreference, User, UserRole
from app.db.session import SessionLocal, engine


OWNER_EMAIL = "billy@neonflux.net"
MERCHANT_LEGAL_NAME = "Bond Collective"
MERCHANT_DBA_NAME = "Bond Collective"
MERCHANT_DOMAIN = "bondcollective.com"
MERCHANT_CATEGORY = "coworking"
OFFER_TITLE = "Bond Collective: 20% initial services discount"
OFFER_TERMS = (
    "PerkNation members receive a 20% initial discount on eligible Bond Collective services, "
    "including private office space, dedicated desks, coworking, day passes, and conference rooms. "
    "Bond public starting prices currently list private offices from $500/month, dedicated desks from $500/month, "
    "coworking from $300/month, day passes from $25/day, and conference rooms from $50/hour. "
    "New customer offer; availability and final terms are confirmed by Bond Collective."
)


def favicon_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=256"


def ensure_owner_user(db) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    created = False
    if not user:
        user = User(
            full_name="Billy",
            email=OWNER_EMAIL,
            phone=None,
            password_hash=None,
            role=UserRole.merchant,
            reward_preference=RewardPreference.cash,
            email_verified=True,
        )
        db.add(user)
        db.flush()
        created = True
    else:
        if user.role != UserRole.admin:
            user.role = UserRole.merchant
        user.email_verified = True
        if user.reward_preference != RewardPreference.cash:
            user.reward_preference = RewardPreference.cash
    return user, created


def ensure_profile(db, user: User) -> tuple[MerchantProfile, bool]:
    profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == user.id))
    created = False
    if not profile:
        profile = MerchantProfile(
            owner_user_id=user.id,
            legal_name=MERCHANT_LEGAL_NAME,
            dba_name=MERCHANT_DBA_NAME,
            logo_url=favicon_url(MERCHANT_DOMAIN),
            category=MERCHANT_CATEGORY,
            subscription_tier="growth",
            status="approved",
        )
        db.add(profile)
        db.flush()
        created = True
    else:
        profile.legal_name = MERCHANT_LEGAL_NAME
        profile.dba_name = MERCHANT_DBA_NAME
        profile.logo_url = favicon_url(MERCHANT_DOMAIN)
        profile.category = MERCHANT_CATEGORY
        profile.subscription_tier = "growth"
        profile.status = "approved"
    return profile, created


def ensure_offer(db, user: User, profile: MerchantProfile) -> bool:
    now = datetime.now(timezone.utc)
    starts_at = now - timedelta(days=1)
    ends_at = now + timedelta(days=365)

    offer = db.scalar(
        select(Offer).where(
            Offer.merchant_id == profile.id,
            Offer.title == OFFER_TITLE,
        )
    )
    created = False
    if not offer:
        offer = Offer(
            merchant_id=profile.id,
            location_id=None,
            created_by_user_id=user.id,
            title=OFFER_TITLE,
            offer_type="discount",
            terms_text=OFFER_TERMS,
            reward_rate_cash=Decimal("0.2000"),
            reward_rate_stock=Decimal("0.0000"),
            starts_at=starts_at,
            ends_at=ends_at,
            schedule_rules="Eligible services; confirm availability with Bond Collective",
            daily_cap=None,
            total_cap=None,
            per_user_limit=1,
            approval_status=OfferStatus.approved,
        )
        db.add(offer)
        created = True
    else:
        offer.offer_type = "discount"
        offer.terms_text = OFFER_TERMS
        offer.reward_rate_cash = Decimal("0.2000")
        offer.reward_rate_stock = Decimal("0.0000")
        offer.starts_at = starts_at
        offer.ends_at = ends_at
        offer.schedule_rules = "Eligible services; confirm availability with Bond Collective"
        offer.daily_cap = None
        offer.total_cap = None
        offer.per_user_limit = 1
        offer.approval_status = OfferStatus.approved
    return created


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    with SessionLocal() as db:
        user, user_created = ensure_owner_user(db)
        profile, profile_created = ensure_profile(db, user)
        offer_created = ensure_offer(db, user, profile)
        db.commit()

        print("Bond Collective seed complete.")
        print(f"owner_user_id={user.id}")
        print(f"owner_role={user.role.value}")
        print(f"merchant_profile_id={profile.id}")
        print(f"user_created={user_created}")
        print(f"profile_created={profile_created}")
        print(f"offer_created={offer_created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
