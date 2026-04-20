from collections.abc import Callable
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import RewardPreference, User, UserRole, UserStatus
from app.db.session import SessionLocal
from app.services.referrals import ensure_referral_profile
from app.services.security import decode_access_token
from app.services.supabase_auth import SupabaseAuthError, fetch_supabase_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/token")
http_bearer_optional = HTTPBearer(auto_error=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_user_from_token(db: Session, token: str) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Preferred: Supabase Auth tokens (when configured).
    if settings.supabase_url and settings.supabase_anon_key:
        try:
            sb_user = fetch_supabase_user(token)
        except SupabaseAuthError as exc:
            raise credentials_exception from exc

        if not sb_user.email:
            raise credentials_exception
        normalized_email = (sb_user.email or "").strip().lower()
        owner_admin_email = (settings.owner_admin_message_email or "").strip().lower()
        force_owner_admin = bool(owner_admin_email) and normalized_email == owner_admin_email

        user = db.scalar(select(User).where(User.supabase_user_id == sb_user.id))
        if not user and sb_user.email:
            # Allow linking an existing user record by matching email once.
            user = db.scalar(select(User).where(User.email == normalized_email))
            if user:
                user.supabase_user_id = sb_user.id
                # Keep owner admin account elevated even if legacy data drifted.
                if force_owner_admin and user.role != UserRole.admin:
                    user.role = UserRole.admin
                    user.status = UserStatus.active
                    user.email_verified = True
                ensure_referral_profile(db, user)
                db.commit()

        if not user:
            meta = sb_user.user_metadata or {}

            # Never allow self-signup as admin.
            role = UserRole.consumer
            requested_role = str(meta.get("role") or "").lower()
            if requested_role == "merchant":
                role = UserRole.merchant
            if force_owner_admin:
                role = UserRole.admin

            # Rewards accrue in cash by default; stock is a conversion action.
            reward_pref = RewardPreference.cash

            full_name = str(meta.get("full_name") or meta.get("fullName") or "").strip()
            if not full_name:
                full_name = sb_user.email.split("@", 1)[0] if sb_user.email else "PerkNation User"

            phone = meta.get("phone")
            if isinstance(phone, str):
                phone = phone.strip() or None
            else:
                phone = None

            notifications_enabled = meta.get("notifications_enabled", meta.get("notificationsEnabled", True))
            if not isinstance(notifications_enabled, bool):
                notifications_enabled = True

            location_consent = meta.get("location_consent", meta.get("locationConsent", True))
            if not isinstance(location_consent, bool):
                location_consent = True

            alert_radius_miles = meta.get("alert_radius_miles", meta.get("alertRadiusMiles", 5))
            if not isinstance(alert_radius_miles, int) or alert_radius_miles not in (2, 5, 10):
                alert_radius_miles = 5

            raw_categories = meta.get("notification_categories", meta.get("notificationCategories"))
            notification_categories = None
            if isinstance(raw_categories, list):
                cleaned = []
                for item in raw_categories:
                    if isinstance(item, str):
                        token = item.strip().lower()
                        if token and token not in cleaned:
                            cleaned.append(token)
                notification_categories = ",".join(cleaned) if cleaned else None
            elif isinstance(raw_categories, str):
                cleaned = []
                for item in raw_categories.split(","):
                    token = item.strip().lower()
                    if token and token not in cleaned:
                        cleaned.append(token)
                notification_categories = ",".join(cleaned) if cleaned else None

            user = User(
                full_name=full_name,
                email=normalized_email,
                phone=phone,
                password_hash=None,
                role=role,
                reward_preference=reward_pref,
                notifications_enabled=notifications_enabled,
                location_consent=location_consent,
                alert_radius_miles=alert_radius_miles,
                notification_categories=notification_categories,
                email_verified=True,
                supabase_user_id=sb_user.id,
            )
            db.add(user)
            db.flush()
            ensure_referral_profile(db, user)
            db.commit()
            db.refresh(user)
        elif force_owner_admin and user.role != UserRole.admin:
            # Repair drift: the owner account must retain admin access.
            user.role = UserRole.admin
            user.status = UserStatus.active
            user.email_verified = True
            db.commit()
            db.refresh(user)

        if user.status != UserStatus.active:
            raise credentials_exception

        return user

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError as exc:
        raise credentials_exception from exc

    user = db.get(User, int(user_id))
    if user is None or user.status != UserStatus.active:
        raise credentials_exception

    return user


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    return _resolve_user_from_token(db, token)


def get_optional_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_optional),
) -> Optional[User]:
    if credentials is None:
        return None

    token = (credentials.credentials or "").strip()
    if not token:
        raise _credentials_exception()

    return _resolve_user_from_token(db, token)


def require_roles(*allowed_roles: UserRole) -> Callable[[User], User]:
    def _role_guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return current_user

    return _role_guard
