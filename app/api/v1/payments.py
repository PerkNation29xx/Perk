from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Optional
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_optional_current_user
from app.db.models import User, WebLeadSubmission
from app.schemas import CheckoutPassStatusOut, CheckoutUserPassOut
from app.services.campaign_passes import (
    ensure_paid_order_pass,
    find_checkout_by_pass_code,
    find_checkout_by_stripe_session_id,
)
from app.services.runtime_settings import get_effective_payment_setting, get_runtime_setting, normalize_stripe_mode
from app.core.config import settings

router = APIRouter(prefix="/web/payments", tags=["web-payments"])
logger = logging.getLogger(__name__)


class ApplePayCheckoutRequest(BaseModel):
    source_page: str = Field(default="/hollywood-sports", max_length=255)
    offer_choice: str = Field(min_length=1, max_length=255)
    package_quantity: str = Field(default="1", max_length=16)
    selected_offer: Optional[str] = Field(default=None, max_length=255)
    selected_park: Optional[str] = Field(default=None, max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=64)
    account_email: Optional[EmailStr] = None
    account_first_name: Optional[str] = Field(default=None, max_length=120)
    account_last_name: Optional[str] = Field(default=None, max_length=120)
    account_full_name: Optional[str] = Field(default=None, max_length=255)
    account_phone: Optional[str] = Field(default=None, max_length=64)
    account_mode: Optional[str] = Field(default=None, max_length=32)
    submission_id: Optional[int] = None
    stripe_mode: Optional[str] = Field(default=None, max_length=8)


class ApplePayCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    provider: str = "stripe"
    amount_total_cents: int
    stripe_mode: str


class StripeWebhookResponse(BaseModel):
    received: bool = True


@dataclass(frozen=True)
class OfferPricing:
    label: str
    unit_amount_cents: int


_HSP_PRICING: dict[str, OfferPricing] = {
    "$1 mini test pass (live qa)": OfferPricing(
        label="$1 Mini Test Pass (Live QA)",
        unit_amount_cents=100,
    ),
    "$5 admission promo (save $60+)": OfferPricing(
        label="$5 Admission Promo",
        unit_amount_cents=500,
    ),
    "$70 bundle (12 park passes, $500+ value)": OfferPricing(
        label="$70 Bundle (12 park passes, $500+ value)",
        unit_amount_cents=7000,
    ),
}

_ALLOWED_STRIPE_MODES = {"test", "live"}
_CANONICAL_HSP_PATHS = {"/hollywood-sports", "/white/hollywood-sports"}


def _normalize_offer_key(raw_offer: str) -> str:
    return (raw_offer or "").strip().lower()


