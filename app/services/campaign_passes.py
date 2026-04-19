from __future__ import annotations

import json
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import WebLeadSubmission

logger = logging.getLogger(__name__)

PASS_VALIDITY = timedelta(days=365)
PASS_CODE_PREFIX = "PKI-HSP"


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
    return (settings.public_web_base_url or "https://perknation.net").rstrip("/")


def _api_base_url() -> str:
    base = _web_base_url()
    prefix = (settings.api_v1_prefix or "/v1").strip()
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return f"{base}{prefix}"


def _default_account_url() -> str:
    return f"{_web_base_url()}/login"


def _generate_pass_code(row_id: int) -> str:
    token = secrets.token_hex(3).upper()
    return f"{PASS_CODE_PREFIX}-{int(row_id):06d}-{token}"


def _build_pass_urls(pass_code: str) -> dict[str, str]:
    api_base = _api_base_url()
    pass_view_url = f"{api_base}/web/payments/pass/{quote(pass_code, safe='')}"
    wallet_query = urlencode(
        {
            "title": "PerkNation Park Entry Pass",
            "code": pass_code,
            "payload": pass_view_url,
            "template": "perknation",
        }
    )
    wallet_pass_url = f"{api_base}/wallet/pass?{wallet_query}"
    return {
        "pass_view_url": pass_view_url,
        "pass_qr_payload": pass_view_url,
        "pass_wallet_url": wallet_pass_url,
        "pass_account_url": _default_account_url(),
    }


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
    if not expires_at:
        return changed

    if status_value in {"", "active", "issued"} and now_utc >= expires_at:
        payload["pass_status"] = "expired"
        changed = True

    return changed


def _smtp_ready() -> bool:
    return bool(settings.smtp_host)


def _send_checkout_pass_email(row: WebLeadSubmission, payload: dict[str, Any]) -> bool:
    recipient = (row.email or "").strip()
    if not recipient or not _smtp_ready():
        return False

    sender = (
        (settings.smtp_from_email or "").strip()
        or (settings.smtp_username or "").strip()
        or "no-reply@perknation.net"
    )

    customer_name = _first_non_empty(row.name, row.contact_name, payload.get("full_name")) or "PerkNation member"
    offer_choice = _first_non_empty(payload.get("offer_choice"), payload.get("selected_offer")) or "Hollywood Sports campaign"
    selected_park = _first_non_empty(payload.get("selected_park"), payload.get("park")) or "Participating park"
    package_quantity = _first_non_empty(payload.get("package_quantity"), "1 package")
    pass_code = str(payload.get("pass_code") or "").strip()
    expires_at = _parse_iso_datetime(payload.get("pass_expires_at"))
    expires_text = expires_at.strftime("%B %d, %Y") if expires_at else "One year from purchase"

    account_url = str(payload.get("pass_account_url") or _default_account_url()).strip()
    wallet_pass_url = str(payload.get("pass_wallet_url") or "").strip()
    pass_view_url = str(payload.get("pass_view_url") or "").strip()

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "Your PerkNation park entry pass"

    plain_lines = [
        f"Hi {customer_name},",
        "",
        "Thanks for your PerkNation purchase.",
        "",
        f"Offer: {offer_choice}",
        f"Park: {selected_park}",
        f"Quantity: {package_quantity}",
        f"Pass code: {pass_code}",
        f"Expires: {expires_text}",
        "",
        f"Account: {account_url}",
        f"Wallet pass: {wallet_pass_url}",
        f"Pass page: {pass_view_url}",
        "",
        "This pass is valid for one year and will be deactivated after it is scanned at the park.",
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
              <h1 style=\"margin:0;font-size:20px;\">PerkNation Entry Pass</h1>
              <p style=\"margin:8px 0 0;font-size:13px;color:#cbd5e1;\">Your purchase is confirmed and your pass is ready.</p>
            </td>
          </tr>
          <tr>
            <td style=\"padding:18px 20px;\">
              <p style=\"margin:0 0 12px;\">Hi {escape(customer_name)},</p>
              <p style=\"margin:0 0 12px;\">Use this pass at check-in. It expires in one year and deactivates after the first successful scan.</p>
              <table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"width:100%;border-collapse:collapse;margin:8px 0 16px;\">
                <tr><td style=\"padding:6px 0;color:#6b7280;width:130px;\">Offer</td><td style=\"padding:6px 0;font-weight:600;\">{escape(offer_choice)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Park</td><td style=\"padding:6px 0;font-weight:600;\">{escape(selected_park)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Quantity</td><td style=\"padding:6px 0;font-weight:600;\">{escape(package_quantity)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Pass code</td><td style=\"padding:6px 0;font-weight:700;letter-spacing:0.03em;\">{escape(pass_code)}</td></tr>
                <tr><td style=\"padding:6px 0;color:#6b7280;\">Expires</td><td style=\"padding:6px 0;font-weight:600;\">{escape(expires_text)}</td></tr>
              </table>
              <p style=\"margin:0 0 10px;\"><a href=\"{escape(account_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">Open your account</a></p>
              <p style=\"margin:0 0 10px;\"><a href=\"{escape(wallet_pass_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">Add pass to Apple Wallet</a></p>
              <p style=\"margin:0 0 14px;\"><a href=\"{escape(pass_view_url, quote=True)}\" style=\"color:#0f5bd8;font-weight:600;\">View pass + scan link</a></p>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """.strip()
    msg.add_alternative(html, subtype="html")

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

        if not str(payload.get("pass_status") or "").strip():
            payload["pass_status"] = "active"
            changed = True

        pass_urls = _build_pass_urls(pass_code)
        for key, value in pass_urls.items():
            if str(payload.get(key) or "").strip() != value:
                payload[key] = value
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
        pass_code = str(payload.get("pass_code") or "").strip()
        if pass_code.lower() == normalized.lower():
            payload = _touch_expiration_if_needed(db, row, payload)
            return row, payload, pass_code

    return None


def _build_pass_record(
    row: WebLeadSubmission,
    payload: dict[str, Any],
    *,
    message: str,
    result_status: str,
) -> dict[str, Any]:
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
        "pass_code": _first_non_empty(payload.get("pass_code"), "") or "",
        "pass_status": _first_non_empty(payload.get("pass_status"), "unknown") or "unknown",
        "pass_issued_at": _parse_iso_datetime(payload.get("pass_issued_at")),
        "pass_expires_at": _parse_iso_datetime(payload.get("pass_expires_at")),
        "pass_redeemed_at": _parse_iso_datetime(payload.get("pass_redeemed_at")),
        "pass_scan_count": int(payload.get("pass_scan_count") or 0),
        "pass_account_url": _first_non_empty(payload.get("pass_account_url"), _default_account_url()),
        "pass_wallet_url": _first_non_empty(payload.get("pass_wallet_url"), ""),
        "pass_view_url": _first_non_empty(payload.get("pass_view_url"), ""),
    }


