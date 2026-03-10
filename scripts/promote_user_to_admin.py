#!/usr/bin/env python3
"""
Promote (or create) a backend user as admin by email.

This is needed because Supabase Auth self-signup is restricted to consumer/merchant
roles in the backend mapping logic.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Allow running as a script (python scripts/...) by adding the project root to sys.path.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models import RewardPreference, User, UserRole, UserStatus


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: promote_user_to_admin.py <email>")
        return 2

    email = _normalize_email(sys.argv[1])
    if not email or "@" not in email:
        print("Invalid email.")
        return 2

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))

        if not user:
            user = User(
                full_name=email.split("@", 1)[0],
                email=email,
                phone=None,
                password_hash=None,
                supabase_user_id=None,
                role=UserRole.admin,
                status=UserStatus.active,
                reward_preference=RewardPreference.cash,
                notifications_enabled=True,
                location_consent=True,
                email_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created admin user id={user.id} email={user.email}")
            return 0

        before = user.role
        user.role = UserRole.admin
        user.status = UserStatus.active
        user.email_verified = True
        db.commit()

        print(f"Updated user id={user.id} email={user.email} role {before.value} -> {user.role.value}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
