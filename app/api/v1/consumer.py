from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from decimal import Decimal
import math

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_roles
from app.db.models import (
    DisputeCase,
    MerchantProfile,
    Offer,
    OfferActivation,
    OfferStatus,
    RestaurantReview,
    ReferralAttribution,
    ReferralEvent,
    ReferralEventType,
    ReferralProfile,
    RewardPreference,
    RewardLedgerEntry,
    RewardState,
    StockConversion,
    SupportTicket,
    Transaction,
    User,
    UserRole,
)
from app.schemas import (
    APIMessage,
    DisputeCreate,
    DisputeOut,
    InvestmentSummaryOut,
    ReferralEventOut,
    OfferOut,
    RestaurantReviewCreate,
    RestaurantReviewOut,
    RestaurantReviewSummaryOut,
    ReferralProfileOut,
    ReferralRedeemRequest,
    ReferralShareRequest,
    RedeemRequest,
    RewardOut,
    StockConversionCreate,
    SupportTicketCreate,
    SupportTicketOut,
    TransactionCreate,
    TransactionOut,
)
from app.services.audit import log_action
from app.services.referrals import (
    build_referral_invite_url,
    count_pending_referrals,
    count_successful_referrals,
    ensure_referral_profile,
    log_referral_event,
    normalize_referral_code,
    qualify_user_referral_if_needed,
)

