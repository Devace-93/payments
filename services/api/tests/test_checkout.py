"""``POST /api/checkout`` validation and the fake Stripe session, plus
``GET /api/checkout/<id>``."""
from __future__ import annotations

import uuid

from conftest import app_row, bearer, make_identity, session_cookie
from sqlalchemy import select

from dbcore.db import session_scope
from dbcore.models import CheckoutSession, Customer, Subscription


def donate(client, **overrides):
    body = {"app": "retro", "kind": "donation", "amount": 500, "currency": "usd", "origin": "https://retro.3m4.net"}
    body.update(overrides)
    return client.post("/api/checkout", json=body)


def test_guest_donation_creates_row_and_fake_url(client, fake_stripe):
    resp = donate(client, return_to="https://retro.3m4.net/thanks", public=True, display_name="Ana", message="gracias", lang="es")
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    row_id = uuid.UUID(body["id"])
    assert body["url"].startswith("http://localhost:8086/success?cs=cs_fake_")
    with session_scope() as session:
        row = session.get(CheckoutSession, row_id)
        assert row.status == "open" and row.stripe_session_id.startswith("cs_fake_")
        assert row.amount == 500 and row.currency == "usd" and row.kind == "donation"
        assert row.identity_id is None and row.public is True and row.lang == "es"
        assert row.return_to == "https://retro.3m4.net/thanks" and row.opener_origin == "https://retro.3m4.net"
    call = fake_stripe.checkout.sessions.calls[-1]
    assert call["options"] == {"idempotency_key": str(row_id)}
    params = call["params"]
    assert params["mode"] == "payment" and params["submit_type"] == "donate"
    assert params["customer_creation"] == "always" and "customer_email" not in params
    assert params["line_items"][0]["price_data"] == {"currency": "usd", "unit_amount": 500, "product": "prod_fake_donation_retro"}  # per-app "Support Retro" product
    assert params["client_reference_id"] == str(row_id)
    assert params["metadata"] == {"app": "retro", "kind": "donation", "checkout_id": str(row_id)}
    assert params["payment_intent_data"]["metadata"] == params["metadata"]
    assert params["success_url"] == "http://localhost:8086/success?cs={CHECKOUT_SESSION_ID}"
    assert params["cancel_url"] == f"http://localhost:8086/cancel?id={row_id}"
    assert params["locale"] == "es-419"
    assert params["automatic_tax"] == {"enabled": False}
    assert params["integration_identifier"] == "3m4-payments-testtest"
    assert "payment_method_types" not in params


def test_checkout_validation_errors(client):
    assert donate(client, app="nope").get_json()["error"]["code"] == "unknown_app"
    assert donate(client, kind="tip").get_json()["error"]["code"] == "validation_error"
    assert donate(client, currency="gbp").get_json()["error"]["code"] == "unsupported_currency"
    resp = donate(client, amount=100)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == {"code": "amount_too_small", "message": "Amount is below the minimum.", "min": 200}
    assert donate(client, amount=100, currency="mxn").get_json()["error"]["min"] == 2500
    assert donate(client, amount=10**7).get_json()["error"]["code"] == "amount_too_large"
    assert donate(client, amount="five").get_json()["error"]["code"] == "validation_error"
    assert donate(client, origin="https://evil.example").get_json()["error"]["code"] == "bad_origin"
    # exp.3m4.net is an allowed 3m4 origin globally but not one of retro's
    assert donate(client, origin="https://exp.3m4.net").get_json()["error"]["code"] == "bad_origin"
    assert donate(client, return_to="https://evil.example/x").get_json()["error"]["code"] == "bad_origin"
    assert donate(client, return_to="/relative").get_json()["error"]["code"] == "bad_origin"
    assert donate(client, origin="http://localhost:5173", return_to="http://localhost:5173/x").status_code == 201
    assert client.post("/api/checkout", data="x", content_type="text/plain").status_code == 415


def test_guest_subscription_requires_session(client):
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "pro_monthly"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "no_session"


def test_expired_session_on_subscription_says_session_expired(client):
    identity = make_identity()
    from conftest import session_token

    headers = {"Authorization": f"Bearer {session_token(identity, ttl=-3600)}"}
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "pro_monthly"}, headers=headers)
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "session_expired"


