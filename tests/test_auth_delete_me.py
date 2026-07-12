from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.models import RewardPreference, User, UserRole, UserStatus
from app.db.session import SessionLocal, engine
from app.main import app
from app.services.security import create_access_token, hash_password


def _new_user(*, supabase_user_id: str | None = None) -> int:
    suffix = uuid.uuid4().int % 10_000_000
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with SessionLocal() as db:
        user = User(
            full_name="Delete Me User",
            email=f"delete-me-{uuid.uuid4().hex[:10]}@example.com",
            phone=f"+1555{suffix:07d}",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.consumer,
            reward_preference=RewardPreference.cash,
            email_verified=True,
            notifications_enabled=True,
            location_consent=True,
            supabase_user_id=supabase_user_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), role=UserRole.consumer.value)
    return {"Authorization": f"Bearer {token}"}


def test_delete_me_anonymizes_local_user_and_blocks_reuse_token() -> None:
    user_id = _new_user()
    headers = _auth_headers(user_id)

    with TestClient(app) as client:
        response = client.delete("/v1/auth/me", headers=headers)
        assert response.status_code == 200
        assert response.json()["message"] == "Account deleted"

        response = client.get("/v1/auth/me", headers=headers)
        assert response.status_code == 401

    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.status == UserStatus.suspended
        assert user.full_name == "Deleted User"
        assert user.email.startswith(f"deleted-user-{user_id}-")
        assert user.phone is None
        assert user.password_hash is None
        assert user.supabase_user_id is None
        assert user.notifications_enabled is False
        assert user.location_consent is False


def test_delete_me_calls_supabase_admin_delete_before_anonymizing(monkeypatch) -> None:
    supabase_user_id = f"sb-{uuid.uuid4()}"
    user_id = _new_user(supabase_user_id=supabase_user_id)
    deleted_ids: list[str] = []

    def _fake_delete_supabase_auth_user(value: str) -> None:
        deleted_ids.append(value)

    monkeypatch.setattr("app.api.v1.auth.delete_supabase_auth_user", _fake_delete_supabase_auth_user)

    with TestClient(app) as client:
        response = client.delete("/v1/auth/me", headers=_auth_headers(user_id))

    assert response.status_code == 200
    assert deleted_ids == [supabase_user_id]
