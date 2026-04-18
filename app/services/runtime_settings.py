from __future__ import annotations

import os
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import RuntimeSetting

PAYMENT_SETTING_KEYS: tuple[str, ...] = (
    "stripe_mode",
    "stripe_secret_key_test",
    "stripe_publishable_key_test",
    "stripe_webhook_secret_test",
    "stripe_secret_key_live",
    "stripe_publishable_key_live",
    "stripe_webhook_secret_live",
    "stripe_secret_key",
    "stripe_publishable_key",
    "stripe_webhook_secret",
)

_ALLOWED_STRIPE_MODES = {"test", "live"}


def normalize_stripe_mode(raw: Optional[str], *, fallback: str = "test") -> str:
    mode = (raw or "").strip().lower()
    if mode in _ALLOWED_STRIPE_MODES:
        return mode
    return fallback


def get_runtime_setting(db: Session, key: str) -> Optional[str]:
    row = db.get(RuntimeSetting, key)
    if not row:
        return None
    return (row.value or "").strip()


def set_runtime_setting(db: Session, key: str, value: str) -> None:
    row = db.get(RuntimeSetting, key)
    if not row:
        row = RuntimeSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value


def _from_settings_attr(key: str) -> Optional[str]:
    attr_name = key.lower()
    value = getattr(settings, attr_name, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_effective_payment_setting(
    db: Session,
    key: str,
    *,
    fallback: Optional[str] = None,
) -> Optional[str]:
    if key not in PAYMENT_SETTING_KEYS:
        raise ValueError(f"Unsupported payment setting key: {key}")

    from_db = get_runtime_setting(db, key)
    if from_db:
        return from_db

    env_key = key.upper()
    from_env = os.environ.get(env_key)
    if from_env and from_env.strip():
        return from_env.strip()

    from_settings = _from_settings_attr(key)
    if from_settings:
        return from_settings

    return fallback


def get_payment_settings_snapshot(db: Session) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in PAYMENT_SETTING_KEYS:
        out[key] = get_effective_payment_setting(db, key, fallback="") or ""

    out["stripe_mode"] = normalize_stripe_mode(out.get("stripe_mode"), fallback="test")
    return out


def apply_payment_settings_updates(db: Session, updates: Mapping[str, Optional[str]]) -> dict[str, str]:
    for key, raw_value in updates.items():
        if key not in PAYMENT_SETTING_KEYS:
            continue
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if key == "stripe_mode":
            value = normalize_stripe_mode(value, fallback="")
            if value not in _ALLOWED_STRIPE_MODES:
                raise ValueError("stripe_mode must be 'test' or 'live'")
        set_runtime_setting(db, key, value)
        os.environ[key.upper()] = value

    db.commit()
    return get_payment_settings_snapshot(db)