def test_subscription_checkout(client, fake_stripe):
    identity = session_cookie(client, make_identity(currency="mxn"))
    resp = client.post(
        "/api/checkout",
        json={"app": "retro", "kind": "subscription", "price": "pro_monthly", "currency": "mxn", "return_to": "https://retro.3m4.net/dashboard"},
    )
    assert resp.status_code == 201, resp.get_json()
    params = fake_stripe.checkout.sessions.calls[-1]["params"]
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_fake_retro_pro_monthly", "quantity": 1}]
    assert params["currency"] == "mxn"
    assert params["customer_email"] == identity["email"]
    assert params["allow_promotion_codes"] is True
    assert params["subscription_data"]["metadata"]["identity_id"] == identity["sub"]
    assert "submit_type" not in params and "customer_creation" not in params
    with session_scope() as session:
        row = session.scalar(select(CheckoutSession).where(CheckoutSession.kind == "subscription"))
        assert row.amount == 9900 and str(row.identity_id) == identity["sub"]
        customer = session.get(Customer, uuid.UUID(identity["sub"]))
        assert customer.email == identity["email"] and customer.preferred_currency == "mxn"


def test_subscription_unknown_price_and_currency(client):
    session_cookie(client, make_identity())
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "gold"})
    assert resp.get_json()["error"]["code"] == "unknown_price"
    resp = client.post("/api/checkout", json={"app": "info", "kind": "subscription", "price": "pro_monthly"})
    assert resp.get_json()["error"]["code"] == "unknown_price"


def test_already_subscribed(client):
    identity = session_cookie(client, make_identity())
    retro = app_row("retro")
    with session_scope() as session:
        session.add(
            Subscription(
                stripe_subscription_id="sub_existing",
                identity_id=uuid.UUID(identity["sub"]),
                app_id=retro.id,
                entitlement="pro",
                status="active",
            )
        )
    resp = client.post("/api/checkout", json={"app": "retro", "kind": "subscription", "price": "pro_monthly"})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "already_subscribed"


def test_logged_in_donation_reuses_stripe_customer(client, fake_stripe):
    identity = make_identity()
    with session_scope() as session:
        session.add(Customer(identity_id=uuid.UUID(identity["sub"]), stripe_customer_id="cus_123", email=identity["email"]))
    resp = donate(client, headers=None) if False else client.post(
        "/api/checkout",
        json={"app": "retro", "kind": "donation", "amount": 300, "currency": "eur"},
        headers=bearer(identity),
    )
    assert resp.status_code == 201
    params = fake_stripe.checkout.sessions.calls[-1]["params"]
    assert params["customer"] == "cus_123"
    assert "customer_creation" not in params and "customer_email" not in params
    assert params["metadata"]["identity_id"] == identity["sub"]


def test_get_checkout_status(client):
    resp = donate(client, return_to="https://retro.3m4.net/x")
    row_id = resp.get_json()["id"]
    with session_scope() as session:
        cs_id = session.get(CheckoutSession, uuid.UUID(row_id)).stripe_session_id
    for key in (row_id, cs_id):
        got = client.get(f"/api/checkout/{key}")
        assert got.status_code == 200
        body = got.get_json()
        assert body["id"] == row_id and body["status"] == "open" and body["kind"] == "donation"
        assert body["app"] == {"slug": "retro", "name": "Retro", "icon": "https://payments.3m4.net/icons/retro.png"}
        assert body["amount"] == 500 and body["currency"] == "usd"
        assert body["return_to"] == "https://retro.3m4.net/x" and body["opener_origin"] == "https://retro.3m4.net"
        assert body["needs_claim"] is False and body["claimed"] is False and body["entitlements"] == []
        assert got.headers["Access-Control-Allow-Origin"] == "*"
    assert client.get(f"/api/checkout/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/checkout/cs_nope").status_code == 404
    assert client.get("/api/checkout/garbage").status_code == 404


def test_donations_flag_gates_checkout(client, monkeypatch):
    monkeypatch.setenv("FEATURE_FLAG_OVERRIDES", "donations=off")
    resp = donate(client)
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "feature_disabled"
