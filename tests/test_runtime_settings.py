from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.runtime_settings import apply_payment_settings_updates, get_effective_payment_setting


def _db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return SessionLocal()


def test_blank_runtime_payment_setting_overrides_environment(monkeypatch):
    db = _db_session()
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY_LIVE", "env-publishable-value")

    apply_payment_settings_updates(db, {"stripe_publishable_key_live": ""})

    assert get_effective_payment_setting(db, "stripe_publishable_key_live", fallback="") == ""


def test_restricted_live_key_can_be_stored_as_live_secret(monkeypatch):
    db = _db_session()
    monkeypatch.setenv("STRIPE_SECRET_KEY_LIVE", "env-secret-value")

    apply_payment_settings_updates(db, {"stripe_secret_key_live": "restricted-server-value"})

    assert get_effective_payment_setting(db, "stripe_secret_key_live", fallback="") == "restricted-server-value"