def scan_checkout_pass(
    db: Session,
    raw_code: str,
    *,
    scanner_email: str,
) -> dict[str, Any]:
    lookup = find_checkout_by_pass_code(db, raw_code)
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

    row, payload, pass_code = lookup
    payload = ensure_paid_order_pass(db, row, notify_customer=False)

    payment_status = str(payload.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        return _build_pass_record(
            row,
            payload,
            message="This order is not fully paid yet. Entry pass is not active.",
            result_status="payment_pending",
        )

    pass_status = str(payload.get("pass_status") or "").strip().lower()
    now_utc = _utcnow()
    changed = False

    if pass_status in {"", "active", "issued"}:
        expires_at = _parse_iso_datetime(payload.get("pass_expires_at"))
        if expires_at and now_utc >= expires_at:
            payload["pass_status"] = "expired"
            pass_status = "expired"
            changed = True

    if pass_status == "expired":
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
        )

    if pass_status == "redeemed":
        return _build_pass_record(
            row,
            payload,
            message="Pass already scanned and deactivated.",
            result_status="already_redeemed",
        )

    payload["pass_status"] = "redeemed"
    payload["pass_redeemed_at"] = _to_iso_utc(now_utc)
    payload["pass_redeemed_by"] = scanner_email.strip().lower()
    payload["pass_scan_count"] = int(payload.get("pass_scan_count") or 0) + 1
    row.payload_json = _dump_payload(payload)
    db.add(row)
    db.commit()
    db.refresh(row)

    payload = _parse_payload(row.payload_json)
    return _build_pass_record(
        row,
        payload,
        message="Pass scanned successfully. Entry approved and pass is now deactivated.",
        result_status="redeemed",
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
        pass_code = str(payload.get("pass_code") or "").strip()
        if not pass_code:
            continue

        if _refresh_expiration(payload, now=_utcnow()):
            row.payload_json = _dump_payload(payload)
            db.add(row)
            changed_any = True

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
