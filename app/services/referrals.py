from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    ReferralAttribution,
    ReferralAttributionStatus,
    ReferralEvent,
    ReferralEventType,
    ReferralProfile,
    User,
)

REFERRAL_SUFFIX_ALPHABET = string.ascii_uppercase + string.digits


def normalize_referral_code(raw_code: str) -> str:
    return raw_code.strip().upper()


def build_referral_invite_url(referral_code: str) -> str:
    """
    Build the public invite URL for a referral code.

    If REFERRAL_INVITE_BASE_URL contains `{code}`, it is replaced directly.
    Otherwise, `code` is appended/merged as a query parameter.
    """

    base = (settings.referral_invite_base_url or "https://perknation.app/invite").strip()
    if "{code}" in base:
        return base.replace("{code}", quote(referral_code, safe=""))

    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["code"] = referral_code
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def ensure_referral_profile(db: Session, user: User) -> ReferralProfile:
    existing = db.scalar(select(ReferralProfile).where(ReferralProfile.user_id == user.id))
    if existing:
        return existing

    if user.id is None:
        db.flush()

    user_id = user.id
    if user_id is None:
        raise RuntimeError("Cannot create referral profile without a persisted user id")

    profile: ReferralProfile | None = None
    for _ in range(20):
        suffix = "".join(secrets.choice(REFERRAL_SUFFIX_ALPHABET) for _ in range(4))
        code = f"PKN-{user_id:06d}-{suffix}"
        in_use = db.scalar(select(ReferralProfile.id).where(ReferralProfile.referral_code == code))
        if in_use:
            continue
        profile = ReferralProfile(user_id=user_id, referral_code=code)
        db.add(profile)
        db.flush()
        break

    if not profile:
        raise RuntimeError("Failed to generate a unique referral code")

    return profile


def log_referral_event(
    db: Session,
    profile: ReferralProfile,
    event_type: ReferralEventType,
    *,
    channel: str | None = None,
    metadata_text: str | None = None,
) -> None:
    db.add(
        ReferralEvent(
            profile_id=profile.id,
            event_type=event_type,
            channel=channel,
            metadata_text=metadata_text,
        )
    )


def count_pending_referrals(db: Session, referrer_user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(ReferralAttribution.id)).where(
                ReferralAttribution.referrer_user_id == referrer_user_id,
                ReferralAttribution.status == ReferralAttributionStatus.linked,
            )
        )
        or 0
    )


def count_successful_referrals(db: Session, referrer_user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(ReferralAttribution.id)).where(
                ReferralAttribution.referrer_user_id == referrer_user_id,
                ReferralAttribution.status == ReferralAttributionStatus.qualified,
            )
        )
        or 0
    )


def qualify_user_referral_if_needed(db: Session, user_id: int) -> None:
    """
    Marks a linked referral as qualified after the referred user transacts.
    """

    attribution = db.scalar(
        select(ReferralAttribution).where(
            ReferralAttribution.referred_user_id == user_id,
            ReferralAttribution.status == ReferralAttributionStatus.linked,
        )
    )
    if not attribution:
        return

    attribution.status = ReferralAttributionStatus.qualified
    attribution.qualified_at = datetime.now(timezone.utc)

    referrer_profile = db.scalar(
        select(ReferralProfile).where(ReferralProfile.user_id == attribution.referrer_user_id)
    )
    if referrer_profile:
        referrer_profile.successful_referrals += 1
        log_referral_event(
            db,
            referrer_profile,
            ReferralEventType.qualify,
            channel="system",
            metadata_text=f"referred_user_id={user_id}",
        )