def _parse_quantity(raw_quantity: str) -> int:
    """
    Accepts checkout quantity select values: "1", "2", ..., "5+".
    """
    candidate = (raw_quantity or "").strip().lower()
    if not candidate:
        return 1

    if candidate.endswith("+"):
        candidate = candidate[:-1]

    try:
        parsed = int(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid package quantity") from exc

    if parsed < 1:
        raise HTTPException(status_code=400, detail="Package quantity must be at least 1")
    if parsed > 25:
        raise HTTPException(status_code=400, detail="Package quantity too large")
    return parsed


def _offer_pricing(offer_choice: str) -> OfferPricing:
    key = _normalize_offer_key(offer_choice)
    pricing = _HSP_PRICING.get(key)
    if pricing:
        return pricing
    raise HTTPException(status_code=400, detail="Unsupported offer for Apple Pay checkout")


def _normalize_source_page_path(source_page: str, *, default_path: str = "/hollywood-sports") -> str:
    raw = (source_page or "").strip()
    if not raw:
        return default_path

    try:
        parsed = urlsplit(raw)
        path = (parsed.path or "").strip() or raw
    except Exception:
        path = raw

    if not path.startswith("/"):
        path = f"/{path}"
    path = path.rstrip("/") or "/"

    if path in _CANONICAL_HSP_PATHS:
        return path
    if path.startswith("/white/hollywood-sports"):
        return "/white/hollywood-sports"
    if path.startswith("/hollywood-sports"):
        return "/hollywood-sports"
    return default_path


def _resolve_public_base_url(request: Optional[Request] = None) -> str:
    configured = (settings.public_web_base_url or "").strip().rstrip("/")
    fallback = configured or "https://perknation.app"
    if request is None:
        return fallback

    try:
        parsed = urlsplit(str(request.url))
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return fallback


def _canonical_web_base_url() -> str:
    return "https://perknation.app"


def _build_success_url(source_page: str, *, base_url: Optional[str] = None) -> str:
    path = _normalize_source_page_path(source_page)
    host = (base_url or settings.public_web_base_url or "https://perknation.app").rstrip("/")
    connector = "&" if "?" in path else "?"
    return f"{host}{path}{connector}payment=success&session_id={{CHECKOUT_SESSION_ID}}"


def _build_cancel_url(source_page: str, *, base_url: Optional[str] = None) -> str:
    path = _normalize_source_page_path(source_page)
    host = (base_url or settings.public_web_base_url or "https://perknation.app").rstrip("/")
    connector = "&" if "?" in path else "?"
    return f"{host}{path}{connector}payment=cancelled"


def _is_local_hostname(hostname: str) -> bool:
    host = str(hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.endswith(".local"):
        return True
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("172.16."):
        return True
    return False


def _host_default_stripe_mode(request: Optional[Request]) -> str:
    if request is None:
        return "test"
    host = str(request.url.hostname or "").strip().lower()
    return "test" if _is_local_hostname(host) else "live"


def _effective_default_stripe_mode(*, db: Session, request: Optional[Request] = None) -> str:
    # 1) explicit runtime DB setting wins
    runtime_mode = normalize_stripe_mode(get_runtime_setting(db, "stripe_mode"), fallback="")
    if runtime_mode in _ALLOWED_STRIPE_MODES:
        return runtime_mode

    # 2) explicit process env wins (STRIPE_MODE)
    env_mode = normalize_stripe_mode(os.environ.get("STRIPE_MODE"), fallback="")
    if env_mode in _ALLOWED_STRIPE_MODES:
        return env_mode

    # 3) host-aware default: public domains -> live, local hosts -> test
    host_mode = _host_default_stripe_mode(request)
    if host_mode in _ALLOWED_STRIPE_MODES:
        return host_mode

    # 4) final fallback to configured setting/default
    from_settings = get_effective_payment_setting(db, "stripe_mode", fallback="test")
    return normalize_stripe_mode(from_settings, fallback="test")


def _resolve_requested_stripe_mode(raw_mode: Optional[str], *, db: Session, request: Optional[Request] = None) -> str:
    if raw_mode is None:
        return _effective_default_stripe_mode(db=db, request=request)
    mode = (raw_mode or "").strip().lower()
    if mode not in _ALLOWED_STRIPE_MODES:
        raise HTTPException(status_code=400, detail="Unsupported Stripe mode. Use test or live.")
    return mode


def _mode_secret_key(mode: str, *, db: Session) -> str:
    if mode == "live":
        return get_effective_payment_setting(db, "stripe_secret_key_live", fallback="") or ""
    return get_effective_payment_setting(db, "stripe_secret_key_test", fallback="") or ""


def _legacy_secret_key(*, db: Session) -> str:
    return get_effective_payment_setting(db, "stripe_secret_key", fallback="") or ""


def _mode_webhook_secret(mode: str, *, db: Session) -> str:
    if mode == "live":
        return get_effective_payment_setting(db, "stripe_webhook_secret_live", fallback="") or ""
    return get_effective_payment_setting(db, "stripe_webhook_secret_test", fallback="") or ""


def _legacy_webhook_secret(*, db: Session) -> str:
    return get_effective_payment_setting(db, "stripe_webhook_secret", fallback="") or ""


def _import_stripe():
    try:
        import stripe  # type: ignore
    except Exception as exc:
        logger.exception("Stripe SDK import failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is temporarily unavailable. Please choose Zelle for now.",
        ) from exc
    return stripe


def _load_stripe(mode: str, *, db: Session):
    stripe_secret_key = _mode_secret_key(mode, db=db) or _legacy_secret_key(db=db)
    if not stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Stripe ({mode}) is not configured on this backend yet.",
        )

    stripe = _import_stripe()

    stripe.api_key = stripe_secret_key
    return stripe


def _webhook_secret_candidates(*, db: Session) -> list[tuple[str, str]]:
    """
    Return ordered webhook-secret candidates:
    1) currently selected Stripe mode
    2) the other Stripe mode
    3) legacy STRIPE_WEBHOOK_SECRET
    """

    preferred = _effective_default_stripe_mode(db=db)
    ordered_modes = [preferred] + [m for m in ("test", "live") if m != preferred]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for mode in ordered_modes:
        secret = _mode_webhook_secret(mode, db=db)
        if secret and secret not in seen:
            seen.add(secret)
            out.append((mode, secret))

    legacy = _legacy_webhook_secret(db=db)
    if legacy and legacy not in seen:
        out.append((preferred, legacy))

    return out


def _stripe_mode_candidates(*, db: Session, preferred_mode: Optional[str] = None) -> list[str]:
    preferred = normalize_stripe_mode(preferred_mode or _effective_default_stripe_mode(db=db), fallback="test")
    ordered = [preferred] + [mode for mode in ("test", "live") if mode != preferred]
    out: list[str] = []
    for mode in ordered:
        if _mode_secret_key(mode, db=db) or _legacy_secret_key(db=db):
            out.append(mode)
    return out


def _checkout_session_to_dict(session_obj) -> dict:
    if isinstance(session_obj, dict):
        return dict(session_obj)
    for method_name in ("to_dict_recursive", "to_dict"):
        method = getattr(session_obj, method_name, None)
        if callable(method):
            try:
                candidate = method()
                if isinstance(candidate, dict):
                    return candidate
            except Exception:
                continue
    return {}


def _derive_checkout_status(checkout_session: dict) -> str:
    payment_status = str(checkout_session.get("payment_status") or "").strip().lower()
    session_status = str(checkout_session.get("status") or "").strip().lower()
    if payment_status == "paid":
        return "paid"
    if session_status == "expired":
        return "expired"
    if payment_status in {"failed", "canceled"}:
        return "failed"
    return "checkout_created"


def _build_checkout_payload_from_session(
    checkout_session: dict,
    *,
    session_id: str,
    payment_status: str,
    stripe_mode: str,
    amount_total_cents: Optional[int],
) -> dict:
    metadata = checkout_session.get("metadata") or {}
    return {
        "selected_offer": str(metadata.get("selected_offer") or "").strip(),
        "offer_choice": str(metadata.get("offer_choice") or "").strip(),
        "selected_park": str(metadata.get("selected_park") or "").strip(),
        "full_name": str(metadata.get("full_name") or "").strip(),
        "email": str(metadata.get("email") or "").strip().lower(),
        "phone": str(metadata.get("phone") or "").strip(),
        "account_email": str(metadata.get("account_email") or "").strip().lower(),
        "account_first_name": str(metadata.get("account_first_name") or "").strip(),
        "account_last_name": str(metadata.get("account_last_name") or "").strip(),
        "account_full_name": str(metadata.get("account_full_name") or "").strip(),
        "account_phone": str(metadata.get("account_phone") or "").strip(),
        "account_mode": str(metadata.get("account_mode") or "").strip(),
        "package_quantity": str(metadata.get("package_quantity") or "1").strip() or "1",
        "payment_option": "apple_pay",
        "payment_status": payment_status,
        "payment_provider": "stripe",
        "stripe_mode": stripe_mode,
        "stripe_checkout_session_id": session_id,
        "stripe_checkout_url": checkout_session.get("url"),
        "payment_amount_cents": amount_total_cents,
        "payment_card_last4": str(metadata.get("payment_card_last4") or "").strip(),
        "payment_card_brand": str(metadata.get("payment_card_brand") or "").strip().lower(),
    }


def _safe_lower(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _safe_trim(value: Optional[str]) -> str:
    return str(value or "").strip()


def _extract_card_meta_from_payment_intent(payment_intent_obj) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (last4, brand) when available, otherwise (None, None).
    """

    pi = _checkout_session_to_dict(payment_intent_obj)
    if not pi:
        return None, None

    latest_charge = pi.get("latest_charge") or {}
    latest_charge_dict = _checkout_session_to_dict(latest_charge)
    card = (
        ((latest_charge_dict.get("payment_method_details") or {}).get("card") or {})
        if latest_charge_dict
        else {}
    )
    last4 = _safe_trim(card.get("last4"))
    brand = _safe_lower(card.get("brand"))
    if last4:
        return last4, (brand or None)

    charges_data = ((pi.get("charges") or {}).get("data") or [])
    if isinstance(charges_data, list):
        for charge in charges_data:
            charge_dict = _checkout_session_to_dict(charge)
            card_data = ((charge_dict.get("payment_method_details") or {}).get("card") or {})
            candidate_last4 = _safe_trim(card_data.get("last4"))
            if candidate_last4:
                candidate_brand = _safe_lower(card_data.get("brand"))
                return candidate_last4, (candidate_brand or None)

    return None, None


def _hydrate_card_meta_from_session(
    db: Session,
    checkout_session: dict,
    *,
    stripe_mode: str,
) -> tuple[Optional[str], Optional[str]]:
    payment_intent = checkout_session.get("payment_intent")
    if not payment_intent:
        return None, None

    payment_intent_dict = _checkout_session_to_dict(payment_intent)
    if payment_intent_dict:
        last4, brand = _extract_card_meta_from_payment_intent(payment_intent_dict)
        if last4:
            return last4, brand

    payment_intent_id = _safe_trim(payment_intent if isinstance(payment_intent, str) else payment_intent_dict.get("id"))
    if not payment_intent_id:
        return None, None

    try:
        stripe = _load_stripe(stripe_mode, db=db)
        pi_obj = stripe.PaymentIntent.retrieve(
            payment_intent_id,
            expand=[
                "latest_charge.payment_method_details.card",
                "charges.data.payment_method_details.card",
            ],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Stripe payment-intent lookup failed for %s in %s mode: %s",
            payment_intent_id,
            stripe_mode,
            exc,
        )
        return None, None

    return _extract_card_meta_from_payment_intent(pi_obj)


def _checkout_submission_summary(seed_payload: dict) -> str:
    bits: list[str] = []
    for label, key in (
        ("Offer", "selected_offer"),
        ("Offer choice", "offer_choice"),
        ("Park", "selected_park"),
    ):
        value = str(seed_payload.get(key) or "").strip()
        if value:
            bits.append(f"{label}: {value}")

    bits.append("Payment: Apple Pay (Stripe Checkout)")
    amount_cents = seed_payload.get("payment_amount_cents")
    try:
        if amount_cents is not None:
            bits.append(f"Amount: ${int(amount_cents) / 100:.2f}")
    except Exception:
        pass
    return " | ".join(bits)


def _sync_checkout_from_stripe(
    db: Session,
    session_id: str,
    *,
    preferred_mode: Optional[str] = None,
) -> Optional[tuple[WebLeadSubmission, dict]]:
    session_id_text = str(session_id or "").strip()
    if not session_id_text:
        return None

    for mode in _stripe_mode_candidates(db=db, preferred_mode=preferred_mode):
        try:
            stripe = _load_stripe(mode, db=db)
        except HTTPException:
            continue

        try:
            checkout_obj = stripe.checkout.Session.retrieve(
                session_id_text,
                expand=[
                    "payment_intent.latest_charge.payment_method_details.card",
                    "payment_intent.charges.data.payment_method_details.card",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stripe session lookup failed for %s in %s mode: %s", session_id_text, mode, exc)
            continue

        checkout_session = _checkout_session_to_dict(checkout_obj)
        if not checkout_session:
            continue

        card_last4, card_brand = _hydrate_card_meta_from_session(db, checkout_session, stripe_mode=mode)

        status_value = _derive_checkout_status(checkout_session)
        _sync_from_checkout_session(
            db,
            checkout_session,
            status_value=status_value,
            stripe_mode=mode,
            payment_card_last4=card_last4,
            payment_card_brand=card_brand,
        )

        lookup = find_checkout_by_stripe_session_id(db, session_id_text)
        if lookup is not None:
            row, payload = lookup
            if status_value == "paid":
                payload = ensure_paid_order_pass(db, row, notify_customer=True)
            return row, payload

        metadata = checkout_session.get("metadata") or {}
        submission_id_raw = metadata.get("submission_id")
        try:
            submission_id = int(str(submission_id_raw or "").strip())
        except Exception:
            submission_id = None

        amount_total_raw = checkout_session.get("amount_total")
        try:
            amount_total_cents = int(amount_total_raw) if amount_total_raw is not None else None
        except Exception:
            amount_total_cents = None

        row: Optional[WebLeadSubmission] = None
        if submission_id:
            _merge_submission_payment_data(
                db,
                submission_id,
                payment_option="apple_pay",
                payment_status=status_value,
                provider="stripe",
                stripe_mode=mode,
                session_id=session_id_text,
                checkout_url=checkout_session.get("url"),
                amount_total_cents=amount_total_cents,
                payment_card_last4=card_last4,
                payment_card_brand=card_brand,
            )
            candidate_row = db.get(WebLeadSubmission, submission_id)
            if candidate_row and candidate_row.form_type == "checkout":
                row = candidate_row

        # Recovery fallback: if checkout row is missing (for example after DB reset),
        # reconstruct a minimal checkout submission from Stripe session metadata.
        if row is None:
            source_page = _normalize_source_page_path(str(metadata.get("source_page") or ""))
            seed_payload = _build_checkout_payload_from_session(
                checkout_session,
                session_id=session_id_text,
                payment_status=status_value,
                stripe_mode=mode,
                amount_total_cents=amount_total_cents,
            )
            if card_last4:
                seed_payload["payment_card_last4"] = card_last4
            if card_brand:
                seed_payload["payment_card_brand"] = card_brand
            contact_name = str(seed_payload.get("full_name") or "").strip() or None
            email = str(seed_payload.get("email") or "").strip().lower() or None
            phone = str(seed_payload.get("phone") or "").strip() or None
            row = WebLeadSubmission(
                form_type="checkout",
                source_page=source_page,
                name=contact_name,
                company="Hollywood Sports x Perk Nation",
                email=email,
                phone=phone,
                inquiry=_checkout_submission_summary(seed_payload),
                contact_name=contact_name,
                payload_json=json.dumps(seed_payload, separators=(",", ":"), ensure_ascii=False),
                ip_address=None,
                user_agent=None,
            )
            if submission_id and not db.get(WebLeadSubmission, submission_id):
                row.id = submission_id
            db.add(row)
            db.commit()
            db.refresh(row)

        _merge_submission_payment_data(
            db,
            row.id,
            payment_option="apple_pay",
            payment_status=status_value,
            provider="stripe",
            stripe_mode=mode,
            session_id=session_id_text,
            checkout_url=checkout_session.get("url"),
            amount_total_cents=amount_total_cents,
            payment_card_last4=card_last4,
            payment_card_brand=card_brand,
        )

        row = db.get(WebLeadSubmission, row.id)
        if row and row.form_type == "checkout":
            payload = _parse_payload_json(row.payload_json)
            if status_value == "paid":
                payload = ensure_paid_order_pass(db, row, notify_customer=True)
            return row, payload

    return None


def _parse_payload_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _parse_iso_datetime(raw: str | None) -> Optional[datetime]:
    if not raw:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pass_pdf_url(payload: dict) -> Optional[str]:
    explicit = str(payload.get("pass_pdf_url") or "").strip()
    if explicit:
        return explicit
    view_url = str(payload.get("pass_view_url") or "").strip()
    if view_url:
        return f"{view_url.rstrip('/')}/pdf"
    return None


def _amount_cents(payload: dict) -> Optional[int]:
    raw = payload.get("payment_amount_cents")
    try:
        return int(raw) if raw is not None else None
    except Exception:
        return None


def _amount_text(payload: dict) -> str:
    cents = _amount_cents(payload)
    if cents is None:
        return "N/A"
    return f"${cents / 100:.2f}"


def _pdf_escape(value: object) -> str:
    text = str(value if value is not None else "")
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _build_text_pdf(lines: list[str]) -> bytes:
    y = 756
    content_lines = ["BT", "/F1 18 Tf", f"72 {y} Td", f"({_pdf_escape(lines[0] if lines else 'PerkNation')}) Tj"]
    y_step = 18
    for line in lines[1:]:
        if y <= 72:
            break
        size = 11 if line else 8
        content_lines.append(f"/F1 {size} Tf")
        content_lines.append(f"0 -{y_step} Td")
        content_lines.append(f"({_pdf_escape(line)}) Tj")
        y -= y_step
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _build_checkout_pass_status(row: WebLeadSubmission, payload: dict) -> CheckoutPassStatusOut:
    customer_name = (
        str(row.name).strip()
        if row.name
        else (str(payload.get("full_name") or payload.get("name") or payload.get("contact_name") or "").strip() or None)
    )

    return CheckoutPassStatusOut(
        submission_id=row.id,
        payment_status=(str(payload.get("payment_status") or "").strip() or None),
        customer_name=customer_name,
        email=row.email,
        offer_choice=(str(payload.get("offer_choice") or payload.get("selected_offer") or "").strip() or None),
        selected_park=(str(payload.get("selected_park") or payload.get("park") or "").strip() or None),
        package_quantity=(str(payload.get("package_quantity") or "").strip() or None),
        pass_code=(str(payload.get("pass_code") or "").strip() or None),
        pass_status=(str(payload.get("pass_status") or "").strip() or None),
        pass_expires_at=_parse_iso_datetime(payload.get("pass_expires_at")),
        pass_redeemed_at=_parse_iso_datetime(payload.get("pass_redeemed_at")),
        pass_account_url=(str(payload.get("pass_account_url") or "").strip() or None),
        pass_wallet_url=(str(payload.get("pass_wallet_url") or "").strip() or None),
        pass_google_wallet_url=(str(payload.get("pass_google_wallet_url") or "").strip() or None),
        pass_pdf_url=_pass_pdf_url(payload),
        pass_view_url=(str(payload.get("pass_view_url") or "").strip() or None),
        pass_qr_payload=(str(payload.get("pass_qr_payload") or "").strip() or None),
        payment_amount_cents=_amount_cents(payload),
        payment_provider=(str(payload.get("payment_provider") or "").strip() or None),
        payment_card_last4=(str(payload.get("payment_card_last4") or "").strip() or None),
        payment_card_brand=(str(payload.get("payment_card_brand") or "").strip() or None),
    )


def _checkout_email(row: WebLeadSubmission, payload: dict) -> str:
    return _safe_lower(
        row.email
        or payload.get("account_email")
        or payload.get("email")
    )


def _checkout_matches_user(row: WebLeadSubmission, payload: dict, user: User) -> bool:
    user_email = _safe_lower(user.email)
    if not user_email:
        return False

    account_user_id = _safe_trim(payload.get("account_user_id"))
    if account_user_id:
        try:
            if int(account_user_id) == int(user.id):
                return True
        except Exception:
            pass

    return _checkout_email(row, payload) == user_email


def _build_user_pass_row(row: WebLeadSubmission, payload: dict) -> CheckoutUserPassOut:
    offer_choice = (
        str(payload.get("offer_choice") or payload.get("selected_offer") or "").strip()
        or None
    )
    selected_park = (str(payload.get("selected_park") or payload.get("park") or "").strip() or None)
    package_quantity = (str(payload.get("package_quantity") or "").strip() or None)
    payment_status = (str(payload.get("payment_status") or "").strip() or None)

    return CheckoutUserPassOut(
        submission_id=row.id,
        created_at=row.created_at,
        offer_choice=offer_choice,
        selected_park=selected_park,
        package_quantity=package_quantity,
        payment_status=payment_status,
        pass_code=(str(payload.get("pass_code") or "").strip() or None),
        pass_status=(str(payload.get("pass_status") or "").strip() or None),
        pass_expires_at=_parse_iso_datetime(payload.get("pass_expires_at")),
        pass_redeemed_at=_parse_iso_datetime(payload.get("pass_redeemed_at")),
        pass_account_url=(str(payload.get("pass_account_url") or "").strip() or None),
        pass_wallet_url=(str(payload.get("pass_wallet_url") or "").strip() or None),
        pass_google_wallet_url=(str(payload.get("pass_google_wallet_url") or "").strip() or None),
        pass_pdf_url=_pass_pdf_url(payload),
        pass_view_url=(str(payload.get("pass_view_url") or "").strip() or None),
        pass_qr_payload=(str(payload.get("pass_qr_payload") or "").strip() or None),
        payment_amount_cents=_amount_cents(payload),
        payment_provider=(str(payload.get("payment_provider") or "").strip() or None),
        payment_card_last4=(str(payload.get("payment_card_last4") or "").strip() or None),
        payment_card_brand=(str(payload.get("payment_card_brand") or "").strip() or None),
    )


def _merge_submission_payment_data(
    db: Session,
    submission_id: Optional[int],
    *,
    payment_option: str,
    payment_status: str,
    provider: Optional[str] = None,
    stripe_mode: Optional[str] = None,
    session_id: Optional[str] = None,
    checkout_url: Optional[str] = None,
    amount_total_cents: Optional[int] = None,
    payment_card_last4: Optional[str] = None,
    payment_card_brand: Optional[str] = None,
) -> None:
    if not submission_id:
        return
    row = db.get(WebLeadSubmission, int(submission_id))
    if not row or row.form_type != "checkout":
        return

    payload = _parse_payload_json(row.payload_json)
    payload["payment_option"] = payment_option
    payload["payment_status"] = payment_status
    if provider:
        payload["payment_provider"] = provider
    if stripe_mode:
        payload["stripe_mode"] = stripe_mode
    if session_id:
        payload["stripe_checkout_session_id"] = session_id
    if checkout_url:
        payload["stripe_checkout_url"] = checkout_url
    if amount_total_cents is not None:
        payload["payment_amount_cents"] = int(amount_total_cents)
    if payment_card_last4:
        payload["payment_card_last4"] = _safe_trim(payment_card_last4)
    if payment_card_brand:
        payload["payment_card_brand"] = _safe_lower(payment_card_brand)

    if not row.email:
        candidate_email = _safe_lower(payload.get("account_email") or payload.get("email"))
        if candidate_email:
            row.email = candidate_email or None
    if not row.name:
        candidate_name = _safe_trim(payload.get("account_full_name") or payload.get("full_name"))
        if candidate_name:
            row.name = candidate_name or None
            row.contact_name = row.contact_name or candidate_name
    if not row.phone:
        candidate_phone = _safe_trim(payload.get("account_phone") or payload.get("phone"))
        if candidate_phone:
            row.phone = candidate_phone or None

    row.payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    db.commit()


@router.post("/apple-pay/checkout-session", response_model=ApplePayCheckoutResponse)
def create_apple_pay_checkout_session(
    payload: ApplePayCheckoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> ApplePayCheckoutResponse:
    stripe_mode = _resolve_requested_stripe_mode(payload.stripe_mode, db=db, request=request)
    stripe = _load_stripe(stripe_mode, db=db)
    pricing = _offer_pricing(payload.offer_choice)
    quantity = _parse_quantity(payload.package_quantity)
    source_page_path = _normalize_source_page_path(payload.source_page)
    public_base_url = _resolve_public_base_url(request)

    total_cents = pricing.unit_amount_cents * quantity
    if total_cents <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    try:
        _ = Decimal(total_cents) / Decimal(100)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid payment calculation") from exc

    account_email = _safe_lower(
        current_user.email if current_user else (str(payload.account_email) if payload.account_email else payload.email)
    )
    account_full_name = _safe_trim(
        (current_user.full_name if current_user else payload.account_full_name)
        or payload.full_name
        or "PerkNation customer"
    )
    account_first_name = _safe_trim(payload.account_first_name)
    account_last_name = _safe_trim(payload.account_last_name)
    if not account_first_name and account_full_name:
        parts = account_full_name.split()
        account_first_name = parts[0]
        if len(parts) > 1:
            account_last_name = " ".join(parts[1:])

    account_phone = _safe_trim((current_user.phone if current_user else payload.account_phone) or payload.phone)

    metadata = {
        "source_page": source_page_path,
        "offer_choice": payload.offer_choice,
        "selected_offer": payload.selected_offer or "",
        "selected_park": payload.selected_park or "",
        "package_quantity": str(quantity),
        "full_name": payload.full_name or account_full_name or "",
        "email": (str(payload.email) if payload.email else account_email),
        "phone": payload.phone or account_phone,
        "account_email": account_email,
        "account_first_name": account_first_name,
        "account_last_name": account_last_name,
        "account_full_name": account_full_name,
        "account_phone": account_phone,
        "account_mode": _safe_trim(payload.account_mode),
        "account_user_id": str(current_user.id) if current_user else "",
        "account_role": current_user.role.value if current_user else "",
        "submission_id": str(payload.submission_id or ""),
        "platform": "perknation_web_hsp",
        "payment_method": "apple_pay",
        "stripe_mode": stripe_mode,
    }

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": pricing.unit_amount_cents,
                        "product_data": {
                            "name": pricing.label,
                            "description": "Perk Nation Hollywood Sports campaign",
                        },
                    },
                    "quantity": quantity,
                }
            ],
            customer_email=str(payload.email) if payload.email else None,
            success_url=_build_success_url(source_page_path, base_url=public_base_url),
            cancel_url=_build_cancel_url(source_page_path, base_url=public_base_url),
            metadata=metadata,
        )
    except Exception as exc:
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start Apple Pay checkout right now. Please try again or choose Zelle.",
        ) from exc

    checkout_url = getattr(session, "url", None)
    session_id = getattr(session, "id", None)
    if not checkout_url or not session_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment session did not return a checkout URL.",
        )

    _merge_submission_payment_data(
        db,
        payload.submission_id,
        payment_option="apple_pay",
        payment_status="checkout_created",
        provider="stripe",
        stripe_mode=stripe_mode,
        session_id=str(session_id),
        checkout_url=str(checkout_url),
        amount_total_cents=total_cents,
    )

    return ApplePayCheckoutResponse(
        checkout_url=str(checkout_url),
        session_id=str(session_id),
        amount_total_cents=total_cents,
        stripe_mode=stripe_mode,
    )


@router.get("/checkout-status", response_model=CheckoutPassStatusOut)
def checkout_status(
    session_id: str = Query(..., min_length=6, max_length=255),
    db: Session = Depends(get_db),
) -> CheckoutPassStatusOut:
    lookup = find_checkout_by_stripe_session_id(db, session_id)
    if lookup is None:
        lookup = _sync_checkout_from_stripe(db, session_id)
    if lookup is None:
        raise HTTPException(status_code=404, detail="Checkout session was not found")

    row, payload = lookup
    payment_status = str(payload.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        refreshed_lookup = _sync_checkout_from_stripe(
            db,
            session_id,
            preferred_mode=(str(payload.get("stripe_mode") or "").strip().lower() or None),
        )
        if refreshed_lookup is not None:
            row, payload = refreshed_lookup
            payment_status = str(payload.get("payment_status") or "").strip().lower()
    if payment_status == "paid":
        payload = ensure_paid_order_pass(db, row, notify_customer=True)

    return _build_checkout_pass_status(row, payload)


@router.get("/my-passes", response_model=list[CheckoutUserPassOut])
def my_checkout_passes(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CheckoutUserPassOut]:
    user_email = _safe_lower(current_user.email)
    if not user_email:
        return []

    rows = db.scalars(
        select(WebLeadSubmission)
        .where(WebLeadSubmission.form_type == "checkout")
        .where(WebLeadSubmission.email == user_email)
        .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(limit * 3)
    ).all()

    # Include older rows where row.email may be empty but payload stores account email.
    if len(rows) < limit:
        extra = db.scalars(
            select(WebLeadSubmission)
            .where(WebLeadSubmission.form_type == "checkout")
            .where(WebLeadSubmission.payload_json.ilike(f"%{user_email}%"))
            .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
            .limit(limit * 3)
        ).all()
        seen = {row.id for row in rows}
        for candidate in extra:
            if candidate.id not in seen:
                rows.append(candidate)
                seen.add(candidate.id)

    out: list[CheckoutUserPassOut] = []
    seen_submission_ids: set[int] = set()
    for row in sorted(rows, key=lambda item: (item.created_at, item.id), reverse=True):
        if row.id in seen_submission_ids:
            continue
        payload = _parse_payload_json(row.payload_json)
        if not _checkout_matches_user(row, payload, current_user):
            continue
        if _safe_lower(str(payload.get("payment_status") or "")) == "paid":
            payload = ensure_paid_order_pass(db, row, notify_customer=False)
        out.append(_build_user_pass_row(row, payload))
        seen_submission_ids.add(row.id)
        if len(out) >= limit:
            break

    return out


@router.get("/pass/{pass_code}/pdf", include_in_schema=False)
def public_pass_pdf(
    pass_code: str,
    db: Session = Depends(get_db),
) -> Response:
    lookup = find_checkout_by_pass_code(db, pass_code)
    if lookup is None:
        raise HTTPException(status_code=404, detail="Pass not found")

    row, payload, normalized_code = lookup
    payment_status = str(payload.get("payment_status") or "").strip().lower()
    if payment_status == "paid":
        payload = ensure_paid_order_pass(db, row, notify_customer=False)

    expires_at = _parse_iso_datetime(payload.get("pass_expires_at"))
    redeemed_at = _parse_iso_datetime(payload.get("pass_redeemed_at"))
    created_at = row.created_at
    card_last4 = str(payload.get("payment_card_last4") or "").strip()
    card_brand = str(payload.get("payment_card_brand") or "card").strip().title()
    card_text = f"{card_brand} ending in {card_last4}" if card_last4 else "Card details pending"
    pass_view_url = str(payload.get("pass_view_url") or "").strip()
    qr_payload = str(payload.get("pass_qr_payload") or pass_view_url or normalized_code).strip()

    lines = [
        "PerkNation Receipt and Park Entry Ticket",
        "",
        "Receipt",
        f"Order #: {row.id}",
        f"Purchase date: {created_at.strftime('%B %d, %Y %I:%M %p %Z') if created_at else 'N/A'}",
        f"Amount paid: {_amount_text(payload)}",
        f"Payment status: {str(payload.get('payment_status') or 'paid').title()}",
        f"Payment provider: {str(payload.get('payment_provider') or 'Stripe').title()}",
        f"Payment method: {card_text}",
        "",
        "Ticket",
        f"Pass code: {normalized_code}",
        f"Status: {str(payload.get('pass_status') or 'unknown').title()}",
        f"Offer: {str(payload.get('offer_choice') or payload.get('selected_offer') or 'Hollywood Sports campaign')}",
        f"Park: {str(payload.get('selected_park') or payload.get('park') or 'Participating park')}",
        f"Quantity: {str(payload.get('package_quantity') or '1')}",
        f"Expires: {expires_at.strftime('%B %d, %Y %I:%M %p %Z') if expires_at else 'N/A'}",
        f"Redeemed: {redeemed_at.strftime('%B %d, %Y %I:%M %p %Z') if redeemed_at else 'Not scanned yet'}",
        "",
        "Show this PDF, the pass page, or the pass code at park check-in.",
        f"Pass page / QR payload: {qr_payload}",
        "After the first successful scan, this ticket is deactivated.",
        "",
        "Support: cs@perknation.app",
    ]
    pdf = _build_text_pdf(lines)
    filename = f"{normalized_code.lower() or 'perknation-ticket'}-receipt-ticket.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/pass/{pass_code}", response_class=HTMLResponse, include_in_schema=False)
def public_pass_view(
    pass_code: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    lookup = find_checkout_by_pass_code(db, pass_code)
    if lookup is None:
        raise HTTPException(status_code=404, detail="Pass not found")

    row, payload, normalized_code = lookup
    payment_status = str(payload.get("payment_status") or "").strip().lower()
    if payment_status == "paid":
        payload = ensure_paid_order_pass(db, row, notify_customer=False)

    pass_status = str(payload.get("pass_status") or "unknown").strip().lower()
    status_label = {
        "active": "Active",
        "redeemed": "Redeemed",
        "expired": "Expired",
    }.get(pass_status, "Unavailable")
    status_color = {
        "active": "#16a34a",
        "redeemed": "#475569",
        "expired": "#b45309",
    }.get(pass_status, "#7c3aed")

    offer_choice = (
        str(payload.get("offer_choice") or payload.get("selected_offer") or "Hollywood Sports campaign").strip()
    )
    selected_park = str(payload.get("selected_park") or payload.get("park") or "Participating park").strip()
    package_quantity = str(payload.get("package_quantity") or "1").strip()
    expires_at = _parse_iso_datetime(payload.get("pass_expires_at"))
    redeemed_at = _parse_iso_datetime(payload.get("pass_redeemed_at"))
    account_url = str(payload.get("pass_account_url") or f"{_canonical_web_base_url()}/login").strip()
    wallet_url = str(payload.get("pass_wallet_url") or "").strip()
    google_wallet_url = str(payload.get("pass_google_wallet_url") or "").strip()
    pdf_url = _pass_pdf_url(payload) or f"{_canonical_web_base_url()}{settings.api_v1_prefix}/web/payments/pass/{quote(normalized_code, safe='')}/pdf"
    pass_link = str(payload.get("pass_view_url") or "").strip()
    qr_payload = str(payload.get("pass_qr_payload") or pass_link or "").strip()
    qr_url = (
        "https://api.qrserver.com/v1/create-qr-code/?size=280x280&data="
        + quote(qr_payload, safe="")
        if qr_payload
        else ""
    )

    expires_text = expires_at.strftime("%B %d, %Y %I:%M %p %Z") if expires_at else "N/A"
    redeemed_text = redeemed_at.strftime("%B %d, %Y %I:%M %p %Z") if redeemed_at else "Not scanned yet"

    html = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PerkNation Entry Pass</title>
  <style>
    body {{
      margin: 0;
      font-family: "Avenir Next", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #0f172a, #020617);
      color: #e2e8f0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 20px;
    }}
    .card {{
      width: min(760px, 100%);
      border-radius: 22px;
      border: 1px solid rgba(226, 232, 240, 0.18);
      background: rgba(15, 23, 42, 0.78);
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.42);
      padding: 22px;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      border: 1px solid {status_color};
      color: {status_color};
      padding: 6px 12px;
      font-weight: 700;
      font-size: 13px;
      margin-bottom: 12px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }}
    .meta {{
      border-radius: 14px;
      border: 1px solid rgba(226, 232, 240, 0.16);
      background: rgba(148, 163, 184, 0.08);
      padding: 12px;
    }}
    .label {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .value {{ margin-top: 6px; font-size: 15px; font-weight: 700; color: #f8fafc; }}
    .qr {{
      margin-top: 16px;
      display: grid;
      justify-items: center;
      gap: 10px;
      border-radius: 16px;
      border: 1px solid rgba(226, 232, 240, 0.16);
      padding: 14px;
      background: rgba(2, 6, 23, 0.46);
    }}
    .qr img {{
      width: 220px;
      height: 220px;
      border-radius: 12px;
      background: #fff;
      padding: 6px;
    }}
    .actions {{
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .btn {{
      border: 1px solid rgba(226, 232, 240, 0.26);
      border-radius: 999px;
      padding: 10px 14px;
      color: #f8fafc;
      text-decoration: none;
      font-weight: 700;
      font-size: 14px;
    }}
    .btn.primary {{
      background: #16a34a;
      border-color: #16a34a;
      color: #052e16;
    }}
    .walletAction[hidden] {{ display: none; }}
    @media (max-width: 760px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <article class="card">
    <div class="status">Pass status: {escape(status_label)}</div>
    <h1 style="margin:0 0 8px;font-size:30px;">PerkNation Park Entry Pass</h1>
    <p style="margin:0 0 14px;color:#cbd5e1;">Show this pass at park check-in. It expires after one year and is deactivated after the first successful scan.</p>
    <div class="grid">
      <div class="meta"><div class="label">Pass code</div><div class="value">{escape(normalized_code)}</div></div>
      <div class="meta"><div class="label">Offer</div><div class="value">{escape(offer_choice)}</div></div>
      <div class="meta"><div class="label">Park</div><div class="value">{escape(selected_park)}</div></div>
      <div class="meta"><div class="label">Quantity</div><div class="value">{escape(package_quantity)}</div></div>
      <div class="meta"><div class="label">Expires</div><div class="value">{escape(expires_text)}</div></div>
      <div class="meta"><div class="label">Scanned</div><div class="value">{escape(redeemed_text)}</div></div>
    </div>
    <div class="qr">
      <strong>Entry QR payload</strong>
      {f'<img src="{qr_url}" alt="PerkNation pass QR code" />' if qr_url else '<div>No QR payload available.</div>'}
    </div>
    <div class="actions">
      <a class="btn" href="{escape(account_url, quote=True)}">Open account</a>
      {f'<a class="btn primary walletAction" data-apple-wallet-action href="{escape(wallet_url, quote=True)}" hidden>Add to Apple Wallet</a>' if wallet_url else ''}
      {f'<a class="btn primary walletAction" data-google-wallet-action href="{escape(google_wallet_url, quote=True)}" hidden>Add to Google Wallet</a>' if google_wallet_url else ''}
      <a class="btn walletAction" data-pdf-ticket-action href="{escape(pdf_url, quote=True)}">Download PDF receipt + ticket</a>
      <a class="btn" href="{escape(_canonical_web_base_url() + '/hollywood-sports', quote=True)}">Back to offer</a>
    </div>
  </article>
  <script>
    (function(){{
      var ua = navigator.userAgent || "";
      var platform = navigator.platform || "";
      var maxTouch = navigator.maxTouchPoints || 0;
      var isIphoneWallet = /iPhone|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
      var isAndroid = /Android/i.test(ua);
      var apple = document.querySelector("[data-apple-wallet-action]");
      var google = document.querySelector("[data-google-wallet-action]");
      var pdf = document.querySelector("[data-pdf-ticket-action]");
      if(apple && isIphoneWallet){{ apple.hidden = false; }}
      if(google && isAndroid){{ google.hidden = false; }}
      if(pdf){{ pdf.hidden = !!((apple && !apple.hidden) || (google && !google.hidden)); }}
      if(platform === "MacIntel" && maxTouch > 1 && apple){{ apple.hidden = false; if(pdf) pdf.hidden = true; }}
    }})();
  </script>
</body>
</html>
""".strip()

    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


def _sync_from_checkout_session(
    db: Session,
    checkout_session: dict,
    *,
    status_value: str,
    stripe_mode: Optional[str],
    payment_card_last4: Optional[str] = None,
    payment_card_brand: Optional[str] = None,
) -> None:
    metadata = checkout_session.get("metadata") or {}
    submission_id_raw = metadata.get("submission_id")
    if not submission_id_raw:
        return
    try:
        submission_id = int(str(submission_id_raw).strip())
    except ValueError:
        return

    amount_total_cents = checkout_session.get("amount_total")
    try:
        amount_total_cents_int = int(amount_total_cents) if amount_total_cents is not None else None
    except (ValueError, TypeError):
        amount_total_cents_int = None

    normalized_mode = normalize_stripe_mode(stripe_mode or _effective_default_stripe_mode(db=db), fallback="test")
    if not payment_card_last4:
        inferred_last4, inferred_brand = _hydrate_card_meta_from_session(db, checkout_session, stripe_mode=normalized_mode)
        payment_card_last4 = payment_card_last4 or inferred_last4
        payment_card_brand = payment_card_brand or inferred_brand

    _merge_submission_payment_data(
        db,
        submission_id,
        payment_option="apple_pay",
        payment_status=status_value,
        provider="stripe",
        stripe_mode=normalized_mode,
        session_id=checkout_session.get("id"),
        checkout_url=checkout_session.get("url"),
        amount_total_cents=amount_total_cents_int,
        payment_card_last4=payment_card_last4,
        payment_card_brand=payment_card_brand,
    )

    if status_value == "paid":
        row = db.get(WebLeadSubmission, submission_id)
        if row and row.form_type == "checkout":
            ensure_paid_order_pass(db, row, notify_customer=True)


@router.post("/stripe/webhook", response_model=StripeWebhookResponse)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> StripeWebhookResponse:
    stripe = _import_stripe()
    candidates = _webhook_secret_candidates(db=db)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook secret is not configured.",
        )

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    event = None
    matched_mode = _effective_default_stripe_mode(db=db)
    last_exc: Optional[Exception] = None
    for candidate_mode, secret in candidates:
        try:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=secret)
            matched_mode = candidate_mode
            break
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
            continue

    if event is None:
        logger.warning("Stripe webhook signature verification failed: %s", last_exc)
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature") from last_exc

    event_type = str(event.get("type") or "")
    obj = ((event.get("data") or {}).get("object") or {})
    if not isinstance(obj, dict):
        return StripeWebhookResponse(received=True)

    event_mode = "live" if bool(event.get("livemode")) else "test"
    stripe_mode = event_mode if event_mode in _ALLOWED_STRIPE_MODES else matched_mode

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        _sync_from_checkout_session(db, obj, status_value="paid", stripe_mode=stripe_mode)
    elif event_type in {"checkout.session.expired"}:
        _sync_from_checkout_session(db, obj, status_value="expired", stripe_mode=stripe_mode)
    elif event_type in {"checkout.session.async_payment_failed"}:
        _sync_from_checkout_session(db, obj, status_value="failed", stripe_mode=stripe_mode)

    return StripeWebhookResponse(received=True)
