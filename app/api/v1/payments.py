from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

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
    submission_id: Optional[int] = None


class ApplePayCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    provider: str = "stripe"
    amount_total_cents: int


@dataclass(frozen=True)
class OfferPricing:
    label: str
    unit_amount_cents: int


_HSP_PRICING: dict[str, OfferPricing] = {
    "$5 admission promo (save $60+)": OfferPricing(
        label="$5 Admission Promo",
        unit_amount_cents=500,
    ),
    "$70 bundle (12 park passes, $500+ value)": OfferPricing(
        label="$70 Bundle (12 park passes, $500+ value)",
        unit_amount_cents=7000,
    ),
}


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


def _build_success_url(source_page: str) -> str:
    path = (source_page or "/hollywood-sports").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    connector = "&" if "?" in path else "?"
    return f"{settings.public_web_base_url.rstrip('/')}{path}{connector}payment=success&session_id={{CHECKOUT_SESSION_ID}}"


def _build_cancel_url(source_page: str) -> str:
    path = (source_page or "/hollywood-sports").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    connector = "&" if "?" in path else "?"
    return f"{settings.public_web_base_url.rstrip('/')}{path}{connector}payment=cancelled"


def _load_stripe():
    stripe_secret_key = (os.environ.get("STRIPE_SECRET_KEY") or getattr(settings, "stripe_secret_key", None) or "").strip()
    if not stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Apple Pay is not enabled on this backend yet. Please choose Zelle for now.",
        )

    try:
        import stripe  # type: ignore
    except Exception as exc:
        logger.exception("Stripe SDK import failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is temporarily unavailable. Please choose Zelle for now.",
        ) from exc

    stripe.api_key = stripe_secret_key
    return stripe


@router.post("/apple-pay/checkout-session", response_model=ApplePayCheckoutResponse)
def create_apple_pay_checkout_session(payload: ApplePayCheckoutRequest) -> ApplePayCheckoutResponse:
    stripe = _load_stripe()
    pricing = _offer_pricing(payload.offer_choice)
    quantity = _parse_quantity(payload.package_quantity)

    total_cents = pricing.unit_amount_cents * quantity
    if total_cents <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    try:
        _ = Decimal(total_cents) / Decimal(100)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid payment calculation") from exc

    metadata = {
        "source_page": payload.source_page,
        "offer_choice": payload.offer_choice,
        "selected_offer": payload.selected_offer or "",
        "selected_park": payload.selected_park or "",
        "full_name": payload.full_name or "",
        "email": str(payload.email) if payload.email else "",
        "phone": payload.phone or "",
        "submission_id": str(payload.submission_id or ""),
        "platform": "perknation_web_hsp",
        "payment_method": "apple_pay",
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
            success_url=_build_success_url(payload.source_page),
            cancel_url=_build_cancel_url(payload.source_page),
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

    return ApplePayCheckoutResponse(
        checkout_url=str(checkout_url),
        session_id=str(session_id),
        amount_total_cents=total_cents,
    )
