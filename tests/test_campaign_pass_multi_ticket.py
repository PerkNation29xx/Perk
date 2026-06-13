import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import User, WebLeadSubmission
from app.api.v1.payments import _offer_pricing, checkout_status
from app.services.campaign_passes import (
    ensure_paid_order_pass,
    find_checkout_ticket_by_pass_code,
    scan_checkout_pass,
)


def _db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return SessionLocal()


def _checkout_row(db, payload: dict) -> WebLeadSubmission:
    row = WebLeadSubmission(
        form_type="checkout",
        source_page="/hollywood-sports",
        name="Bundle Buyer",
        email="qa@example.com",
        phone="555-0100",
        payload_json=json.dumps(payload),
        created_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _assert_hsp_bundle_ticket_mix(payload: dict) -> None:
    tickets = payload["pass_tickets"]
    codes = [ticket["pass_code"] for ticket in tickets]
    assert len(tickets) == 12
    assert len(set(codes)) == 12
    assert payload["pass_ticket_count"] == 12
    assert payload["pass_delivery_mode"] == "multi_ticket"
    assert payload["pass_code"] == tickets[0]["pass_code"]
    assert all(ticket["pass_status"] == "active" for ticket in tickets)
    assert all(ticket["pass_wallet_url"] for ticket in tickets)
    assert all(ticket["pass_pdf_url"].endswith("/pdf") for ticket in tickets)

    regular = tickets[:11]
    golden = tickets[11]
    assert all(ticket["ticket_type"] == "regular_entry" for ticket in regular)
    assert all(ticket["pass_title"] == "Regular Entry Ticket" for ticket in regular)
    assert all("paintball marker" in " ".join(ticket["pass_terms"]).lower() for ticket in regular)
    assert golden["ticket_type"] == "golden_ticket"
    assert golden["pass_title"] == "Golden Ticket"
    assert "200 paintballs" in golden["pass_summary"].lower()
    assert any("walk-ons" in term.lower() for term in golden["pass_terms"])


def test_sixty_dollar_package_mints_eleven_regular_and_one_golden_ticket():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 6000,
            "payment_provider": "stripe",
            "offer_choice": "$60 Bundle (12 park passes, $500+ value)",
            "selected_park": "Hollywood Sports - Bellflower",
            "package_quantity": "1",
        },
    )

    payload = ensure_paid_order_pass(db, row, notify_customer=False)

    _assert_hsp_bundle_ticket_mix(payload)

    lookup = find_checkout_ticket_by_pass_code(db, payload["pass_tickets"][5]["pass_code"])
    assert lookup is not None
    assert lookup[3] == 5
    assert lookup[4]["pass_code"] == payload["pass_tickets"][5]["pass_code"]


def test_legacy_seventy_dollar_package_label_still_mints_bundle_ticket_mix():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 6000,
            "payment_provider": "stripe",
            "offer_choice": "$70 Bundle (12 park passes, $500+ value)",
            "selected_park": "Hollywood Sports - Bellflower",
            "package_quantity": "1",
        },
    )

    payload = ensure_paid_order_pass(db, row, notify_customer=False)

    _assert_hsp_bundle_ticket_mix(payload)


def test_scanning_one_bundle_ticket_does_not_deactivate_siblings():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 6000,
            "offer_choice": "$60 Bundle (12 park passes, $500+ value)",
            "selected_park": "Hollywood Sports - Bellflower",
        },
    )
    payload = ensure_paid_order_pass(db, row, notify_customer=False)
    first_code = payload["pass_tickets"][0]["pass_code"]
    second_code = payload["pass_tickets"][1]["pass_code"]

    result = scan_checkout_pass(db, first_code, scanner_email="scanner@perknation.app")

    assert result["result_status"] == "redeemed"
    refreshed = json.loads(db.get(WebLeadSubmission, row.id).payload_json)
    assert refreshed["pass_tickets"][0]["pass_status"] == "redeemed"
    assert refreshed["pass_tickets"][0]["pass_scan_count"] == 1
    assert refreshed["pass_tickets"][1]["pass_status"] == "active"
    assert refreshed["pass_tickets"][1]["pass_scan_count"] == 0
    assert refreshed["pass_status"] == "redeemed"

    duplicate = scan_checkout_pass(db, first_code, scanner_email="scanner@perknation.app")
    assert duplicate["result_status"] == "already_redeemed"

    sibling = scan_checkout_pass(db, second_code, scanner_email="scanner@perknation.app")
    assert sibling["result_status"] == "redeemed"


def test_five_dollar_purchase_keeps_single_entry_only_pass_shape():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 500,
            "offer_choice": "$5 Admission Promo",
            "selected_park": "Hollywood Sports - Bellflower",
        },
    )

    payload = ensure_paid_order_pass(db, row, notify_customer=False)

    assert payload["pass_code"].startswith("PKI-HSP-")
    assert "pass_tickets" not in payload
    assert payload["pass_status"] == "active"
    assert payload["ticket_type"] == "entry_only"
    assert payload["pass_title"] == "$5 Entry Only Pass"
    assert payload["pass_summary"] == "Entry only"


def test_checkout_status_redacts_ticket_details_without_matching_account():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 6000,
            "payment_provider": "stripe",
            "stripe_checkout_session_id": "cs_test_secure_bundle",
            "account_user_id": "42",
            "account_email": "buyer@example.com",
            "offer_choice": "$60 Bundle (12 park passes, $500+ value)",
            "selected_park": "Hollywood Sports - Bellflower",
        },
    )

    body = checkout_status(session_id="cs_test_secure_bundle", db=db, current_user=None)

    assert body.submission_id == row.id
    assert body.pass_details_locked is True
    assert body.pass_tickets is None
    assert body.pass_code is None
    assert body.pass_wallet_url is None
    assert body.pass_pdf_url is None
    assert body.pass_qr_payload is None
    assert body.email is None


def test_checkout_status_returns_ticket_details_for_matching_account():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 6000,
            "payment_provider": "stripe",
            "stripe_checkout_session_id": "cs_test_secure_bundle_owner",
            "account_user_id": "42",
            "account_email": "buyer@example.com",
            "offer_choice": "$60 Bundle (12 park passes, $500+ value)",
            "selected_park": "Hollywood Sports - Bellflower",
        },
    )
    user = User(id=42, full_name="Buyer", email="buyer@example.com")

    body = checkout_status(session_id="cs_test_secure_bundle_owner", db=db, current_user=user)

    assert body.submission_id == row.id
    assert body.pass_details_locked is False
    assert body.pass_tickets is not None
    assert len(body.pass_tickets) == 12
    assert body.pass_code


def test_sixty_dollar_bundle_pricing_charges_sixty_dollars():
    pricing = _offer_pricing("$60 Bundle (12 park passes, $500+ value)")

    assert pricing.label == "$60 Bundle (12 park passes, $500+ value)"
    assert pricing.unit_amount_cents == 6000


def test_legacy_seventy_dollar_bundle_pricing_alias_charges_sixty_dollars():
    pricing = _offer_pricing("$70 Bundle (12 park passes, $500+ value)")

    assert pricing.label == "$60 Bundle (12 park passes, $500+ value)"
    assert pricing.unit_amount_cents == 6000


def test_one_dollar_live_qa_pricing_is_removed():
    with pytest.raises(HTTPException):
        _offer_pricing("$1 Mini Test Pass (Live QA)")
