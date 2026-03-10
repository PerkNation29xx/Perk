import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import RewardPreference, User, UserRole
from app.schemas import (
    APIMessage,
    EmailVerificationRequest,
    EmailVerificationRequestResponse,
    EmailVerificationVerify,
    LoginRequest,
    RegisterResponse,
    TokenResponse,
    UserOut,
    UserPreferencesUpdate,
    UserRegister,
)
from app.core.config import settings
from app.services.audit import log_action
from app.services.referrals import ensure_referral_profile
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_verification_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _new_verification_code() -> str:
    # Human-friendly 6-digit numeric code.
    return f"{secrets.randbelow(1_000_000):06d}"


def _issue_email_verification(user: User) -> str:
    code = _new_verification_code()
    user.email_verified = False
    user.email_verification_code_hash = _hash_verification_code(code)
    user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.email_verification_code_ttl_minutes
    )
    return code


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> RegisterResponse:
    email = _normalize_email(payload.email)
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    phone = payload.phone.strip() if payload.phone else None
    if phone == "":
        phone = None
    if phone:
        existing_phone = db.scalar(select(User).where(User.phone == phone))
        if existing_phone:
            raise HTTPException(status_code=409, detail="Phone already registered")

    user = User(
        full_name=payload.full_name,
        email=email,
        phone=phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
        # Rewards accrue in cash by default. Stock is a conversion action from
        # available cash rewards (separate endpoint).
        reward_preference=RewardPreference.cash,
        notifications_enabled=payload.notifications_enabled,
        location_consent=payload.location_consent,
        alert_radius_miles=5 if payload.alert_radius_miles not in (2, 5, 10) else payload.alert_radius_miles,
        notification_categories=(payload.notification_categories.strip() if payload.notification_categories else None),
    )
    verification_code = _issue_email_verification(user)
    db.add(user)
    try:
        db.flush()
        ensure_referral_profile(db, user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email or phone already registered") from exc

    log_action(
        db,
        actor=user,
        action="user.register",
        object_type="user",
        object_id=str(user.id),
        after_snapshot=f"role={user.role.value}",
    )

    db.commit()
    db.refresh(user)
    if settings.dev_expose_email_verification_code:
        logger.info("Dev email verification code for %s: %s", user.email, verification_code)

    return RegisterResponse(
        user=UserOut.model_validate(user),
        verification_required=True,
        verification_code=verification_code if settings.dev_expose_email_verification_code else None,
    )


@router.post("/email/verification/request", response_model=EmailVerificationRequestResponse)
def request_email_verification(
    payload: EmailVerificationRequest, db: Session = Depends(get_db)
) -> EmailVerificationRequestResponse:
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email_verified:
        return EmailVerificationRequestResponse(message="Email already verified")

    verification_code = _issue_email_verification(user)
    db.commit()

    if settings.dev_expose_email_verification_code:
        logger.info("Dev email verification code for %s: %s", user.email, verification_code)

    return EmailVerificationRequestResponse(
        message="Verification code issued",
        verification_code=verification_code if settings.dev_expose_email_verification_code else None,
    )


@router.post("/email/verify", response_model=APIMessage)
def verify_email(payload: EmailVerificationVerify, db: Session = Depends(get_db)) -> APIMessage:
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email_verified:
        return APIMessage(message="Email already verified")

    if not user.email_verification_code_hash or not user.email_verification_expires_at:
        raise HTTPException(status_code=400, detail="No active verification code. Request a new code.")

    expires_at = user.email_verification_expires_at
    now_utc = datetime.now(timezone.utc)
    # SQLite typically returns naive datetimes; treat them as UTC.
    if expires_at.tzinfo is None:
        if now_utc.replace(tzinfo=None) > expires_at:
            raise HTTPException(status_code=400, detail="Verification code expired. Request a new code.")
    else:
        if now_utc > expires_at:
            raise HTTPException(status_code=400, detail="Verification code expired. Request a new code.")

    if _hash_verification_code(payload.code.strip()) != user.email_verification_code_hash:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    user.email_verified = True
    user.email_verification_code_hash = None
    user.email_verification_expires_at = None

    log_action(db, actor=user, action="user.email.verify", object_type="user", object_id=str(user.id))

    db.commit()
    return APIMessage(message="Email verified")


@router.post("/token", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """
    Update the current user's preferences.

    Rewards accrue in cash by default. Consumers can convert cash to Stock Vault
    via a separate endpoint; this endpoint only manages permissions.
    """

    changed_fields: list[str] = []

    if payload.reward_preference is not None:
        # Per product: rewards accrue in cash by default. Stock is a conversion
        # action from cash (separate endpoint), not an earning preference.
        if payload.reward_preference != RewardPreference.cash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reward preference is fixed to cash")
        current_user.reward_preference = RewardPreference.cash
        changed_fields.append("reward_preference")

    if payload.notifications_enabled is not None:
        current_user.notifications_enabled = payload.notifications_enabled
        changed_fields.append("notifications_enabled")

    if payload.location_consent is not None:
        current_user.location_consent = payload.location_consent
        changed_fields.append("location_consent")

    if payload.alert_radius_miles is not None:
        if payload.alert_radius_miles not in (2, 5, 10):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="alert_radius_miles must be one of: 2, 5, 10",
            )
        current_user.alert_radius_miles = payload.alert_radius_miles
        changed_fields.append("alert_radius_miles")

    if payload.notification_categories is not None:
        raw = payload.notification_categories.strip()
        if raw:
            # Normalize comma-separated category list.
            parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
            # Keep stable ordering for easier diffing in clients.
            deduped: list[str] = []
            for part in parts:
                if part not in deduped:
                    deduped.append(part)
            current_user.notification_categories = ",".join(deduped)
        else:
            current_user.notification_categories = None
        changed_fields.append("notification_categories")

    if changed_fields:
        log_action(
            db,
            actor=current_user,
            action="user.preferences.update",
            object_type="user",
            object_id=str(current_user.id),
            after_snapshot=",".join(changed_fields),
        )

        db.commit()
        db.refresh(current_user)

    return UserOut.model_validate(current_user)
