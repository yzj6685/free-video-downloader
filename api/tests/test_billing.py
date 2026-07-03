from app.services.billing_service import BillingService, BillingStore


def test_billing_store_fulfills_paid_checkout(tmp_path):
    store = BillingStore(str(tmp_path / "billing.sqlite3"))
    session = {
        "id": "cs_test_paid",
        "customer_email": "USER@example.com",
        "payment_status": "paid",
        "amount_total": 1990,
        "currency": "cny",
        "metadata": {"plan_id": "pro", "email": "user@example.com"},
    }

    assert store.fulfill_checkout_session(session, "evt_test") is True

    entitlement = store.get_entitlement("user@example.com")
    assert entitlement.active is True
    assert entitlement.plan_id == "pro"


def test_billing_store_does_not_fulfill_unpaid_checkout(tmp_path):
    store = BillingStore(str(tmp_path / "billing.sqlite3"))
    session = {
        "id": "cs_test_unpaid",
        "customer_email": "user@example.com",
        "payment_status": "unpaid",
        "metadata": {"plan_id": "pro"},
    }

    assert store.fulfill_checkout_session(session, "evt_test") is False
    assert store.get_entitlement("user@example.com").active is False


def test_billing_store_tracks_free_ai_usage(tmp_path):
    store = BillingStore(str(tmp_path / "billing.sqlite3"))

    entitlement = store.get_entitlement("user@example.com")
    assert entitlement.free_limit == 3
    assert entitlement.free_used == 0
    assert entitlement.free_remaining == 3

    assert store.increment_ai_usage("user@example.com") == 1
    assert store.increment_ai_usage("user@example.com") == 2

    entitlement = store.get_entitlement("user@example.com")
    assert entitlement.free_used == 2
    assert entitlement.free_remaining == 1


def test_billing_service_allows_three_free_analyses_then_requires_pro(tmp_path):
    service = BillingService(BillingStore(str(tmp_path / "billing.sqlite3")))

    for _ in range(3):
        service.ensure_ai_analysis_allowed("free@example.com")
        service.record_ai_analysis_success("free@example.com")

    try:
        service.ensure_ai_analysis_allowed("free@example.com")
    except Exception as exc:
        assert getattr(exc, "status_code") == 402
    else:
        raise AssertionError("Expected free quota exhaustion to be rejected")


def test_billing_service_requires_pro_entitlement(tmp_path):
    service = BillingService(BillingStore(str(tmp_path / "billing.sqlite3")))

    try:
        service.require_pro_entitlement("missing@example.com")
    except Exception as exc:
        assert getattr(exc, "status_code") == 402
    else:
        raise AssertionError("Expected missing entitlement to be rejected")


def test_billing_service_rejects_checkout_for_existing_pro(tmp_path):
    store = BillingStore(str(tmp_path / "billing.sqlite3"))
    service = BillingService(store)
    store.fulfill_checkout_session(
        {
            "id": "cs_existing_paid",
            "customer_email": "pro@example.com",
            "payment_status": "paid",
            "metadata": {"plan_id": "pro"},
        },
        "evt_existing",
    )

    try:
        service.create_checkout("pro@example.com")
    except Exception as exc:
        assert getattr(exc, "status_code") == 409
    else:
        raise AssertionError("Expected existing Pro checkout to be rejected")


def test_billing_service_handles_checkout_completed_event(tmp_path):
    service = BillingService(BillingStore(str(tmp_path / "billing.sqlite3")))
    event = {
        "id": "evt_completed",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_completed",
                "customer_email": "buyer@example.com",
                "payment_status": "paid",
                "metadata": {"plan_id": "pro"},
            }
        },
    }

    result = service.handle_webhook_event(event)

    assert result == {"received": True, "fulfilled": True}
    service.require_pro_entitlement("buyer@example.com")
