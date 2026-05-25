from app.api.v1.payments import _derive_checkout_status


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
