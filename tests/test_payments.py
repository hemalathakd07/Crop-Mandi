import hashlib
import hmac
import json
from pathlib import Path

from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.errors import ApiError
from apps.api.payments import DEMO_USER_CODE, ensure_demo_user
from cropmandi.db.models import Payment, PaymentWebhookEvent, User
from cropmandi.db.session import create_all, make_session_factory


TEST_KEY_SECRET = "unit_test_key_secret"
TEST_WEBHOOK_SECRET = "unit_test_webhook_secret"
ROOT = Path(__file__).resolve().parents[1]


def _setup(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'payments.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_unit")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", TEST_KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)
    create_all(url)
    factory = make_session_factory(url)
    api_main.SessionLocal = factory
    api_main.app.state.session_factory = factory
    return factory


def _sign_payment(order_id, payment_id, secret=TEST_KEY_SECRET):
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _sign_webhook(body: bytes, secret=TEST_WEBHOOK_SECRET):
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _add_payment(session, user, order_id="order_ok", status="CREATED"):
    row = Payment(
        user_id=user.id,
        receipt=f"rcpt-{order_id}",
        razorpay_order_id=order_id,
        amount_paise=10000,
        currency="INR",
        crop="coffee",
        quantity="10",
        status=status,
    )
    session.add(row)
    session.commit()
    return row


def test_create_order_rejects_non_positive_amount(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(api_main.app)
    zero = client.post("/api/payment/create-order", json={"amount": 0, "crop": "coffee", "quantity": 10})
    negative = client.post("/api/payment/create-order", json={"amount": -5, "crop": "coffee", "quantity": 10})
    assert zero.status_code == 400
    assert negative.status_code == 400
    assert zero.json()["error"] == "invalid_amount"


def test_create_order_rejects_tampered_amount(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/create-order",
        json={"amount": 2500, "crop": "coffee", "quantity": 50},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_amount"


def test_create_order_missing_amount_uses_server_price(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)

    def fake_create(amount_paise, currency, receipt, notes):
        assert amount_paise == 10000
        return {"id": "order_missing_amt", "amount": amount_paise, "currency": currency}

    monkeypatch.setattr("apps.api.razorpay_service.create_order", fake_create)
    client = TestClient(api_main.app)
    response = client.post("/api/payment/create-order", json={"crop": "coffee", "quantity": 10})
    assert response.status_code == 200
    assert response.json()["amount"] == 10000
    session = factory()
    assert session.query(Payment).filter_by(razorpay_order_id="order_missing_amt").one().amount_paise == 10000
    session.close()


def test_create_order_persists_mocked_razorpay_order(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)

    def fake_create(amount_paise, currency, receipt, notes):
        assert amount_paise == 10000
        assert currency == "INR"
        assert notes["crop"] == "coffee"
        assert receipt
        return {"id": "order_mocked_1", "amount": amount_paise, "currency": currency}

    monkeypatch.setattr("apps.api.razorpay_service.create_order", fake_create)
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/create-order",
        json={"amount": 100, "crop": "coffee", "quantity": 50, "listing_id": "c5-mysuru"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"success", "key_id", "order_id", "amount", "currency"}
    dumped = json.dumps(body).lower()
    assert "key_secret" not in dumped
    assert "webhook" not in dumped
    assert TEST_KEY_SECRET not in dumped
    assert body["success"] is True
    assert body["order_id"] == "order_mocked_1"
    assert body["amount"] == 10000
    assert body["currency"] == "INR"
    session = factory()
    row = session.query(Payment).filter_by(razorpay_order_id="order_mocked_1").one()
    user = session.query(User).filter_by(code=DEMO_USER_CODE).one()
    assert row.user_id == user.id
    assert user.is_demo is True
    assert row.crop == "coffee"
    assert row.listing_id == "c5-mysuru"
    assert row.status == "CREATED"
    session.close()


def test_create_order_handles_razorpay_failure(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def fake_create(*_args, **_kwargs):
        raise ApiError(502, "razorpay_order_failed", "Unable to create payment order.")

    monkeypatch.setattr("apps.api.razorpay_service.create_order", fake_create)
    client = TestClient(api_main.app)
    response = client.post("/api/payment/create-order", json={"crop": "pepper", "quantity": 1})
    assert response.status_code == 502
    body = response.json()
    assert body["error"] == "razorpay_order_failed"
    assert TEST_KEY_SECRET not in json.dumps(body)


def test_verify_rejects_invalid_signature(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    user = ensure_demo_user(session)
    _add_payment(session, user, "order_bad_sig")
    session.close()
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/verify",
        json={
            "razorpay_order_id": "order_bad_sig",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "deadbeef",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_signature"
    session = factory()
    assert session.query(Payment).filter_by(razorpay_order_id="order_bad_sig").one().status == "CREATED"
    session.close()


def test_verify_rejects_unknown_order_id(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(api_main.app)
    signature = _sign_payment("order_missing", "pay_ok")
    response = client.post(
        "/api/payment/verify",
        json={
            "razorpay_order_id": "order_missing",
            "razorpay_payment_id": "pay_ok",
            "razorpay_signature": signature,
        },
    )
    assert response.status_code == 404


def test_verify_accepts_valid_signature(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    user = ensure_demo_user(session)
    _add_payment(session, user, "order_ok")
    session.close()
    monkeypatch.setattr(
        "apps.api.razorpay_service.fetch_payment",
        lambda _pid: {"id": "pay_ok", "order_id": "order_ok", "status": "captured"},
    )
    signature = _sign_payment("order_ok", "pay_ok")
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/verify",
        json={
            "razorpay_order_id": "order_ok",
            "razorpay_payment_id": "pay_ok",
            "razorpay_signature": signature,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert "key_secret" not in json.dumps(body).lower()
    session = factory()
    row = session.query(Payment).filter_by(razorpay_order_id="order_ok").one()
    assert row.status == "CAPTURED"
    assert row.signature_verified is True
    assert row.razorpay_payment_id == "pay_ok"
    session.close()


def test_verify_duplicate_is_idempotent(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    user = ensure_demo_user(session)
    _add_payment(session, user, "order_dup")
    session.close()
    monkeypatch.setattr("apps.api.razorpay_service.fetch_payment", lambda _pid: None)
    payload = {
        "razorpay_order_id": "order_dup",
        "razorpay_payment_id": "pay_dup",
        "razorpay_signature": _sign_payment("order_dup", "pay_dup"),
    }
    client = TestClient(api_main.app)
    first = client.post("/api/payment/verify", json=payload)
    second = client.post("/api/payment/verify", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    session = factory()
    rows = session.query(Payment).filter_by(razorpay_order_id="order_dup").all()
    assert len(rows) == 1
    assert rows[0].status == "CAPTURED"
    session.close()


def test_verify_marks_gateway_failure(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    user = ensure_demo_user(session)
    _add_payment(session, user, "order_fail")
    session.close()
    monkeypatch.setattr(
        "apps.api.razorpay_service.fetch_payment",
        lambda _pid: {"id": "pay_fail", "order_id": "order_fail", "status": "failed"},
    )
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/verify",
        json={
            "razorpay_order_id": "order_fail",
            "razorpay_payment_id": "pay_fail",
            "razorpay_signature": _sign_payment("order_fail", "pay_fail"),
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "payment_failed"
    session = factory()
    assert session.query(Payment).filter_by(razorpay_order_id="order_fail").one().status == "FAILED"
    session.close()


def test_status_and_history_are_demo_scoped(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    demo = ensure_demo_user(session)
    other = User(code="other_user", display_name="Other", is_demo=False)
    session.add(other)
    session.flush()
    session.add_all(
        [
            Payment(
                user_id=demo.id,
                receipt="rcpt-demo",
                razorpay_order_id="order_demo",
                amount_paise=200,
                currency="INR",
                crop="coffee",
                quantity="1",
                status="CREATED",
            ),
            Payment(
                user_id=other.id,
                receipt="rcpt-other",
                razorpay_order_id="order_other",
                amount_paise=999,
                currency="INR",
                crop="pepper",
                quantity="9",
                status="CAPTURED",
            ),
        ]
    )
    session.commit()
    session.close()
    client = TestClient(api_main.app)
    history = client.get("/api/payment/history")
    assert history.status_code == 200
    body = history.json()
    ids = [row["razorpay_order_id"] for row in body["payments"]]
    assert ids == ["order_demo"]
    assert "order_other" not in ids
    assert body["authentication"] == "demo_identity_not_production"
    own = client.get("/api/payment/status/order_demo")
    hidden = client.get("/api/payment/status/order_other")
    assert own.status_code == 200
    assert own.json()["payment"]["status"] == "CREATED"
    assert hidden.status_code == 404


def test_webhook_rejects_invalid_signature(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/webhook",
        content=b'{"event":"payment.captured"}',
        headers={"X-Razorpay-Signature": "nope"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_webhook_signature"


def test_webhook_rejects_malformed_body(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    raw = b"not-json"
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": _sign_webhook(raw)},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_webhook"


def test_webhook_unknown_event_is_accepted(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    payload = {"id": "evt_unknown", "event": "invoice.paid", "payload": {}}
    raw = json.dumps(payload).encode("utf-8")
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": _sign_webhook(raw)},
    )
    assert response.status_code == 200
    assert response.json()["updated"] is False


def test_webhook_updates_status(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    user = ensure_demo_user(session)
    _add_payment(session, user, "order_wh")
    session.close()
    payload = {
        "id": "evt_wh",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_wh",
                    "order_id": "order_wh",
                    "status": "captured",
                }
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    client = TestClient(api_main.app)
    response = client.post(
        "/api/payment/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": _sign_webhook(raw)},
    )
    assert response.status_code == 200
    assert response.json()["updated"] is True
    session = factory()
    row = session.query(Payment).filter_by(razorpay_order_id="order_wh").one()
    assert row.status == "CAPTURED"
    assert row.webhook_verified is True
    assert row.razorpay_payment_id == "pay_wh"
    session.close()


def test_webhook_is_idempotent(tmp_path, monkeypatch):
    factory = _setup(tmp_path, monkeypatch)
    session = factory()
    user = ensure_demo_user(session)
    _add_payment(session, user, "order_idem")
    session.close()
    payload = {
        "id": "evt_idem",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_idem", "order_id": "order_idem"}}},
    }
    raw = json.dumps(payload).encode("utf-8")
    headers = {"X-Razorpay-Signature": _sign_webhook(raw)}
    client = TestClient(api_main.app)
    first = client.post("/api/payment/webhook", content=raw, headers=headers)
    second = client.post("/api/payment/webhook", content=raw, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    session = factory()
    rows = session.query(Payment).filter_by(razorpay_order_id="order_idem").all()
    events = session.query(PaymentWebhookEvent).filter_by(event_id="evt_idem").all()
    assert len(rows) == 1
    assert len(events) == 1
    assert rows[0].status == "CAPTURED"
    session.close()


def test_frontend_never_embeds_razorpay_secrets():
    js_files = list((ROOT / "frontend").rglob("*.js")) + list((ROOT / "frontend").rglob("*.html"))
    joined = "\n".join(path.read_text(encoding="utf-8") for path in js_files)
    assert "RAZORPAY_KEY_SECRET" not in joined
    assert "RAZORPAY_WEBHOOK_SECRET" not in joined
    assert "checkout.razorpay.com/v1/checkout.js" in joined
    payment_js = (ROOT / "frontend" / "js" / "dashboard-payment.js").read_text(encoding="utf-8")
    assert "preventDefault" in payment_js
    assert "createPaymentOrder" in payment_js
    assert "checkout.open" in payment_js
    assert "KEY_SECRET" not in payment_js
    html = (ROOT / "frontend" / "cropmandi_ai_dashboard" / "code.html").read_text(encoding="utf-8")
    assert 'id="dash-pay-button"' in html
    assert 'type="button"' in html
    assert "dashboard-payment.js" in html


def test_env_example_has_no_live_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "RAZORPAY_KEY_ID=" in text
    assert "RAZORPAY_KEY_SECRET=" in text
    assert "RAZORPAY_WEBHOOK_SECRET=" in text
    for line in text.splitlines():
        if line.startswith("RAZORPAY_KEY_SECRET=") or line.startswith("RAZORPAY_WEBHOOK_SECRET="):
            assert line.split("=", 1)[1].strip() == ""
