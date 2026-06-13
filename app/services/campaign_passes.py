from __future__ import annotations

import json
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from html import escape
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import WebLeadSubmission
from app.services.wallet_passes import wallet_pass_service

logger = logging.getLogger(__name__)

PASS_VALIDITY = timedelta(days=365)
PASS_CODE_PREFIX = "PKI-HSP"
PASS_QR_SIZE_PX = 320
PASS_QR_FETCH_TIMEOUT_SECONDS = 8
HSP_BUNDLE_TICKET_COUNT = 12
PASS_TICKETS_KEY = "pass_tickets"
PASS_TICKET_FIELD_KEYS = (
    "ticket_number",
    "ticket_type",
    "pass_label",
    "pass_title",
    "pass_summary",
    "pass_terms",
    "pass_code",
    "pass_status",
    "pass_issued_at",
    "pass_expires_at",
    "pass_redeemed_at",
    "pass_redeemed_by",
    "pass_scan_count",
    "pass_account_url",
    "pass_wallet_url",
    "pass_google_wallet_url",
    "pass_pdf_url",
    "pass_view_url",
    "pass_qr_payload",
    "pass_qr_image_url",
    "pass_wallet_serial_number",
    "pass_wallet_auth_token",
    "pass_wallet_web_service_url",
    "pass_wallet_last_updated_at",
    "pass_wallet_registrations",
)
PRIMARY_PASS_FIELD_KEYS = (
    "ticket_number",
    "ticket_type",
    "pass_label",
    "pass_title",
    "pass_summary",
    "pass_terms",
    "pass_code",
    "pass_status",
    "pass_issued_at",
    "pass_expires_at",
    "pass_redeemed_at",
    "pass_redeemed_by",
    "pass_scan_count",
    "pass_account_url",
    "pass_wallet_url",
    "pass_google_wallet_url",
    "pass_pdf_url",
    "pass_view_url",
    "pass_qr_payload",
    "pass_qr_image_url",
    "pass_wallet_serial_number",
    "pass_wallet_auth_token",
    "pass_wallet_web_service_url",
    "pass_wallet_last_updated_at",
    "pass_wallet_registrations",
)

