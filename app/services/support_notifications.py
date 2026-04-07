from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.db.models import WebLeadSubmission

logger = logging.getLogger(__name__)


def _smtp_ready() -> bool:
    return bool(settings.smtp_host and settings.contact_form_notify_email)


def send_contact_submission_email(row: WebLeadSubmission) -> bool:
    """
    Best-effort email notification for contact-form submissions.

    Returns True when email dispatch succeeds, False when disabled/unconfigured
    or when SMTP send fails.
    """

    if not settings.contact_email_forwarding_enabled:
        return False
    if not _smtp_ready():
        logger.info("Contact email forwarding skipped: SMTP is not configured.")
        return False

    recipient = settings.contact_form_notify_email.strip()
    if not recipient:
        return False

    sender = (
        (settings.smtp_from_email or "").strip()
        or (settings.smtp_username or "").strip()
        or "no-reply@perknation.net"
    )

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient

    if row.form_type == "checkout":
        msg["Subject"] = f"PerkNation Checkout Request #{row.id}"
        plain = (
            "New PerkNation checkout request\n\n"
            f"Submission ID: {row.id}\n"
            f"Created At: {row.created_at}\n"
            f"Source Page: {row.source_page or ''}\n"
            f"Name: {row.name or ''}\n"
            f"Email: {row.email or ''}\n"
            f"Phone: {row.phone or ''}\n"
            f"Summary:\n{row.inquiry or ''}\n"
        )
    else:
        msg["Subject"] = f"PerkNation Contact Submission #{row.id}"
        plain = (
            "New Contact Us submission\n\n"
            f"Submission ID: {row.id}\n"
            f"Created At: {row.created_at}\n"
            f"Source Page: {row.source_page or ''}\n"
            f"Name: {row.name or ''}\n"
            f"Email: {row.email or ''}\n"
            f"Phone: {row.phone or ''}\n"
            f"Inquiry:\n{row.inquiry or ''}\n"
        )
    msg.set_content(plain)

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
        logger.exception("Failed to send contact submission email: %s", exc)
        return False
