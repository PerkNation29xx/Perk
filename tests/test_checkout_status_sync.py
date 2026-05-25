from app.api.v1.payments import _derive_checkout_status
from app.services.campaign_passes import _reconcile_unpaid_checkout_payload


def test_checkout_status_is_paid_when_checkout_session_is_paid():
    assert _derive_checkout_status({"payment_status": "paid", "status": "complete"}) == "paid"


def test_checkout_status_is_paid_when_payment_intent_succeeded():
    assert (
        _derive_checkout_status(
            {
                "payment_status": "unpaid",
                "status": "complete",
                "payment_intent": {"status": "succeeded"},
            }
        )
        == "paid"
    )


def test_checkout_status_is_failed_when_payment_intent_canceled():
    assert (
        _derive_checkout_status(
            {
                "payment_status": "unpaid",
                "status": "complete",
                "payment_intent": {"status": "canceled"},
            }
        )
        == "failed"
    )


def test_expired_payment_closes_pending_pass_status():
    payload = {"payment_status": "expired", "pass_status": ""}

    changed = _reconcile_unpaid_checkout_payload(payload)

    assert changed is True
    assert payload["pass_status"] == "expired"


def test_unpaid_checkout_without_pass_becomes_payment_pending():
    payload = {"payment_status": "checkout_created", "pass_status": ""}

    changed = _reconcile_unpaid_checkout_payload(payload)

    assert changed is True
    assert payload["pass_status"] == "payment_pending"