router = APIRouter(prefix="/consumer", tags=["consumer"])


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two lat/lon points in miles.
    """
    r_miles = 3958.7613
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat / 2) ** 2) + math.cos(p1) * math.cos(p2) * (math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(1 - a, 0)))
    return r_miles * c


def _offer_coordinates(offer: Offer) -> tuple[float | None, float | None]:
    if not offer.location:
        return None, None
    try:
        lat = float(offer.location.latitude)
        lon = float(offer.location.longitude)
        return lat, lon
    except Exception:
        return None, None


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _is_offer_live(offer: Offer, *, now_utc: datetime) -> bool:
    if offer.approval_status != OfferStatus.approved:
        return False
    return _as_utc(offer.starts_at) <= now_utc <= _as_utc(offer.ends_at)


def _hours_since(now_utc: datetime, moment: datetime) -> float:
    dt = _as_utc(moment)
    return max((now_utc - dt).total_seconds() / 3600.0, 0.0)


def _rank_offers_by_acceptance_and_geo(
    offers: list[Offer],
    activation_counts: dict[int, int],
    *,
    now_utc: datetime,
    user_latitude: float | None,
    user_longitude: float | None,
    user_radius_miles: int,
) -> tuple[list[Offer], dict[int, float], dict[int, int]]:
    """
    Rank offers by:
    - direct acceptance volume for the offer (primary signal)
    - local-area acceptance volume around the offer location
    - freshness signal (small tie-breaker)
    - optional proximity signal when caller provides user location
    """

    local_cluster_radius_miles = 2.0

    coords_by_offer: dict[int, tuple[float | None, float | None]] = {
        offer.id: _offer_coordinates(offer) for offer in offers
    }

    score_by_offer: dict[int, float] = {}
    area_acceptance_by_offer: dict[int, int] = {}
    for offer in offers:
        direct_accepts = activation_counts.get(offer.id, 0)

        # Geo-cluster signal: nearby offers with high acceptance lift each other.
        offer_lat, offer_lon = coords_by_offer.get(offer.id, (None, None))
        area_accepts = 0
        for other in offers:
            other_accepts = activation_counts.get(other.id, 0)
            if other_accepts <= 0:
                continue

            other_lat, other_lon = coords_by_offer.get(other.id, (None, None))
            if offer_lat is not None and offer_lon is not None and other_lat is not None and other_lon is not None:
                if _haversine_miles(offer_lat, offer_lon, other_lat, other_lon) <= local_cluster_radius_miles:
                    area_accepts += other_accepts
                continue

            # Fallback when lat/lon is missing: same location_id counts as local area.
            if offer.location_id is not None and offer.location_id == other.location_id:
                area_accepts += other_accepts

        area_acceptance_by_offer[offer.id] = area_accepts

        direct_signal = math.log1p(direct_accepts) * 1.25
        area_signal = math.log1p(area_accepts) * 0.95

        hours_live = _hours_since(now_utc, offer.created_at)
        freshness_signal = max(0.0, 1.0 - min(hours_live / 168.0, 1.0)) * 0.22

        proximity_signal = 0.0
        if (
            user_latitude is not None
            and user_longitude is not None
            and offer_lat is not None
            and offer_lon is not None
            and user_radius_miles > 0
        ):
            dist = _haversine_miles(user_latitude, user_longitude, offer_lat, offer_lon)
            if dist <= user_radius_miles:
                proximity_signal = max(0.0, 1.0 - (dist / float(user_radius_miles))) * 0.28

        score_by_offer[offer.id] = direct_signal + area_signal + freshness_signal + proximity_signal

    ranked = sorted(
        offers,
        key=lambda offer: (
            score_by_offer.get(offer.id, 0.0),
            activation_counts.get(offer.id, 0),
            offer.created_at,
        ),
        reverse=True,
    )
    return ranked, score_by_offer, area_acceptance_by_offer


def _build_referral_profile_out(db: Session, user: User, profile: ReferralProfile | None = None) -> ReferralProfileOut:
    profile = profile or ensure_referral_profile(db, user)

    pending = count_pending_referrals(db, user.id)
    successful = count_successful_referrals(db, user.id)

    recent_events = db.scalars(
        select(ReferralEvent)
        .where(ReferralEvent.profile_id == profile.id)
        .order_by(desc(ReferralEvent.created_at), desc(ReferralEvent.id))
        .limit(10)
    ).all()

    invite_url = build_referral_invite_url(profile.referral_code)
    return ReferralProfileOut(
        referral_code=profile.referral_code,
        invite_url=invite_url,
        qr_payload=invite_url,
        invites_sent=profile.invites_sent,
        pending_referrals=pending,
        successful_referrals=successful,
        recent_events=[ReferralEventOut.model_validate(event) for event in recent_events],
    )


def _resolve_review_target(
    db: Session,
    *,
    offer_id: int | None,
    merchant_id: int | None,
) -> tuple[int, int | None]:
    resolved_merchant_id = merchant_id
    resolved_offer_id = offer_id

    if offer_id is not None:
        offer = db.get(Offer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if resolved_merchant_id is not None and resolved_merchant_id != offer.merchant_id:
            raise HTTPException(status_code=400, detail="Offer does not belong to merchant")
        resolved_merchant_id = offer.merchant_id

    if resolved_merchant_id is None:
        raise HTTPException(status_code=400, detail="merchant_id or offer_id is required")

    merchant = db.get(MerchantProfile, resolved_merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    return int(resolved_merchant_id), resolved_offer_id


@router.get("/referrals/profile", response_model=ReferralProfileOut)
def get_referral_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> ReferralProfileOut:
    profile = ensure_referral_profile(db, current_user)
    db.commit()
    return _build_referral_profile_out(db, current_user, profile=profile)


@router.post("/referrals/share", response_model=ReferralProfileOut)
def share_referral_link(
    payload: ReferralShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> ReferralProfileOut:
    profile = ensure_referral_profile(db, current_user)
    profile.invites_sent += 1

    channel = (payload.channel or "link").strip().lower() or "link"
    log_referral_event(db, profile, ReferralEventType.share, channel=channel)

    log_action(
        db,
        actor=current_user,
        action="referral.share",
        object_type="referral_profile",
        object_id=str(profile.id),
        after_snapshot=f"channel={channel};invites_sent={profile.invites_sent}",
    )

    db.commit()
    return _build_referral_profile_out(db, current_user, profile=profile)


@router.post("/referrals/redeem", response_model=APIMessage)
def redeem_referral_code(
    payload: ReferralRedeemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> APIMessage:
    code = normalize_referral_code(payload.referral_code)
    if not code:
        raise HTTPException(status_code=400, detail="Referral code is required")

    existing = db.scalar(
        select(ReferralAttribution).where(ReferralAttribution.referred_user_id == current_user.id)
    )
    if existing:
        if normalize_referral_code(existing.referral_code_used) == code:
            return APIMessage(message="Referral already linked")
        raise HTTPException(status_code=409, detail="User is already linked to a referral code")

    profile = db.scalar(select(ReferralProfile).where(ReferralProfile.referral_code == code))
    if not profile:
        raise HTTPException(status_code=404, detail="Referral code not found")

    if profile.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot redeem your own referral code")

    db.add(
        ReferralAttribution(
            referrer_user_id=profile.user_id,
            referred_user_id=current_user.id,
            referral_code_used=profile.referral_code,
        )
    )

    log_referral_event(
        db,
        profile,
        ReferralEventType.redeem,
        channel="app",
        metadata_text=f"referred_user_id={current_user.id}",
    )

    log_action(
        db,
        actor=current_user,
        action="referral.redeem",
        object_type="referral_profile",
        object_id=str(profile.id),
        after_snapshot=f"referred_user_id={current_user.id}",
    )

    db.commit()
    return APIMessage(message="Referral code linked")


@router.get("/offers", response_model=list[OfferOut])
def list_offers(
    category: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> list[OfferOut]:
    now = datetime.now(timezone.utc)
    # Eager-load merchant so OfferOut.merchant_name/logo_url are always populated
    # without relying on lazy-loading during response serialization.
    query = select(Offer).options(selectinload(Offer.merchant), selectinload(Offer.location)).where(
        and_(
            Offer.approval_status != OfferStatus.denied,
            Offer.ends_at >= (now - timedelta(days=1)),
        )
    )

    if category:
        query = query.where(Offer.merchant.has(category=category))

    offers = db.scalars(query.order_by(Offer.created_at.desc())).all()
    if not offers:
        return []

    # Keep offer inventory consistent for signed-in consumer surfaces.
    # We still use geo inputs for ranking (nearby first), nearby alerts, and
    # badges, but we do not hard-filter out non-local offers here.

    offer_ids = [offer.id for offer in offers]
    activation_counts_rows = db.execute(
        select(OfferActivation.offer_id, func.count(OfferActivation.id))
        .where(OfferActivation.offer_id.in_(offer_ids))
        .group_by(OfferActivation.offer_id)
    ).all()
    activation_counts: dict[int, int] = {int(row[0]): int(row[1]) for row in activation_counts_rows}

    activated_offer_ids = set(
        db.scalars(
            select(OfferActivation.offer_id).where(
                OfferActivation.user_id == current_user.id,
                OfferActivation.offer_id.in_(offer_ids),
            )
        ).all()
    )

    is_live_by_offer_id: dict[int, bool] = {
        offer.id: _is_offer_live(offer, now_utc=now)
        for offer in offers
    }

    live_activated_offer_ids = {
        offer_id
        for offer_id in activated_offer_ids
        if is_live_by_offer_id.get(offer_id, False)
    }
    early_bird_opted_in_offer_ids = {
        offer_id
        for offer_id in activated_offer_ids
        if not is_live_by_offer_id.get(offer_id, False)
    }

    merchant_ids = {offer.merchant_id for offer in offers}
    review_avg_by_merchant: dict[int, float] = {}
    review_count_by_merchant: dict[int, int] = {}
    my_review_by_merchant: dict[int, int] = {}
    if merchant_ids:
        review_rows = db.execute(
            select(
                RestaurantReview.merchant_id,
                func.avg(RestaurantReview.overall_hearts),
                func.count(RestaurantReview.id),
            )
            .where(RestaurantReview.merchant_id.in_(merchant_ids))
            .group_by(RestaurantReview.merchant_id)
        ).all()
        review_avg_by_merchant = {
            int(row[0]): float(row[1] or 0.0)
            for row in review_rows
        }
        review_count_by_merchant = {
            int(row[0]): int(row[2] or 0)
            for row in review_rows
        }

        my_review_rows = db.execute(
            select(RestaurantReview.merchant_id, RestaurantReview.overall_hearts).where(
                RestaurantReview.user_id == current_user.id,
                RestaurantReview.merchant_id.in_(merchant_ids),
            )
        ).all()
        my_review_by_merchant = {
            int(row[0]): int(row[1])
            for row in my_review_rows
        }

    offers, score_by_offer, area_acceptance_by_offer = _rank_offers_by_acceptance_and_geo(
        offers,
        activation_counts,
        now_utc=now,
        user_latitude=latitude,
        user_longitude=longitude,
        user_radius_miles=current_user.alert_radius_miles,
    )

    offers = sorted(
        offers,
        key=lambda offer: (
            is_live_by_offer_id.get(offer.id, False),
            score_by_offer.get(offer.id, 0.0),
            activation_counts.get(offer.id, 0),
            offer.created_at,
        ),
        reverse=True,
    )

    # Mark a top slice of ranked offers as "popular" so clients can render a
    # consistent badge even when the marketplace is early/low-volume.
    live_offers = [offer for offer in offers if is_live_by_offer_id.get(offer.id, False)]
    if live_offers:
        popular_count = min(len(live_offers), max(1, math.ceil(len(live_offers) * 0.35)))
        popular_offer_ids = {offer.id for offer in live_offers[:popular_count]}
    else:
        popular_offer_ids = set()

    result: list[OfferOut] = []
    for offer in offers:
        dto = OfferOut.model_validate(offer).model_copy(
            update={
                "is_activated": offer.id in live_activated_offer_ids,
                "is_live_offer": is_live_by_offer_id.get(offer.id, False),
                "is_coming_soon": not is_live_by_offer_id.get(offer.id, False),
                "is_early_bird_opted_in": offer.id in early_bird_opted_in_offer_ids,
                "early_bird_count": (
                    activation_counts.get(offer.id, 0)
                    if not is_live_by_offer_id.get(offer.id, False)
                    else 0
                ),
                "is_popular": offer.id in popular_offer_ids,
                "activation_count": activation_counts.get(offer.id, 0),
                "area_activation_count": area_acceptance_by_offer.get(offer.id, 0),
                "rank_score": round(score_by_offer.get(offer.id, 0.0), 4),
                "merchant_category": offer.merchant.category if offer.merchant else None,
                "review_avg_hearts": round(review_avg_by_merchant.get(offer.merchant_id, 0.0), 2),
                "review_count": review_count_by_merchant.get(offer.merchant_id, 0),
                "my_review_hearts": my_review_by_merchant.get(offer.merchant_id),
            }
        )
        result.append(dto)

    return result


@router.get("/reviews", response_model=list[RestaurantReviewOut])
def list_reviews(
    merchant_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    mine_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> list[RestaurantReviewOut]:
    resolved_merchant_id = merchant_id
    if offer_id is not None:
        offer = db.get(Offer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if resolved_merchant_id is not None and resolved_merchant_id != offer.merchant_id:
            raise HTTPException(status_code=400, detail="Offer does not belong to merchant")
        resolved_merchant_id = offer.merchant_id

    query = select(RestaurantReview).options(selectinload(RestaurantReview.merchant))
    if resolved_merchant_id is not None:
        query = query.where(RestaurantReview.merchant_id == resolved_merchant_id)
    if offer_id is not None:
        query = query.where(RestaurantReview.offer_id == offer_id)

    if mine_only or resolved_merchant_id is None:
        query = query.where(RestaurantReview.user_id == current_user.id)

    reviews = db.scalars(
        query.order_by(desc(RestaurantReview.updated_at), desc(RestaurantReview.id)).limit(100)
    ).all()
    return [RestaurantReviewOut.model_validate(r) for r in reviews]


@router.get("/reviews/summary", response_model=list[RestaurantReviewSummaryOut])
def list_review_summaries(
    merchant_id: Optional[int] = None,
    offer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> list[RestaurantReviewSummaryOut]:
    resolved_merchant_id = merchant_id
    if offer_id is not None:
        offer = db.get(Offer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if resolved_merchant_id is not None and resolved_merchant_id != offer.merchant_id:
            raise HTTPException(status_code=400, detail="Offer does not belong to merchant")
        resolved_merchant_id = offer.merchant_id

    summary_query = select(
        RestaurantReview.merchant_id,
        func.avg(RestaurantReview.overall_hearts),
        func.count(RestaurantReview.id),
    ).group_by(RestaurantReview.merchant_id)

    if resolved_merchant_id is not None:
        summary_query = summary_query.where(RestaurantReview.merchant_id == resolved_merchant_id)

    summary_rows = db.execute(summary_query).all()
    if not summary_rows:
        return []

    merchant_ids = [int(row[0]) for row in summary_rows]
    merchant_rows = db.execute(
        select(MerchantProfile.id, MerchantProfile.dba_name).where(MerchantProfile.id.in_(merchant_ids))
    ).all()
    merchant_name_by_id = {int(row[0]): str(row[1]) for row in merchant_rows}

    my_rows = db.execute(
        select(RestaurantReview.merchant_id, RestaurantReview.overall_hearts).where(
            RestaurantReview.user_id == current_user.id,
            RestaurantReview.merchant_id.in_(merchant_ids),
        )
    ).all()
    my_review_by_merchant = {int(row[0]): int(row[1]) for row in my_rows}

    return [
        RestaurantReviewSummaryOut(
            merchant_id=int(row[0]),
            merchant_name=merchant_name_by_id.get(int(row[0]), f"Merchant #{int(row[0])}"),
            review_count=int(row[2] or 0),
            avg_overall_hearts=round(float(row[1] or 0.0), 2),
            my_review_hearts=my_review_by_merchant.get(int(row[0])),
        )
        for row in summary_rows
    ]


@router.post("/reviews", response_model=RestaurantReviewOut, status_code=status.HTTP_201_CREATED)
def upsert_review(
    payload: RestaurantReviewCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> RestaurantReviewOut:
    merchant_id, resolved_offer_id = _resolve_review_target(
        db,
        offer_id=payload.offer_id,
        merchant_id=payload.merchant_id,
    )

    overall = int(payload.overall_hearts)
    plates = int(payload.plates_hearts or overall)
    sides = int(payload.sides_hearts or overall)
    umami = int(payload.umami_hearts or overall)
    review_text = (payload.review_text or "").strip() or None

    existing = db.scalar(
        select(RestaurantReview).where(
            RestaurantReview.user_id == current_user.id,
            RestaurantReview.merchant_id == merchant_id,
        )
    )

    if existing:
        existing.offer_id = resolved_offer_id
        existing.overall_hearts = overall
        existing.plates_hearts = plates
        existing.sides_hearts = sides
        existing.umami_hearts = umami
        existing.review_text = review_text
        review = existing
        response.status_code = status.HTTP_200_OK
    else:
        review = RestaurantReview(
            user_id=current_user.id,
            merchant_id=merchant_id,
            offer_id=resolved_offer_id,
            overall_hearts=overall,
            plates_hearts=plates,
            sides_hearts=sides,
            umami_hearts=umami,
            review_text=review_text,
        )
        db.add(review)

    log_action(
        db,
        actor=current_user,
        action="review.upsert",
        object_type="restaurant_review",
        object_id=str(review.id if review.id else "pending"),
        after_snapshot=f"merchant_id={merchant_id};overall={overall}",
    )

    db.commit()
    db.refresh(review)
    return RestaurantReviewOut.model_validate(review)


@router.post("/offers/{offer_id}/activate", response_model=APIMessage)
def activate_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> APIMessage:
    offer = db.get(Offer, offer_id)
    if not offer or offer.approval_status == OfferStatus.denied:
        raise HTTPException(status_code=404, detail="Offer not found")

    is_live_offer = _is_offer_live(offer, now_utc=datetime.now(timezone.utc))

    existing = db.scalar(
        select(OfferActivation).where(
            OfferActivation.offer_id == offer_id,
            OfferActivation.user_id == current_user.id,
        )
    )
    if existing:
        if is_live_offer:
            return APIMessage(message="Offer already activated")
        return APIMessage(message="Early bird already enabled")

    activation = OfferActivation(offer_id=offer_id, user_id=current_user.id)
    db.add(activation)

    log_action(
        db,
        actor=current_user,
        action="offer.activate" if is_live_offer else "offer.early_bird_opt_in",
        object_type="offer",
        object_id=str(offer_id),
        after_snapshot=f"user_id={current_user.id};mode={'live' if is_live_offer else 'early_bird'}",
    )

    db.commit()
    if is_live_offer:
        return APIMessage(message="Offer activated")
    return APIMessage(message="Early bird opt-in saved. We will notify you when this offer goes live.")


@router.post("/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> TransactionOut:
    offer = db.get(Offer, payload.offer_id) if payload.offer_id else None

    if payload.offer_id and not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer and not _is_offer_live(offer, now_utc=datetime.now(timezone.utc)):
        raise HTTPException(status_code=400, detail="This offer is coming soon. Purchase simulation is disabled.")

    merchant_id = payload.merchant_id
    location_id = payload.location_id

    if offer:
        merchant_id = offer.merchant_id
        location_id = offer.location_id

    transaction = Transaction(
        user_id=current_user.id,
        merchant_id=merchant_id,
        location_id=location_id,
        offer_id=payload.offer_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        rail_type=payload.rail_type,
    )
    db.add(transaction)
    db.flush()

    # Per product: rewards accrue in cash by default. Stock is an optional
    # conversion action from available cash rewards (handled separately).
    reward_type = RewardPreference.cash
    reward_rate = offer.reward_rate_cash if offer else Decimal("0.01")

    reward_amount = (payload.amount * reward_rate).quantize(Decimal("0.01"))

    reward_entry = RewardLedgerEntry(
        txn_id=transaction.id,
        user_id=current_user.id,
        merchant_id=merchant_id,
        offer_id=payload.offer_id,
        reward_type=reward_type,
        rate_applied=reward_rate,
        reward_amount=reward_amount,
        state=RewardState.pending,
    )
    db.add(reward_entry)

    # First completed transaction for a referred user qualifies the referral.
    qualify_user_referral_if_needed(db, current_user.id)

    log_action(
        db,
        actor=current_user,
        action="transaction.create",
        object_type="transaction",
        object_id=str(transaction.id),
        after_snapshot=f"amount={payload.amount};reward={reward_amount}",
    )

    db.commit()
    db.refresh(transaction)
    return TransactionOut.model_validate(transaction)


def _quantize_usd(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _investment_summary(db: Session, user_id: int) -> InvestmentSummaryOut:
    from sqlalchemy import func

    increment = Decimal("25.00")

    cash_available = (
        db.scalar(
            select(func.coalesce(func.sum(RewardLedgerEntry.reward_amount), 0))
            .where(
                RewardLedgerEntry.user_id == user_id,
                RewardLedgerEntry.state == RewardState.available,
                RewardLedgerEntry.reward_type == RewardPreference.cash,
            )
        )
        or Decimal("0")
    )

    cash_available = _quantize_usd(cash_available)

    stock_balance = (
        db.scalar(
            select(func.coalesce(func.sum(StockConversion.amount_usd), 0)).where(
                StockConversion.user_id == user_id
            )
        )
        or Decimal("0")
    )
    stock_balance = _quantize_usd(stock_balance)

    convertible_now = _quantize_usd((cash_available // increment) * increment)

    remainder = cash_available % increment
    until_next = increment if remainder == 0 else (increment - remainder)
    until_next = _quantize_usd(until_next)

    return InvestmentSummaryOut(
        cash_available=cash_available,
        convertible_now=convertible_now,
        until_next_unlock=until_next,
        stock_balance_usd=stock_balance,
    )


@router.get("/investments/summary", response_model=InvestmentSummaryOut)
def investment_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> InvestmentSummaryOut:
    return _investment_summary(db, current_user.id)


@router.post("/investments/convert", response_model=InvestmentSummaryOut)
def convert_cash_to_stocks(
    payload: StockConversionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> InvestmentSummaryOut:
    """
    Convert available cash rewards to Stock Vault balance.

    Constraints:
    - Minimum $25
    - Must be in $25 increments
    """

    increment = Decimal("25.00")
    amount = _quantize_usd(payload.amount_usd)

    if amount < increment:
        raise HTTPException(status_code=400, detail="Minimum conversion is $25")

    if amount % increment != 0:
        raise HTTPException(status_code=400, detail="Conversion amount must be in $25 increments")

    # Pull available cash rewards oldest-first and consume exactly `amount`.
    available_rewards = db.scalars(
        select(RewardLedgerEntry)
        .where(
            RewardLedgerEntry.user_id == current_user.id,
            RewardLedgerEntry.state == RewardState.available,
            RewardLedgerEntry.reward_type == RewardPreference.cash,
        )
        .order_by(RewardLedgerEntry.created_at.asc(), RewardLedgerEntry.id.asc())
    ).all()

    total_available = sum((r.reward_amount for r in available_rewards), Decimal("0"))
    total_available = _quantize_usd(total_available)
    if total_available < amount:
        raise HTTPException(status_code=400, detail="Insufficient available cash rewards")

    remaining = amount
    for reward in available_rewards:
        if remaining <= 0:
            break

        reward_amount = _quantize_usd(reward.reward_amount)

        if reward_amount <= remaining:
            reward.state = RewardState.paid
            remaining = _quantize_usd(remaining - reward_amount)
            continue

        # Split the reward entry so we can consume the exact remaining amount.
        consume = remaining
        leftover = _quantize_usd(reward_amount - consume)

        reward.reward_amount = consume
        reward.state = RewardState.paid

        db.add(
            RewardLedgerEntry(
                txn_id=reward.txn_id,
                user_id=reward.user_id,
                merchant_id=reward.merchant_id,
                offer_id=reward.offer_id,
                reward_type=reward.reward_type,
                rate_applied=reward.rate_applied,
                reward_amount=leftover,
                funding_source=reward.funding_source,
                state=RewardState.available,
                created_at=reward.created_at,
                settled_at=reward.settled_at,
            )
        )

        remaining = Decimal("0.00")
        break

    if remaining != Decimal("0.00"):
        # Defensive: should never happen given the earlier total check.
        raise HTTPException(status_code=500, detail="Conversion failed to allocate rewards")

    conversion = StockConversion(user_id=current_user.id, amount_usd=amount)
    db.add(conversion)

    log_action(
        db,
        actor=current_user,
        action="investment.convert",
        object_type="stock_conversion",
        object_id="pending",
        after_snapshot=f"amount_usd={amount}",
    )

    db.commit()
    return _investment_summary(db, current_user.id)


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> list[TransactionOut]:
    transactions = db.scalars(
        select(Transaction)
        .options(selectinload(Transaction.offer).selectinload(Offer.merchant))
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.occurred_at.desc())
    ).all()
    return [TransactionOut.model_validate(txn) for txn in transactions]


@router.get("/rewards", response_model=list[RewardOut])
def list_rewards(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> list[RewardOut]:
    rewards = db.scalars(
        select(RewardLedgerEntry)
        .options(
            selectinload(RewardLedgerEntry.transaction)
            .selectinload(Transaction.offer)
            .selectinload(Offer.merchant)
        )
        .where(RewardLedgerEntry.user_id == current_user.id)
        .order_by(RewardLedgerEntry.created_at.desc())
    ).all()
    return [RewardOut.model_validate(r) for r in rewards]


@router.post("/rewards/settle", response_model=APIMessage)
def settle_pending_rewards(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> APIMessage:
    rewards = db.scalars(
        select(RewardLedgerEntry).where(
            RewardLedgerEntry.user_id == current_user.id,
            RewardLedgerEntry.state == RewardState.pending,
        )
    ).all()

    if not rewards:
        return APIMessage(message="No pending rewards to settle")

    settled_at = datetime.now(timezone.utc)
    for reward in rewards:
        reward.state = RewardState.available
        reward.settled_at = settled_at

    log_action(
        db,
        actor=current_user,
        action="reward.settle.pending",
        object_type="reward",
        object_id=",".join(str(reward.id) for reward in rewards),
    )

    db.commit()
    return APIMessage(message=f"Settled {len(rewards)} reward(s)")


@router.post("/rewards/redeem", response_model=APIMessage)
def redeem_rewards(
    payload: RedeemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> APIMessage:
    rewards = db.scalars(
        select(RewardLedgerEntry).where(
            RewardLedgerEntry.id.in_(payload.reward_ids),
            RewardLedgerEntry.user_id == current_user.id,
        )
    ).all()

    if len(rewards) != len(payload.reward_ids):
        raise HTTPException(status_code=404, detail="One or more rewards not found")

    unavailable = [r.id for r in rewards if r.state != RewardState.available]
    if unavailable:
        raise HTTPException(status_code=400, detail=f"Rewards not redeemable: {unavailable}")

    for reward in rewards:
        reward.state = RewardState.paid

    log_action(
        db,
        actor=current_user,
        action="reward.redeem",
        object_type="reward",
        object_id=",".join(str(r.id) for r in rewards),
    )

    db.commit()
    return APIMessage(message="Rewards redeemed")


@router.post("/support/tickets", response_model=SupportTicketOut, status_code=status.HTTP_201_CREATED)
def create_support_ticket(
    payload: SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> SupportTicketOut:
    ticket = SupportTicket(
        user_id=current_user.id,
        txn_id=payload.txn_id,
        category=payload.category,
        subject=payload.subject,
        message=payload.message,
    )
    db.add(ticket)

    log_action(
        db,
        actor=current_user,
        action="support.ticket.create",
        object_type="ticket",
        object_id="pending",
    )

    db.commit()
    db.refresh(ticket)
    return SupportTicketOut.model_validate(ticket)


@router.get("/support/tickets", response_model=list[SupportTicketOut])
def list_support_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> list[SupportTicketOut]:
    tickets = db.scalars(
        select(SupportTicket)
        .where(SupportTicket.user_id == current_user.id)
        .order_by(SupportTicket.created_at.desc())
    ).all()
    return [SupportTicketOut.model_validate(ticket) for ticket in tickets]


@router.post("/disputes", response_model=DisputeOut, status_code=status.HTTP_201_CREATED)
def create_dispute(
    payload: DisputeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.consumer)),
) -> DisputeOut:
    txn = db.get(Transaction, payload.txn_id)
    if not txn or txn.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    dispute = DisputeCase(
        txn_id=txn.id,
        user_id=current_user.id,
        reason=payload.reason,
        evidence=payload.evidence,
    )
    db.add(dispute)

    log_action(
        db,
        actor=current_user,
        action="dispute.create",
        object_type="dispute",
        object_id="pending",
    )

    db.commit()
    db.refresh(dispute)
    return DisputeOut.model_validate(dispute)
