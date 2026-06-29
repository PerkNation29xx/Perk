from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import RewardPreference, User, UserRole
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.security import create_access_token, hash_password, verify_password


def _new_user(password: str = "OldPass123!") -> int:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with SessionLocal() as db:
        user = User(
            full_name="Password Test User",
            email=f"password-test-{uuid.uuid4().hex[:10]}@example.com",
            phone=None,
            password_hash=hash_password(password),
            role=UserRole.consumer,
            reward_preference=RewardPreference.cash,
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), role=UserRole.consumer.value)
    return {"Authorization": f"Bearer {token}"}


def test_change_password_updates_local_password_hash() -> None:
    user_id = _new_user()

    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/me/password",
            json={
                "current_password": "OldPass123!",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
            headers=_auth_headers(user_id),
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Password updated"

    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert verify_password("NewPass123!", user.password_hash)


def test_change_password_rejects_wrong_current_password() -> None:
    user_id = _new_user()

    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/me/password",
            json={
                "current_password": "WrongPass123!",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
            headers=_auth_headers(user_id),
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Current password is incorrect"
