from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Location, MerchantProfile, Offer, OfferStatus, RewardPreference, User, UserRole
from app.services.security import hash_password


def seed_if_empty(db: Session) -> None:
    has_users = db.scalar(select(User.id).limit(1))
    if has_users:
        return

    admin = User(
        full_name="PerkNation Admin",
        email="admin@perknation.dev",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.admin,
        email_verified=True,
    )

    merchant_user = User(
        full_name="Brew District Owner",
        email="merchant@perknation.dev",
        password_hash=hash_password("MerchantPass123!"),
        role=UserRole.merchant,
        email_verified=True,
    )

    consumer = User(
        full_name="Demo Consumer",
        email="user@perknation.dev",
        password_hash=hash_password("UserPass123!"),
        role=UserRole.consumer,
        reward_preference=RewardPreference.cash,
        email_verified=True,
    )

    db.add_all([admin, merchant_user, consumer])
    db.flush()

    merchant_profile = MerchantProfile(
        owner_user_id=merchant_user.id,
        legal_name="Brew District LLC",
        dba_name="Brew District",
        category="coffee",
        subscription_tier="growth",
        status="approved",
    )
    db.add(merchant_profile)
    db.flush()

    location = Location(
        merchant_id=merchant_profile.id,
        name="Brew District Midtown",
        address="101 Main St, Anytown, USA",
        latitude=Decimal("37.7749000"),
        longitude=Decimal("-122.4194000"),
        hours="Mon-Fri 7:00-18:00",
        status="active",
    )
    db.add(location)
    db.flush()

    now = datetime.now(timezone.utc)
    approved_offer = Offer(
        merchant_id=merchant_profile.id,
        location_id=location.id,
        created_by_user_id=merchant_user.id,
        title="Morning Boost",
        offer_type="boost",
        terms_text="Valid before 11AM. Max 2 uses/day.",
        reward_rate_cash=Decimal("0.07"),
        reward_rate_stock=Decimal("0.10"),
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=30),
        schedule_rules="Mon-Fri 7:00-11:00",
        daily_cap=Decimal("250"),
        total_cap=Decimal("5000"),
        per_user_limit=2,
        approval_status=OfferStatus.approved,
    )

    pending_offer = Offer(
        merchant_id=merchant_profile.id,
        location_id=location.id,
        created_by_user_id=merchant_user.id,
        title="Lunch Flash 12%",
        offer_type="flash",
        terms_text="Valid weekdays lunch hours.",
        reward_rate_cash=Decimal("0.12"),
        reward_rate_stock=Decimal("0.15"),
        starts_at=now,
        ends_at=now + timedelta(days=10),
        schedule_rules="Mon-Fri 11:30-14:00",
        daily_cap=Decimal("180"),
        total_cap=Decimal("2500"),
        per_user_limit=1,
        approval_status=OfferStatus.pending,
    )

    db.add_all([approved_offer, pending_offer])
    db.commit()
