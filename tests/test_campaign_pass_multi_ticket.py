import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import WebLeadSubmission
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
        name="Live QA Buyer",
        email="qa@example.com",
        phone="555-0100",
        payload_json=json.dumps(payload),
        created_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_live_qa_purchase_mints_twelve_independent_tickets():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 100,
            "payment_provider": "stripe",
            "offer_choice": "$1 Mini Test Pass (Live QA)",
            "selected_park": "Hollywood Sports - Bellflower",
            "package_quantity": "1",
        },
    )

    payload = ensure_paid_order_pass(db, row, notify_customer=False)

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

    lookup = find_checkout_ticket_by_pass_code(db, tickets[5]["pass_code"])
    assert lookup is not None
    assert lookup[3] == 5
    assert lookup[4]["pass_code"] == tickets[5]["pass_code"]


def test_scanning_one_live_qa_ticket_does_not_deactivate_siblings():
    db = _db_session()
    row = _checkout_row(
        db,
        {
            "payment_status": "paid",
            "payment_amount_cents": 100,
            "offer_choice": "$1 Mini Test Pass (Live QA)",
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


def test_non_qa_purchase_keeps_single_pass_shape():
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