HSP_REGULAR_ENTRY_TERMS = [
    "Ticket includes paintball marker.",
    "All day park pass.",
    "All day air and purchase of 400 paintballs required.",
    "Bonus 100 rounds when playing .50 caliber.",
    "Parks are field paint only.",
]
HSP_GOLDEN_TICKET_TERMS = [
    "Admission included.",
    ".50 caliber gun included.",
    "200 paintballs included.",
    "Mask rental included.",
    "Tickets are for .50 cal paintballsoft play only.",
    "Good for walk-ons and cannot be used or combined with any other discount.",
]
HSP_ENTRY_ONLY_TERMS = [
    "Entry only pass.",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _first_non_empty(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_iso_datetime(raw: Any) -> Optional[datetime]:
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _web_base_url() -> str:
    configured = (settings.public_web_base_url or "https://perknation.app").strip().rstrip("/")
    try:
        host = (urlsplit(configured).hostname or "").lower()
    except Exception:
        host = ""
    if host not in {"perknation.app", "www.perknation.app"}:
        return "https://perknation.app"
    return "https://perknation.app"


def _api_base_url() -> str:
    base = _web_base_url()
    prefix = (settings.api_v1_prefix or "/v1").strip()
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return f"{base}{prefix}"


def _default_account_url() -> str:
    return f"{_web_base_url()}/login"


def _generate_pass_code(row_id: int, ticket_number: int | None = None) -> str:
    token = secrets.token_hex(3).upper()
    if ticket_number is not None:
        return f"{PASS_CODE_PREFIX}-{int(row_id):06d}-{int(ticket_number):02d}-{token}"
    return f"{PASS_CODE_PREFIX}-{int(row_id):06d}-{token}"


def _build_pass_urls(pass_code: str, *, pass_title: str | None = None) -> dict[str, str]:
    api_base = _api_base_url()
    pass_view_url = f"{api_base}/web/payments/pass/{quote(pass_code, safe='')}"
    pass_pdf_url = f"{pass_view_url}/pdf"
    pass_qr_payload = pass_view_url
    pass_qr_image_url = _build_qr_image_url(pass_qr_payload)
    wallet_title = str(pass_title or "PerkNation Park Entry Pass").strip() or "PerkNation Park Entry Pass"
    wallet_query = urlencode(
        {
            "title": wallet_title,
            "code": pass_code,
            "payload": pass_view_url,
            "template": "perknation",
        }
    )
    wallet_pass_url = f"{api_base}/wallet/pass?{wallet_query}"
    return {
        "pass_view_url": pass_view_url,
        "pass_pdf_url": pass_pdf_url,
        "pass_qr_payload": pass_qr_payload,
        "pass_qr_image_url": pass_qr_image_url,
        "pass_wallet_url": wallet_pass_url,
        "pass_google_wallet_url": "",
        "pass_account_url": _default_account_url(),
    }


def _hsp_product_text(payload: dict[str, Any]) -> str:
    return " ".join(
        str(payload.get(key) or "")
        for key in (
            "offer_choice",
            "selected_offer",
            "payment_option",
            "package_quantity",
        )
    ).lower()


def _hsp_product_key(payload: dict[str, Any]) -> str:
    text = _hsp_product_text(payload)
    if "$60" in text or "60 bundle" in text or "golden ticket" in text:
        return "bundle_60"
    if "$70" in text or "70 bundle" in text:
        return "bundle_70"
    if "$5" in text or "5 admission" in text or "entry only" in text:
        return "entry_5"
    return ""


def _regular_entry_ticket_meta(ticket_number: int) -> dict[str, Any]:
    return {
        "ticket_number": ticket_number,
        "bundle_ticket_number": ticket_number,
        "ticket_type": "regular_entry",
        "pass_title": "Regular Entry Ticket",
        "pass_label": f"Regular Entry Ticket {ticket_number} of 11",
        "pass_summary": "Paintball marker + all day park pass",
        "pass_terms": list(HSP_REGULAR_ENTRY_TERMS),
    }


def _golden_ticket_meta(ticket_number: int = 12) -> dict[str, Any]:
    return {
        "ticket_number": ticket_number,
        "bundle_ticket_number": 1,
        "ticket_type": "golden_ticket",
        "pass_title": "Golden Ticket",
        "pass_label": "Golden Ticket 1 of 1",
        "pass_summary": "Admission + .50 caliber gun + 200 paintballs + mask rental",
        "pass_terms": list(HSP_GOLDEN_TICKET_TERMS),
    }


def _entry_only_ticket_meta() -> dict[str, Any]:
    return {
        "ticket_number": 1,
        "bundle_ticket_number": 1,
        "ticket_type": "entry_only",
        "pass_title": "$5 Entry Only Pass",
        "pass_label": "Entry Only Pass",
        "pass_summary": "Entry only",
        "pass_terms": list(HSP_ENTRY_ONLY_TERMS),
    }


def _ticket_manifest_for_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    product_key = _hsp_product_key(payload)
    if product_key in {"bundle_60", "bundle_70"}:
        return [_regular_entry_ticket_meta(number) for number in range(1, 12)] + [_golden_ticket_meta(12)]
    if product_key == "entry_5":
        return [_entry_only_ticket_meta()]
    return []


def _checkout_wants_multi_ticket_bundle(payload: dict[str, Any]) -> bool:
    if str(payload.get("pass_delivery_mode") or "").strip().lower() == "multi_ticket":
        return True
    return len(_ticket_manifest_for_payload(payload)) > 1


def _pass_ticket_count_for_payload(payload: dict[str, Any]) -> int:
    manifest = _ticket_manifest_for_payload(payload)
    if manifest:
        return len(manifest)
    return HSP_BUNDLE_TICKET_COUNT if _checkout_wants_multi_ticket_bundle(payload) else 1


def _single_ticket_meta_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = _ticket_manifest_for_payload(payload)
    return manifest[0] if len(manifest) == 1 else {}


def _ticket_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tickets = payload.get(PASS_TICKETS_KEY)
    if not isinstance(tickets, list):
        return []
    return [ticket for ticket in tickets if isinstance(ticket, dict)]


def _public_ticket_record(ticket: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ticket.get(key)
        for key in (
            "ticket_number",
            "bundle_ticket_number",
            "ticket_type",
            "pass_label",
            "pass_title",
            "pass_summary",
            "pass_terms",
            "pass_code",
            "pass_status",
            "pass_issued_at",
            "pass_expires_at",
            "pass_redeemed_at",
            "pass_scan_count",
            "pass_account_url",
            "pass_wallet_url",
            "pass_google_wallet_url",
            "pass_pdf_url",
            "pass_view_url",
            "pass_qr_payload",
            "pass_qr_image_url",
        )
    }


def checkout_pass_tickets_for_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_public_ticket_record(ticket) for ticket in _ticket_records(payload)]


def _ticket_by_pass_code(
    payload: dict[str, Any],
    raw_code: str,
) -> tuple[int | None, dict[str, Any] | None, str]:
    normalized = _extract_pass_code(raw_code)
    if not normalized:
        return None, None, ""

    for idx, ticket in enumerate(_ticket_records(payload)):
        pass_code = str(ticket.get("pass_code") or "").strip()
        if pass_code and pass_code.lower() == normalized.lower():
            return idx, ticket, pass_code

    pass_code = str(payload.get("pass_code") or "").strip()
    if pass_code and pass_code.lower() == normalized.lower():
        return None, payload, pass_code

    return None, None, normalized


def checkout_ticket_from_payload(
    payload: dict[str, Any],
    raw_code: str,
) -> tuple[int | None, dict[str, Any] | None, str]:
    return _ticket_by_pass_code(payload, raw_code)


def _wallet_registration_tokens(payload: dict[str, Any], ticket: dict[str, Any] | None = None) -> list[str]:
    source = ticket if isinstance(ticket, dict) else payload
    registrations = source.get("pass_wallet_registrations")
    if not isinstance(registrations, dict):
        return []

    tokens: list[str] = []
    for record in registrations.values():
        if not isinstance(record, dict):
            continue
        token = str(record.get("pushToken") or record.get("push_token") or "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _sync_primary_pass_from_ticket(payload: dict[str, Any], ticket: dict[str, Any] | None) -> bool:
    if not isinstance(ticket, dict):
        return False

    changed = False
    for key in PRIMARY_PASS_FIELD_KEYS:
        value = ticket.get(key)
        if payload.get(key) != value:
            payload[key] = value
            changed = True
    return changed


def _refresh_ticket_expiration(ticket: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    now_utc = now or _utcnow()
    status_value = str(ticket.get("pass_status") or "").strip().lower()
    expires_at = _parse_iso_datetime(ticket.get("pass_expires_at"))
    if not expires_at:
        return False
    if status_value in {"", "active", "issued"} and now_utc >= expires_at:
        ticket["pass_status"] = "expired"
        ticket["pass_wallet_last_updated_at"] = _to_iso_utc(now_utc)
        return True
    return False


def _seed_ticket_from_primary_payload(
    row_id: int,
    payload: dict[str, Any],
    *,
    ticket_number: int,
    total_count: int,
    issued_at: datetime,
    expires_at: datetime,
    ticket_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = ticket_meta or {}
    ticket: dict[str, Any] = {
        "ticket_number": ticket_number,
        "pass_label": str(meta.get("pass_label") or f"Ticket {ticket_number} of {total_count}"),
    }
    for key, value in meta.items():
        ticket[key] = value
    for key in PRIMARY_PASS_FIELD_KEYS:
        if key in payload:
            ticket[key] = payload.get(key)
    for key, value in meta.items():
        ticket[key] = value
    if not str(ticket.get("pass_code") or "").strip():
        ticket["pass_code"] = _generate_pass_code(row_id, ticket_number)
    if not str(ticket.get("pass_status") or "").strip():
        ticket["pass_status"] = "active"
    if not str(ticket.get("pass_issued_at") or "").strip():
        ticket["pass_issued_at"] = _to_iso_utc(issued_at)
    if not str(ticket.get("pass_expires_at") or "").strip():
        ticket["pass_expires_at"] = _to_iso_utc(expires_at)
    if "pass_scan_count" not in ticket:
        ticket["pass_scan_count"] = int(payload.get("pass_scan_count") or 0)
    return ticket


def _ensure_ticket_fields(
    row_id: int,
    ticket: dict[str, Any],
    *,
    ticket_number: int,
    total_count: int,
    issued_at: datetime,
    expires_at: datetime,
    now: datetime,
    ticket_meta: dict[str, Any] | None = None,
) -> bool:
    changed = False
    meta = ticket_meta or {}
    desired_ticket_number = int(meta.get("ticket_number") or ticket_number)
    if ticket.get("ticket_number") != desired_ticket_number:
        ticket["ticket_number"] = desired_ticket_number
        changed = True
    desired_values = {
        "bundle_ticket_number": meta.get("bundle_ticket_number"),
        "ticket_type": meta.get("ticket_type"),
        "pass_title": meta.get("pass_title"),
        "pass_label": meta.get("pass_label") or f"Ticket {ticket_number} of {total_count}",
        "pass_summary": meta.get("pass_summary"),
        "pass_terms": meta.get("pass_terms"),
    }
    for key, value in desired_values.items():
        if value in (None, ""):
            continue
        if ticket.get(key) != value:
            ticket[key] = value
            changed = True

    pass_code = str(ticket.get("pass_code") or "").strip()
    if not pass_code:
        pass_code = _generate_pass_code(row_id, ticket_number)
        ticket["pass_code"] = pass_code
        changed = True

    issued_text = str(ticket.get("pass_issued_at") or "").strip()
    if not issued_text:
        ticket["pass_issued_at"] = _to_iso_utc(issued_at)
        changed = True

    expires_text = str(ticket.get("pass_expires_at") or "").strip()
    if not expires_text:
        ticket["pass_expires_at"] = _to_iso_utc(expires_at)
        changed = True

    current_status = str(ticket.get("pass_status") or "").strip().lower()
    if current_status in {"", "pending", "payment_pending", "failed", "canceled"}:
        ticket["pass_status"] = "active"
        changed = True

    pass_urls = _build_pass_urls(pass_code, pass_title=str(ticket.get("pass_title") or "").strip() or None)
    for key, value in pass_urls.items():
        if str(ticket.get(key) or "").strip() != value:
            ticket[key] = value
            changed = True

    wallet_serial = _pass_wallet_serial_number(pass_code, ticket["pass_view_url"])
    if str(ticket.get("pass_wallet_serial_number") or "").strip() != wallet_serial:
        ticket["pass_wallet_serial_number"] = wallet_serial
        changed = True

    if not str(ticket.get("pass_wallet_auth_token") or "").strip():
        ticket["pass_wallet_auth_token"] = secrets.token_urlsafe(32)
        changed = True

    wallet_web_service_url = _pass_wallet_web_service_url()
    if str(ticket.get("pass_wallet_web_service_url") or "").strip() != wallet_web_service_url:
        ticket["pass_wallet_web_service_url"] = wallet_web_service_url
        changed = True

    if not str(ticket.get("pass_wallet_last_updated_at") or "").strip():
        ticket["pass_wallet_last_updated_at"] = str(ticket.get("pass_issued_at") or _to_iso_utc(now))
        changed = True

    if "pass_scan_count" not in ticket:
        ticket["pass_scan_count"] = 0
        changed = True

    if not isinstance(ticket.get("pass_wallet_registrations"), dict):
        ticket["pass_wallet_registrations"] = {}
        changed = True

    if _refresh_ticket_expiration(ticket, now=now):
        changed = True

    return changed


def _ensure_multi_ticket_payload(
    row_id: int,
    payload: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    changed = False
    ticket_manifest = _ticket_manifest_for_payload(payload)
    total_count = len(ticket_manifest) or _pass_ticket_count_for_payload(payload)
    issued_at = _parse_iso_datetime(payload.get("pass_issued_at")) or now
    expires_at = _parse_iso_datetime(payload.get("pass_expires_at")) or (issued_at + PASS_VALIDITY)

    existing = _ticket_records(payload)
    tickets: list[dict[str, Any]] = []
    if existing:
        tickets.extend(existing[:total_count])
    else:
        tickets.append(
            _seed_ticket_from_primary_payload(
                row_id,
                payload,
                ticket_number=1,
                total_count=total_count,
                issued_at=issued_at,
                expires_at=expires_at,
                ticket_meta=ticket_manifest[0] if ticket_manifest else None,
            )
        )

    while len(tickets) < total_count:
        ticket_number = len(tickets) + 1
        tickets.append(
            {
                "ticket_number": ticket_number,
                "pass_label": str(
                    (ticket_manifest[ticket_number - 1] if len(ticket_manifest) >= ticket_number else {}).get("pass_label")
                    or f"Ticket {ticket_number} of {total_count}"
                ),
                "pass_code": _generate_pass_code(row_id, ticket_number),
                "pass_status": "active",
                "pass_issued_at": _to_iso_utc(issued_at),
                "pass_expires_at": _to_iso_utc(expires_at),
                "pass_scan_count": 0,
                "pass_wallet_registrations": {},
            }
        )
        changed = True

    for idx, ticket in enumerate(tickets, start=1):
        if _ensure_ticket_fields(
            row_id,
            ticket,
            ticket_number=idx,
            total_count=total_count,
            issued_at=issued_at,
            expires_at=expires_at,
            now=now,
            ticket_meta=ticket_manifest[idx - 1] if len(ticket_manifest) >= idx else None,
        ):
            changed = True

    original_tickets = payload.get(PASS_TICKETS_KEY)
    if original_tickets != tickets:
        payload[PASS_TICKETS_KEY] = tickets
        changed = True

    if payload.get("pass_ticket_count") != total_count:
        payload["pass_ticket_count"] = total_count
        changed = True
    if payload.get("pass_delivery_mode") != "multi_ticket":
        payload["pass_delivery_mode"] = "multi_ticket"
        changed = True

    if not str(payload.get("pass_issued_at") or "").strip():
        payload["pass_issued_at"] = _to_iso_utc(issued_at)
        changed = True
    if not str(payload.get("pass_expires_at") or "").strip():
        payload["pass_expires_at"] = _to_iso_utc(expires_at)
        changed = True

    if tickets and _sync_primary_pass_from_ticket(payload, tickets[0]):
        changed = True

    return changed


def _build_qr_image_url(payload: str) -> str:
    qr_payload = str(payload or "").strip()
    if not qr_payload:
        return ""
    return (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size={PASS_QR_SIZE_PX}x{PASS_QR_SIZE_PX}&data="
        + quote(qr_payload, safe="")
    )


def _fetch_qr_png_bytes(qr_image_url: str) -> Optional[bytes]:
    url = str(qr_image_url or "").strip()
    if not url:
        return None

    try:
        req = Request(
            url,
            headers={
                "User-Agent": "PerkNation/1.0 (+https://perknation.app)",
                "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
            },
        )
        with urlopen(req, timeout=PASS_QR_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            data = response.read()
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if not data:
                return None
            if content_type and "image" not in content_type:
                logger.warning("Checkout pass QR fetch returned non-image content-type: %s", content_type)
                return None
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Checkout pass QR fetch failed for %s: %s", url, exc)
        return None


def _extract_pass_code(raw_value: str) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return ""

    if "://" in raw:
        parsed = urlsplit(raw)
        query = parse_qs(parsed.query)
        from_query = (query.get("code") or [""])[0].strip()
        if from_query:
            return from_query

        path_parts = [segment for segment in parsed.path.split("/") if segment]
        if path_parts:
            candidate = path_parts[-1].strip()
            if candidate:
                return candidate

    if "code=" in raw:
        try:
            parsed_inline = urlsplit(raw)
            query = parse_qs(parsed_inline.query)
            from_query = (query.get("code") or [""])[0].strip()
            if from_query:
                return from_query
        except Exception:
            pass

    return raw


def _refresh_expiration(payload: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    now_utc = now or _utcnow()
    changed = False

    status_value = str(payload.get("pass_status") or "").strip().lower()
    expires_at = _parse_iso_datetime(payload.get("pass_expires_at"))
    if expires_at and status_value in {"", "active", "issued"} and now_utc >= expires_at:
        payload["pass_status"] = "expired"
        payload["pass_wallet_last_updated_at"] = _to_iso_utc(now_utc)
        changed = True

    tickets = _ticket_records(payload)
    for ticket in tickets:
        if _refresh_ticket_expiration(ticket, now=now_utc):
            changed = True
    if tickets and _sync_primary_pass_from_ticket(payload, tickets[0]):
        changed = True

    return changed


def _reconcile_unpaid_checkout_payload(payload: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    now_utc = now or _utcnow()
    payment_status = str(payload.get("payment_status") or "").strip().lower()
    pass_status = str(payload.get("pass_status") or "").strip().lower()
    changed = False

    final_status_by_payment = {
        "expired": "expired",
        "failed": "failed",
        "canceled": "canceled",
        "cancelled": "canceled",
        "refunded": "refunded",
    }
    target_status = final_status_by_payment.get(payment_status)

    if target_status and pass_status not in {"redeemed", "refunded"}:
        if pass_status != target_status:
            payload["pass_status"] = target_status
            payload["pass_wallet_last_updated_at"] = _to_iso_utc(now_utc)
            changed = True
        for ticket in _ticket_records(payload):
            ticket_status = str(ticket.get("pass_status") or "").strip().lower()
            if ticket_status not in {"redeemed", "refunded"} and ticket_status != target_status:
                ticket["pass_status"] = target_status
                ticket["pass_wallet_last_updated_at"] = _to_iso_utc(now_utc)
                changed = True
        tickets = _ticket_records(payload)
        if tickets and _sync_primary_pass_from_ticket(payload, tickets[0]):
            changed = True
        return changed

    if payment_status in {"", "pending", "checkout_created", "unpaid"}:
        if pass_status in {"", "pending"} and not str(payload.get("pass_code") or "").strip() and not _ticket_records(payload):
            payload["pass_status"] = "payment_pending"
            changed = True

    return changed


def reconcile_checkout_pass_state(
    db: Session,
    row: WebLeadSubmission,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    reconciled = payload if isinstance(payload, dict) else _parse_payload(row.payload_json)
    changed = False

    if _reconcile_unpaid_checkout_payload(reconciled):
        changed = True
    if _refresh_expiration(reconciled):
        changed = True

    if changed:
        row.payload_json = _dump_payload(reconciled)
        db.add(row)
        db.commit()
        db.refresh(row)

    return reconciled


def _pass_wallet_web_service_url() -> str:
    return f"{_api_base_url()}/wallet"


def _pass_wallet_serial_number(pass_code: str, pass_view_url: str) -> str:
    return wallet_pass_service.serial_number_for(
        template="perknation",
        title="PerkNation Park Entry Pass",
        code=pass_code,
        payload=pass_view_url,
    )


def _payment_amount_text(payload: dict[str, Any]) -> str:
    raw_cents = payload.get("payment_amount_cents")
    try:
        cents = int(raw_cents)
    except Exception:
        return "N/A"
    return f"${cents / 100:.2f}"


def _payment_card_text(payload: dict[str, Any]) -> str:
    last4 = str(payload.get("payment_card_last4") or "").strip()
    if not last4:
        return "Card details pending"
    brand = str(payload.get("payment_card_brand") or "card").strip().title()
    return f"{brand} ending in {last4}"


def _smtp_ready() -> bool:
    return bool(settings.smtp_host)


def _send_checkout_pass_email(row: WebLeadSubmission, payload: dict[str, Any]) -> bool:
    recipient = (row.email or "").strip()
    if not recipient or not _smtp_ready():
        return False

    sender_candidate = (
        (settings.smtp_from_email or "").strip()
        or (settings.smtp_username or "").strip()
        or "cs@perknation.app"
    )
    sender = parseaddr(sender_candidate)[1] or "cs@perknation.app"
    if not sender.lower().endswith("@perknation.app"):
        sender = "cs@perknation.app"

    customer_name = _first_non_empty(row.name, row.contact_name, payload.get("full_name")) or "PerkNation member"
    offer_choice = _first_non_empty(payload.get("offer_choice"), payload.get("selected_offer")) or "Hollywood Sports campaign"
    selected_park = _first_non_empty(payload.get("selected_park"), payload.get("park")) or "Participating park"
    package_quantity = _first_non_empty(payload.get("package_quantity"), "1 package")
    ticket_records = checkout_pass_tickets_for_payload(payload)
    if not ticket_records and str(payload.get("pass_code") or "").strip():
        ticket_records = [_public_ticket_record(payload)]
    first_ticket = ticket_records[0] if ticket_records else {}
    ticket_count = len(ticket_records) or 1
    pass_code = str(first_ticket.get("pass_code") or payload.get("pass_code") or "").strip()
    expires_at = _parse_iso_datetime(first_ticket.get("pass_expires_at") or payload.get("pass_expires_at"))
    expires_text = expires_at.strftime("%B %d, %Y") if expires_at else "One year from purchase"

    account_url = str(payload.get("pass_account_url") or _default_account_url()).strip()

    amount_text = _payment_amount_text(payload)
    payment_status = str(payload.get("payment_status") or "paid").strip() or "paid"
    payment_provider = str(payload.get("payment_provider") or "Stripe").strip() or "Stripe"
    payment_card = _payment_card_text(payload)
    purchased_at = _parse_iso_datetime(payload.get("payment_paid_at")) or row.created_at
    purchased_text = purchased_at.strftime("%B %d, %Y") if purchased_at else "N/A"

    first_qr_payload = str(
        first_ticket.get("pass_qr_payload")
        or first_ticket.get("pass_view_url")
        or pass_code
        or ""
    ).strip()
    first_qr_image_url = str(
        first_ticket.get("pass_qr_image_url")
        or _build_qr_image_url(first_qr_payload)
    ).strip()
    inline_qr_png = _fetch_qr_png_bytes(first_qr_image_url) if ticket_count == 1 else None

    plain_ticket_lines: list[str] = []
    ticket_cards_html: list[str] = []
    for idx, ticket in enumerate(ticket_records or [_public_ticket_record(payload)], start=1):
        ticket_code = str(ticket.get("pass_code") or pass_code).strip()
        label = str(ticket.get("pass_label") or f"Ticket {idx} of {ticket_count}").strip()
        title = str(ticket.get("pass_title") or label).strip()
        summary = str(ticket.get("pass_summary") or "").strip()
        terms = ticket.get("pass_terms") if isinstance(ticket.get("pass_terms"), list) else []
        ticket_wallet_url = str(ticket.get("pass_wallet_url") or "").strip()
        ticket_view_url = str(ticket.get("pass_view_url") or "").strip()
        ticket_pdf_url = str(ticket.get("pass_pdf_url") or "").strip()
        ticket_qr_payload = str(ticket.get("pass_qr_payload") or ticket_view_url or ticket_code).strip()
        ticket_qr_image_url = str(ticket.get("pass_qr_image_url") or _build_qr_image_url(ticket_qr_payload)).strip()
        ticket_expires_at = _parse_iso_datetime(ticket.get("pass_expires_at"))
        ticket_expires_text = ticket_expires_at.strftime("%B %d, %Y") if ticket_expires_at else expires_text

        plain_ticket_lines.extend(
            [
                f"{label}",
                f"Type: {title}",
                f"Includes: {summary or 'See ticket details'}",
                *[f"- {term}" for term in terms],
                f"Pass code: {ticket_code}",
                f"Expires: {ticket_expires_text}",
                f"Wallet pass: {ticket_wallet_url}",
                f"Pass page: {ticket_view_url}",
                f"PDF receipt and ticket: {ticket_pdf_url}",
                f"Entry QR: {ticket_qr_image_url}",
                "",
            ]
        )

        qr_src = "cid:perknation-pass-qr" if inline_qr_png and idx == 1 else ticket_qr_image_url
        ticket_cards_html.append(
            f"""
              <div style=\"border:1px solid #e5e7eb;border-radius:14px;padding:14px;margin:0 0 14px;background:#fbfdff;\">
                <div style=\"font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;margin:0 0 8px;\">{escape(label)}</div>
                <div style=\"font-size:18px;font-weight:800;color:#111827;margin:0 0 6px;\">{escape(title)}</div>
                {f'<div style="font-size:13px;color:#334155;margin:0 0 10px;">{escape(summary)}</div>' if summary else ''}
                <table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;border-collapse:collapse;margin:0 0 12px;\">
                  <tr><td style=\"padding:5px 0;color:#6b7280;width:130px;\">Pass code</td><td style=\"padding:5px 0;font-weight:700;letter-spacing:0.03em;\">{escape(ticket_code)}</td></tr>
                  <tr><td style=\"padding:5px 0;color:#6b7280;\">Expires</td><td style=\"padding:5px 0;font-weight:600;\">{escape(ticket_expires_text)}</td></tr>
                </table>
                {f'<ul style="margin:0 0 12px;padding-left:18px;color:#334155;font-size:13px;line-height:1.45;">{"".join(f"<li>{escape(str(term))}</li>" for term in terms)}</ul>' if terms else ''}
                {f'<img src="{escape(qr_src, quote=True)}" alt="PerkNation entry QR code" style="width:190px;height:190px;border-radius:12px;border:1px solid #e2e8f0;background:#fff;padding:4px;margin:0 0 10px;" />' if qr_src else ''}
                <p style=\"margin:0 0 8px;\"><a href=\"{escape(ticket_wallet_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">Add this ticket to Apple Wallet</a></p>
                <p style=\"margin:0 0 8px;\"><a href=\"{escape(ticket_view_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">View pass + scan link</a></p>
                <p style=\"margin:0;\"><a href=\"{escape(ticket_pdf_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">Download PDF receipt + ticket</a></p>
              </div>
            """.strip()
        )

    msg = EmailMessage()
    msg["From"] = formataddr(("PerkNation", sender))
    msg["To"] = recipient
    msg["Reply-To"] = "cs@perknation.app"
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(idstring=f"pass-{pass_code or row.id}", domain="perknation.app")
    msg["Subject"] = (
        f"Your PerkNation receipt and {ticket_count} park entry passes"
        if ticket_count > 1
        else "Your PerkNation receipt and park entry pass"
    )

    plain_lines = [
        f"Hi {customer_name},",
        "",
        "Thanks for your PerkNation purchase. Your receipt and park entry passes are below.",
        "",
        f"Order #: {row.id}",
        f"Purchase date: {purchased_text}",
        f"Amount paid: {amount_text}",
        f"Payment status: {payment_status}",
        f"Payment provider: {payment_provider}",
        f"Payment method: {payment_card}",
        "",
        f"Offer: {offer_choice}",
        f"Park: {selected_park}",
        f"Quantity: {package_quantity}",
        f"Tickets issued: {ticket_count}",
        f"Expires: {expires_text}",
        "",
        f"Account: {account_url}",
        "",
        "Tickets:",
        *plain_ticket_lines,
        "",
        "Each ticket is valid for one year and is deactivated only after that individual ticket is scanned at the park.",
        "",
        "PerkNation Support",
    ]
    msg.set_content("\n".join(plain_lines))

    html = f"""
    <html>
      <body style=\"font-family:Arial,Helvetica,sans-serif;background:#f7f8fc;color:#111827;padding:16px;\">
        <table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:620px;width:100%;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;\">
          <tr>
            <td style=\"padding:18px 20px;background:#0f172a;color:#f8fafc;\">
              <h1 style=\"margin:0;font-size:20px;\">PerkNation Entry Passes</h1>
              <p style=\"margin:8px 0 0;font-size:13px;color:#cbd5e1;\">Your purchase is confirmed and your tickets are ready.</p>
            </td>
          </tr>
          <tr>
            <td style=\"padding:18px 20px;\">
              <p style=\"margin:0 0 12px;\">Hi {escape(customer_name)},</p>
              <p style=\"margin:0 0 12px;\">Your receipt and park entry tickets are ready. Each ticket has its own QR code, wallet link, and PDF. Each one deactivates only after that ticket is scanned.</p>
              <div style=\"margin:0 0 12px;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;\">Receipt</div>
              <table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;border-collapse:collapse;margin:8px 0 16px;\">
                <tr><td style=\"padding:6px 0;color:#6b7280;width:130px;\">Order #</td><td style=\"padding:6px 0;font-weight:600;\">{row.id}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Purchase date</td><td style=\"padding:6px 0;font-weight:600;\">{escape(purchased_text)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Amount paid</td><td style=\"padding:6px 0;font-weight:700;\">{escape(amount_text)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Payment</td><td style=\"padding:6px 0;font-weight:600;\">{escape(payment_status.title())} via {escape(payment_provider.title())}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Method</td><td style=\"padding:6px 0;font-weight:600;\">{escape(payment_card)}</td></tr>
              </table>
              <div style=\"margin:0 0 12px;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;\">Ticket</div>
              <table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;border-collapse:collapse;margin:8px 0 16px;\">
                <tr><td style=\"padding:6px 0;color:#6b7280;width:130px;\">Offer</td><td style=\"padding:6px 0;font-weight:600;\">{escape(offer_choice)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Park</td><td style=\"padding:6px 0;font-weight:600;\">{escape(selected_park)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Quantity</td><td style=\"padding:6px 0;font-weight:600;\">{escape(package_quantity)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Tickets issued</td><td style=\"padding:6px 0;font-weight:700;letter-spacing:0.03em;\">{ticket_count}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Expires</td><td style=\"padding:6px 0;font-weight:600;\">{escape(expires_text)}</td></tr>
              </table>
              <p style=\"margin:0 0 10px;\"><a href=\"{escape(account_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">Open your account</a></p>
              <div style=\"margin:18px 0 8px;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;\">Tickets</div>
              {"".join(ticket_cards_html)}
            </td>
          </tr>
        </table>
      </body>
    </html>
    """.strip()
    msg.add_alternative(html, subtype="html")
    if inline_qr_png:
        html_part = msg.get_payload()[-1]
        html_part.add_related(
            inline_qr_png,
            maintype="image",
            subtype="png",
            cid="<perknation-pass-qr>",
            filename="perknation-pass-qr.png",
            disposition="inline",
        )

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as smtp:
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as smtp:
                smtp.ehlo()
                if settings.smtp_use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send checkout pass email for submission %s: %s", row.id, exc)
        return False


def ensure_paid_order_pass(
    db: Session,
    row: WebLeadSubmission,
    *,
    notify_customer: bool = True,
) -> dict[str, Any]:
    payload = _parse_payload(row.payload_json)
    changed = False

    now_utc = _utcnow()
    payment_status = str(payload.get("payment_status") or "").strip().lower()

    if payment_status == "paid":
        if _checkout_wants_multi_ticket_bundle(payload):
            if _ensure_multi_ticket_payload(row.id, payload, now=now_utc):
                changed = True

            if notify_customer and row.email and not str(payload.get("pass_email_sent_at") or "").strip():
                if _send_checkout_pass_email(row, payload):
                    payload["pass_email_sent_at"] = _to_iso_utc(now_utc)
                    payload["pass_email_status"] = "sent"
                    changed = True
                else:
                    if str(payload.get("pass_email_status") or "") != "failed":
                        payload["pass_email_status"] = "failed"
                        changed = True

            if changed:
                row.payload_json = _dump_payload(payload)
                db.add(row)
                db.commit()
                db.refresh(row)

            return _parse_payload(row.payload_json)

        single_ticket_meta = _single_ticket_meta_for_payload(payload)
        for key, value in single_ticket_meta.items():
            if value not in (None, "") and payload.get(key) != value:
                payload[key] = value
                changed = True

        pass_code = str(payload.get("pass_code") or "").strip()
        if not pass_code:
            pass_code = _generate_pass_code(row.id)
            payload["pass_code"] = pass_code
            changed = True

        issued_at = _parse_iso_datetime(payload.get("pass_issued_at"))
        if not issued_at:
            issued_at = now_utc
            payload["pass_issued_at"] = _to_iso_utc(issued_at)
            changed = True

        expires_at = _parse_iso_datetime(payload.get("pass_expires_at"))
        if not expires_at:
            expires_at = issued_at + PASS_VALIDITY
            payload["pass_expires_at"] = _to_iso_utc(expires_at)
            changed = True

        current_pass_status = str(payload.get("pass_status") or "").strip().lower()
        if current_pass_status in {"", "pending", "payment_pending", "failed", "canceled"}:
            payload["pass_status"] = "active"
            changed = True

        pass_urls = _build_pass_urls(pass_code, pass_title=str(payload.get("pass_title") or "").strip() or None)
        for key, value in pass_urls.items():
            if str(payload.get(key) or "").strip() != value:
                payload[key] = value
                changed = True

        wallet_serial = _pass_wallet_serial_number(pass_code, payload["pass_view_url"])
        if str(payload.get("pass_wallet_serial_number") or "").strip() != wallet_serial:
            payload["pass_wallet_serial_number"] = wallet_serial
            changed = True

        if not str(payload.get("pass_wallet_auth_token") or "").strip():
            payload["pass_wallet_auth_token"] = secrets.token_urlsafe(32)
            changed = True

        if str(payload.get("pass_wallet_web_service_url") or "").strip() != _pass_wallet_web_service_url():
            payload["pass_wallet_web_service_url"] = _pass_wallet_web_service_url()
            changed = True

        if not str(payload.get("pass_wallet_last_updated_at") or "").strip():
            payload["pass_wallet_last_updated_at"] = payload["pass_issued_at"]
            changed = True

        if "pass_scan_count" not in payload:
            payload["pass_scan_count"] = 0
            changed = True

        if _refresh_expiration(payload, now=now_utc):
            changed = True

        if notify_customer and row.email and not str(payload.get("pass_email_sent_at") or "").strip():
            if _send_checkout_pass_email(row, payload):
                payload["pass_email_sent_at"] = _to_iso_utc(now_utc)
                payload["pass_email_status"] = "sent"
                changed = True
            else:
                if str(payload.get("pass_email_status") or "") != "failed":
                    payload["pass_email_status"] = "failed"
                    changed = True
    else:
        if _reconcile_unpaid_checkout_payload(payload, now=now_utc):
            changed = True
        if _refresh_expiration(payload, now=now_utc):
            changed = True

    if changed:
        row.payload_json = _dump_payload(payload)
        db.add(row)
        db.commit()
        db.refresh(row)

    return payload


def find_checkout_by_stripe_session_id(
    db: Session,
    session_id: str,
) -> Optional[tuple[WebLeadSubmission, dict[str, Any]]]:
    needle = str(session_id or "").strip()
    if not needle:
        return None

    rows = db.scalars(
        select(WebLeadSubmission)
        .where(
            WebLeadSubmission.form_type == "checkout",
            WebLeadSubmission.payload_json.ilike(f"%{needle}%"),
        )
        .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(250)
    ).all()

    for row in rows:
        payload = _parse_payload(row.payload_json)
        if str(payload.get("stripe_checkout_session_id") or "").strip() == needle:
            return row, payload

    return None


def _touch_expiration_if_needed(db: Session, row: WebLeadSubmission, payload: dict[str, Any]) -> dict[str, Any]:
    if _refresh_expiration(payload, now=_utcnow()):
        row.payload_json = _dump_payload(payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return _parse_payload(row.payload_json)
    return payload


def find_checkout_by_pass_code(
    db: Session,
    raw_code: str,
) -> Optional[tuple[WebLeadSubmission, dict[str, Any], str]]:
    lookup = find_checkout_ticket_by_pass_code(db, raw_code)
    if lookup is None:
        return None
    row, payload, pass_code, _, _ = lookup
    return row, payload, pass_code


def find_checkout_ticket_by_pass_code(
    db: Session,
    raw_code: str,
) -> Optional[tuple[WebLeadSubmission, dict[str, Any], str, int | None, dict[str, Any]]]:
    normalized = _extract_pass_code(raw_code)
    if not normalized:
        return None

    rows = db.scalars(
        select(WebLeadSubmission)
        .where(
            WebLeadSubmission.form_type == "checkout",
            WebLeadSubmission.payload_json.ilike(f"%{normalized}%"),
        )
        .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(250)
    ).all()

    for row in rows:
        payload = _parse_payload(row.payload_json)
        ticket_index, ticket, pass_code = _ticket_by_pass_code(payload, normalized)
        if ticket is not None:
            payload = _touch_expiration_if_needed(db, row, payload)
            ticket_index, ticket, pass_code = _ticket_by_pass_code(payload, normalized)
            if ticket is not None:
                return row, payload, pass_code, ticket_index, ticket

    return None


def _build_pass_record(
    row: WebLeadSubmission,
    payload: dict[str, Any],
    *,
    message: str,
    result_status: str,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pass_data = ticket if isinstance(ticket, dict) else payload
    ticket_count = len(_ticket_records(payload)) or int(payload.get("pass_ticket_count") or 1)
    return {
        "result_status": result_status,
        "message": message,
        "order_id": row.id,
        "created_at": row.created_at,
        "customer_name": _first_non_empty(row.name, row.contact_name, payload.get("full_name"), payload.get("name")),
        "email": row.email,
        "phone": _first_non_empty(row.phone, payload.get("phone")),
        "offer_choice": _first_non_empty(payload.get("offer_choice"), payload.get("selected_offer")),
        "selected_park": _first_non_empty(payload.get("selected_park"), payload.get("park")),
        "package_quantity": _first_non_empty(payload.get("package_quantity"), "1"),
        "ticket_number": pass_data.get("ticket_number"),
        "bundle_ticket_number": pass_data.get("bundle_ticket_number"),
        "ticket_type": _first_non_empty(pass_data.get("ticket_type"), ""),
        "pass_label": _first_non_empty(pass_data.get("pass_label"), ""),
        "pass_title": _first_non_empty(pass_data.get("pass_title"), ""),
        "pass_summary": _first_non_empty(pass_data.get("pass_summary"), ""),
        "pass_terms": pass_data.get("pass_terms") if isinstance(pass_data.get("pass_terms"), list) else [],
        "pass_ticket_count": ticket_count,
        "pass_code": _first_non_empty(pass_data.get("pass_code"), "") or "",
        "pass_status": _first_non_empty(pass_data.get("pass_status"), "unknown") or "unknown",
        "pass_issued_at": _parse_iso_datetime(pass_data.get("pass_issued_at")),
        "pass_expires_at": _parse_iso_datetime(pass_data.get("pass_expires_at")),
        "pass_redeemed_at": _parse_iso_datetime(pass_data.get("pass_redeemed_at")),
        "pass_scan_count": int(pass_data.get("pass_scan_count") or 0),
        "pass_account_url": _first_non_empty(pass_data.get("pass_account_url"), payload.get("pass_account_url"), _default_account_url()),
        "pass_wallet_url": _first_non_empty(pass_data.get("pass_wallet_url"), ""),
        "pass_google_wallet_url": _first_non_empty(pass_data.get("pass_google_wallet_url"), ""),
        "pass_pdf_url": _first_non_empty(pass_data.get("pass_pdf_url"), ""),
        "pass_view_url": _first_non_empty(pass_data.get("pass_view_url"), ""),
        "payment_amount_cents": payload.get("payment_amount_cents"),
        "payment_provider": _first_non_empty(payload.get("payment_provider"), ""),
        "payment_card_last4": _first_non_empty(payload.get("payment_card_last4"), ""),
        "payment_card_brand": _first_non_empty(payload.get("payment_card_brand"), ""),
    }


def scan_checkout_pass(
    db: Session,
    raw_code: str,
    *,
    scanner_email: str,
) -> dict[str, Any]:
    lookup = find_checkout_ticket_by_pass_code(db, raw_code)
    if lookup is None:
        return {
            "result_status": "invalid",
            "message": "Pass code was not found.",
            "order_id": None,
            "created_at": None,
            "customer_name": None,
            "email": None,
            "phone": None,
            "offer_choice": None,
            "selected_park": None,
            "package_quantity": None,
            "pass_code": _extract_pass_code(raw_code),
            "pass_status": "invalid",
            "pass_issued_at": None,
            "pass_expires_at": None,
            "pass_redeemed_at": None,
            "pass_scan_count": 0,
            "pass_account_url": _default_account_url(),
            "pass_wallet_url": "",
            "pass_view_url": "",
        }

    row, payload, pass_code, ticket_index, ticket = lookup
    payload = ensure_paid_order_pass(db, row, notify_customer=False)
    ticket_index, ticket, pass_code = _ticket_by_pass_code(payload, pass_code)
    pass_data = ticket if isinstance(ticket, dict) else payload

    payment_status = str(payload.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        return _build_pass_record(
            row,
            payload,
            message="This order is not fully paid yet. Entry pass is not active.",
            result_status="payment_pending",
            ticket=pass_data,
        )

    pass_status = str(pass_data.get("pass_status") or "").strip().lower()
    now_utc = _utcnow()
    changed = False

    if pass_status in {"", "active", "issued"}:
        expires_at = _parse_iso_datetime(pass_data.get("pass_expires_at"))
        if expires_at and now_utc >= expires_at:
            pass_data["pass_status"] = "expired"
            pass_data["pass_wallet_last_updated_at"] = _to_iso_utc(now_utc)
            pass_status = "expired"
            changed = True

    if pass_status == "expired":
        if ticket_index == 0:
            _sync_primary_pass_from_ticket(payload, pass_data)
        if changed:
            row.payload_json = _dump_payload(payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            payload = _parse_payload(row.payload_json)
        return _build_pass_record(
            row,
            payload,
            message="Pass is expired and can no longer be redeemed.",
            result_status="expired",
            ticket=pass_data,
        )

    if pass_status == "redeemed":
        return _build_pass_record(
            row,
            payload,
            message="Pass already scanned and deactivated.",
            result_status="already_redeemed",
            ticket=pass_data,
        )

    pass_data["pass_status"] = "redeemed"
    pass_data["pass_redeemed_at"] = _to_iso_utc(now_utc)
    pass_data["pass_redeemed_by"] = scanner_email.strip().lower()
    pass_data["pass_scan_count"] = int(pass_data.get("pass_scan_count") or 0) + 1
    pass_data["pass_wallet_last_updated_at"] = _to_iso_utc(now_utc)
    if ticket_index == 0 or pass_data is payload:
        _sync_primary_pass_from_ticket(payload, pass_data)
    row.payload_json = _dump_payload(payload)
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        wallet_pass_service.send_update_notifications(
            _wallet_registration_tokens(payload, pass_data),
            template="perknation",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Apple Wallet update notification failed for %s: %s", pass_code, exc)

    payload = _parse_payload(row.payload_json)
    _, pass_data, _ = _ticket_by_pass_code(payload, pass_code)
    return _build_pass_record(
        row,
        payload,
        message="Pass scanned successfully. Entry approved and pass is now deactivated.",
        result_status="redeemed",
        ticket=pass_data if isinstance(pass_data, dict) else payload,
    )


def list_recent_checkout_passes(db: Session, *, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(WebLeadSubmission)
        .where(
            WebLeadSubmission.form_type == "checkout",
            WebLeadSubmission.payload_json.ilike("%pass_code%"),
        )
        .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(max(1, min(int(limit), 500)))
    ).all()

    out: list[dict[str, Any]] = []
    changed_any = False

    for row in rows:
        payload = _parse_payload(row.payload_json)
        if _refresh_expiration(payload, now=_utcnow()):
            row.payload_json = _dump_payload(payload)
            db.add(row)
            changed_any = True

        tickets = _ticket_records(payload)
        if tickets:
            for ticket in tickets:
                pass_code = str(ticket.get("pass_code") or "").strip()
                if not pass_code:
                    continue
                out.append(
                    _build_pass_record(
                        row,
                        payload,
                        message="",
                        result_status="record",
                        ticket=ticket,
                    )
                )
            continue

        pass_code = str(payload.get("pass_code") or "").strip()
        if pass_code:
            out.append(
                _build_pass_record(
                    row,
                    payload,
                    message="",
                    result_status="record",
                )
            )

    if changed_any:
        db.commit()

    return out


def find_checkout_by_wallet_serial(
    db: Session,
    serial_number: str,
) -> Optional[tuple[WebLeadSubmission, dict[str, Any]]]:
    lookup = find_checkout_ticket_by_wallet_serial(db, serial_number)
    if lookup is None:
        return None
    row, payload, _, _ = lookup
    return row, payload


def find_checkout_ticket_by_wallet_serial(
    db: Session,
    serial_number: str,
) -> Optional[tuple[WebLeadSubmission, dict[str, Any], int | None, dict[str, Any]]]:
    needle = str(serial_number or "").strip()
    if not needle:
        return None

    rows = db.scalars(
        select(WebLeadSubmission)
        .where(
            WebLeadSubmission.form_type == "checkout",
            WebLeadSubmission.payload_json.ilike(f"%{needle}%"),
        )
        .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(50)
    ).all()

    for row in rows:
        payload = _parse_payload(row.payload_json)
        for idx, ticket in enumerate(_ticket_records(payload)):
            if str(ticket.get("pass_wallet_serial_number") or "").strip() == needle:
                return row, payload, idx, ticket
        if str(payload.get("pass_wallet_serial_number") or "").strip() == needle:
            return row, payload, None, payload

    return None


def wallet_pass_authorized(
    payload: dict[str, Any],
    authorization: str | None,
    *,
    ticket: dict[str, Any] | None = None,
) -> bool:
    source = ticket if isinstance(ticket, dict) else payload
    expected = str(source.get("pass_wallet_auth_token") or "").strip()
    if not expected:
        return False
    header = str(authorization or "").strip()
    if header.lower().startswith("applepass "):
        header = header.split(" ", 1)[1].strip()
    return bool(header) and secrets.compare_digest(header, expected)


def register_wallet_device(
    db: Session,
    row: WebLeadSubmission,
    payload: dict[str, Any],
    *,
    device_library_identifier: str,
    push_token: str,
    ticket_index: int | None = None,
    ticket: dict[str, Any] | None = None,
) -> bool:
    source = ticket if isinstance(ticket, dict) else payload
    registrations = source.get("pass_wallet_registrations")
    if not isinstance(registrations, dict):
        registrations = {}

    device_key = str(device_library_identifier or "").strip()
    token = str(push_token or "").strip()
    if not device_key or not token:
        return False

    existing = registrations.get(device_key)
    is_new = not isinstance(existing, dict) or str(existing.get("pushToken") or "").strip() != token
    registrations[device_key] = {
        "pushToken": token,
        "registered_at": _to_iso_utc(_utcnow()),
    }
    source["pass_wallet_registrations"] = registrations
    if ticket_index == 0:
        _sync_primary_pass_from_ticket(payload, source)
    row.payload_json = _dump_payload(payload)
    db.add(row)
    db.commit()
    return is_new


def unregister_wallet_device(
    db: Session,
    row: WebLeadSubmission,
    payload: dict[str, Any],
    *,
    device_library_identifier: str,
    ticket_index: int | None = None,
    ticket: dict[str, Any] | None = None,
) -> None:
    source = ticket if isinstance(ticket, dict) else payload
    registrations = source.get("pass_wallet_registrations")
    if not isinstance(registrations, dict):
        return

    device_key = str(device_library_identifier or "").strip()
    if not device_key or device_key not in registrations:
        return

    registrations.pop(device_key, None)
    source["pass_wallet_registrations"] = registrations
    if ticket_index == 0:
        _sync_primary_pass_from_ticket(payload, source)
    row.payload_json = _dump_payload(payload)
    db.add(row)
    db.commit()


def list_wallet_pass_updates_for_device(
    db: Session,
    *,
    device_library_identifier: str,
    passes_updated_since: str | None,
    limit: int = 200,
) -> dict[str, Any]:
    device_key = str(device_library_identifier or "").strip()
    if not device_key:
        return {"lastUpdated": _to_iso_utc(_utcnow()), "serialNumbers": []}

    since_dt = _parse_iso_datetime(passes_updated_since)
    rows = db.scalars(
        select(WebLeadSubmission)
        .where(
            WebLeadSubmission.form_type == "checkout",
            WebLeadSubmission.payload_json.ilike(f"%{device_key}%"),
        )
        .order_by(WebLeadSubmission.created_at.desc(), WebLeadSubmission.id.desc())
        .limit(max(1, min(int(limit), 500)))
    ).all()

    serials: list[str] = []
    last_updated = _utcnow()
    for row in rows:
        payload = _parse_payload(row.payload_json)
        records = _ticket_records(payload) or [payload]
        for record in records:
            registrations = record.get("pass_wallet_registrations")
            if not isinstance(registrations, dict) or device_key not in registrations:
                continue

            updated_raw = str(record.get("pass_wallet_last_updated_at") or record.get("pass_issued_at") or "").strip()
            updated_at = _parse_iso_datetime(updated_raw) or row.created_at
            if since_dt and updated_at <= since_dt:
                continue

            serial = str(record.get("pass_wallet_serial_number") or "").strip()
            if serial and serial not in serials:
                serials.append(serial)
            if updated_at and updated_at > last_updated:
                last_updated = updated_at

    return {"lastUpdated": _to_iso_utc(last_updated), "serialNumbers": serials}
