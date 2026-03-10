from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_roles
from app.db.models import Location, MerchantProfile, Offer, OfferActivation, Transaction, User, UserRole
from app.schemas import APIMessage, LocationCreate, LocationOut, MerchantProfileCreate, OfferCreate, OfferOut
from app.services.audit import log_action

router = APIRouter(prefix="/merchant", tags=["merchant"])


def _get_merchant_profile_or_404(db: Session, user_id: int) -> MerchantProfile:
    profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Merchant profile not found")
    return profile


@router.post("/profile", response_model=APIMessage, status_code=status.HTTP_201_CREATED)
def create_or_update_profile(
    payload: MerchantProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.merchant)),
) -> APIMessage:
    profile = db.scalar(select(MerchantProfile).where(MerchantProfile.owner_user_id == current_user.id))

    if profile:
        profile.legal_name = payload.legal_name
        profile.dba_name = payload.dba_name
        profile.category = payload.category
        action = "merchant.profile.update"
    else:
        profile = MerchantProfile(
            owner_user_id=current_user.id,
            legal_name=payload.legal_name,
            dba_name=payload.dba_name,
            category=payload.category,
            status="pending",
        )
        db.add(profile)
        action = "merchant.profile.create"

    log_action(db, actor=current_user, action=action, object_type="merchant_profile", object_id=str(current_user.id))

    db.commit()
    return APIMessage(message="Merchant profile saved")


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def add_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.merchant)),
) -> LocationOut:
    profile = _get_merchant_profile_or_404(db, current_user.id)

    location = Location(
        merchant_id=profile.id,
        name=payload.name,
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        hours=payload.hours,
        status="active",
    )
    db.add(location)

    log_action(
        db,
        actor=current_user,
        action="merchant.location.create",
        object_type="location",
        object_id="pending",
    )

    db.commit()
    db.refresh(location)
    return LocationOut.model_validate(location)


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.merchant)),
) -> list[LocationOut]:
    profile = _get_merchant_profile_or_404(db, current_user.id)
    locations = db.scalars(
        select(Location)
        .where(Location.merchant_id == profile.id)
        .order_by(Location.id.desc())
    ).all()
    return [LocationOut.model_validate(location) for location in locations]


@router.post("/offers", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(
    payload: OfferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.merchant)),
) -> OfferOut:
    profile = _get_merchant_profile_or_404(db, current_user.id)

    if payload.location_id:
        location_matches = any(location.id == payload.location_id for location in profile.locations)
        if not location_matches:
            raise HTTPException(status_code=400, detail="Location does not belong to this merchant")

    offer = Offer(
        merchant_id=profile.id,
        location_id=payload.location_id,
        created_by_user_id=current_user.id,
        title=payload.title,
        offer_type=payload.offer_type,
        terms_text=payload.terms_text,
        reward_rate_cash=payload.reward_rate_cash,
        reward_rate_stock=payload.reward_rate_stock,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        schedule_rules=payload.schedule_rules,
        daily_cap=payload.daily_cap,
        total_cap=payload.total_cap,
        per_user_limit=payload.per_user_limit,
    )
    db.add(offer)

    log_action(db, actor=current_user, action="merchant.offer.create", object_type="offer", object_id="pending")

    db.commit()
    db.refresh(offer)
    return OfferOut.model_validate(offer)


@router.get("/offers", response_model=list[OfferOut])
def list_merchant_offers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.merchant)),
) -> list[OfferOut]:
    profile = _get_merchant_profile_or_404(db, current_user.id)
    offers = db.scalars(
        select(Offer)
        .options(selectinload(Offer.merchant), selectinload(Offer.location))
        .where(Offer.merchant_id == profile.id)
        .order_by(Offer.created_at.desc())
    ).all()
    return [OfferOut.model_validate(offer) for offer in offers]


@router.get("/metrics")
def metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.merchant)),
) -> dict[str, str]:
    profile = _get_merchant_profile_or_404(db, current_user.id)

    offer_ids = db.scalars(select(Offer.id).where(Offer.merchant_id == profile.id)).all()

    activations = 0
    transactions = 0
    total_volume = Decimal("0")

    if offer_ids:
        activations = db.scalar(select(func.count()).where(OfferActivation.offer_id.in_(offer_ids))) or 0

    transactions = db.scalar(select(func.count()).where(Transaction.merchant_id == profile.id)) or 0
    total_volume = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.merchant_id == profile.id)) or Decimal("0")

    return {
        "impressions_estimate": str(activations * 5 + 100),
        "activations": str(activations),
        "attributed_transactions": str(transactions),
        "attributed_volume_usd": str(total_volume),
    }
